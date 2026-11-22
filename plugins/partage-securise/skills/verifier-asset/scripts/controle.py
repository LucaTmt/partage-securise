#!/usr/bin/env python3
"""Contrôle d'un asset (skill, plugin, dossier, archive .zip ou fichier seul) avant partage ou installation.

Usage :
    python3 controle.py CHEMIN [--sortie DOSSIER] [--mode partager|installer] [--sans-outils]

Le script ne modifie jamais l'asset et n'exécute aucun de ses fichiers. Une archive ou un fichier
seul est contrôlé sur une copie, dans un dossier neuf créé dans le dossier de sortie, et les
commandes sont lancées depuis le dossier de sortie, jamais depuis l'asset.
Il combine des contrôles internes (bibliothèque standard Python uniquement) et, s'ils sont
installés, trois outils externes lancés en local, sans les clés d'API des fournisseurs de modèles
(variables retirées par « env -u » sous macOS et Linux) :
  - detect-secrets (version IBM), avec --no-verify et --no-version-check : rien n'est envoyé en ligne ;
  - SkillEvaluator : harness-check et quality-check ;
  - SkillSpector, avec --no-llm : aucun contenu n'est envoyé à un modèle.
Pour installer ou mettre à jour ces outils : installer_outils.py.

Sorties : rapport.md et rapport.json dans le dossier de sortie, rapport affiché à l'écran.
Code de sortie : 0 = rien relevé et tous les outils ont tourné ; 1 = points à vérifier, dont un
outil qui n'a pas tourné ; 2 = au moins un point bloquant ; 3 = contrôle impossible (chemin
introuvable, archive illisible ou non prise en charge, option invalide, dossier de sortie dans
l'asset) : rien n'a été contrôlé.
Les valeurs des secrets ne sont jamais affichées : seulement le fichier, la ligne et le type.
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

BLOQUANT, VERIFIER, INFO = "BLOQUANT", "À VÉRIFIER", "INFO"
CODE_IMPOSSIBLE = 3
TIMEOUT = 300
MAX_TEXTE = 2_000_000          # au-delà, un fichier n'est pas lu par les contrôles internes (signalé)
MAX_DECOMPRESSE = 500_000_000  # au-delà, archive refusée (bombe de décompression possible)
MAX_ENTREES = 20_000
ARCHIVES = {".zip", ".skill", ".plugin"}
AUTRES_ARCHIVES = {".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar", ".whl", ".jar"}
IMAGES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".tif", ".tiff", ".heic"}
POLICES = {".ttf", ".otf", ".woff", ".woff2"}
DOCUMENTS = {".md", ".txt", ".csv", ".json", ".jsonc", ".svg", ".html", ".htm", ".ipynb", ".xml"}
SCRIPTS_SHELL = {".sh", ".bash", ".zsh", ".ps1", ".psm1", ".bat", ".cmd"}
DOSSIERS_NON_ANALYSES = {
    ".git": (VERIFIER, "historique et configuration du dépôt : à retirer avant de partager"),
    "node_modules": (VERIFIER, "dépendances JavaScript embarquées, non analysées en détail"),
    ".venv": (VERIFIER, "environnement Python embarqué, non analysé en détail"),
    "venv": (VERIFIER, "environnement Python embarqué, non analysé en détail"),
    "__pycache__": (INFO, "fichiers Python compilés, non analysés"),
}
CLES_SSH = {"id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"}
EXT_CLES = {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".kdbx"}
# Noms écrits avec [.] : ce sont des fichiers que le contrôle signale, jamais des fichiers qu'il ouvre ailleurs que dans l'asset.
ACCES = re.compile(r"^[.](npmrc|pypirc|netrc|git-credentials|dockercfg)$")
MODELE_ENV = re.compile(r"^[.]env[.](example|sample|template|dist)$")
FICHIER_ENV = re.compile(r"^[.]env([.].+)?$")

# Les outils absents s'installent, à leur dernière version publiée, avec installer_outils.py.
INSTALLEUR = str(Path(__file__).resolve().parent / "installer_outils.py")
INSTALL = f'python3 "{INSTALLEUR}" --installer'
# Clés d'API retirées de l'environnement des outils (« env -u », macOS et Linux) : aucun appel à un modèle possible.
CLES_API = ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "AZURE_OPENAI_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY",
            "MISTRAL_API_KEY", "NVIDIA_API_KEY", "NGC_API_KEY", "WATSONX_APIKEY", "IBM_CLOUD_API_KEY", "HF_TOKEN"]

# Caractères invisibles suspects (escapes écrites \\uXXXX pour que ce fichier n'en contienne aucun).
INVISIBLES = re.compile("[\\u200b\\u200c\\u200e\\u200f\\u202a-\\u202e\\u2060-\\u2064\\u2066-\\u2069\\ufeff"
                        "\\U000e0000-\\U000e007f\\U000e0100-\\U000e01ef]")
SELECTEURS = re.compile("[\\ufe00-\\ufe0f]{2,}")  # suite de sélecteurs de variante : texte dissimulé possible
ZWJ = re.compile("\\u200d")
BOM = chr(0xFEFF)
SECRETS = [
    ("Clé AWS", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("Clé privée", re.compile(r"-----BEGIN ([A-Z0-9]+ )*PRIVATE KEY-----")),
    ("Jeton GitHub", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})")),
    ("Jeton GitLab", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}")),
    ("Jeton Slack", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("Jeton npm", re.compile(r"\bnpm_[A-Za-z0-9]{30,}")),
    ("Clé d'API (sk-)", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("Clé Stripe", re.compile(r"\b[rs]k_live_[A-Za-z0-9]{16,}")),
    ("Clé Google", re.compile(r"\bAIza[0-9A-Za-z_-]{35}")),
]
URL_IDENTIFIANTS = re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s/:@'\"<>]+:(?P<val>[^\s/@'\"<>]{3,})@[^\s/'\"<>]+")
SECRET_CLAIR = re.compile(r"(?i)[\w.-]*(passw(or)?d|pwd|secret|token|api_?key|access_?key)[\"']?\s*[:=]\s*[\"']?"
                          r"(?P<val>[^\s\"'`,;]{8,})")
FACTICE = re.compile(r"(?i)^(x{4,}|\*{4,}|\.{3,}|<.*|\$.*|\{\{.*|%.*|.*\(.*|your[_-].*|my[_-].*|change.?me.*|"
                     r"example.*|exemple.*|placeholder.*|dummy.*|redacted.*|none|null|true|false|"
                     r"os\.environ.*|process\.env.*|env\[.*)$")
RISQUES = [  # (libellé, motif, portée : tous / exec = vecteurs d'exécution / code)
    ("Script téléchargé puis passé directement à un shell",
     re.compile(r"(curl|wget)[^\n|]*\|\s*(sudo\s+)?(ba|z)?sh\b"), "tous"),
    ("Script téléchargé puis exécuté",
     re.compile(r"(curl|wget)\s[^\n]*(-o|-O|--output)\s*\S+[^\n]*(&&|;)\s*(sudo\s+)?((ba|z)?sh|python3?)\b"), "tous"),
    ("Contenu téléchargé exécuté par PowerShell",
     re.compile(r"(?i)((iwr|irm|invoke-webrequest|invoke-restmethod|downloadstring)[^\n]*\|\s*iex\b"
                r"|\binvoke-expression\b|\biex\s*\()"), "tous"),
    ("Paquet téléchargé et lancé à la volée",
     re.compile(r"(?i)\b(npx\s+(-y|--yes)\b|uvx\s+[\w@]|pipx\s+run\b|bunx\s+[\w@])"), "tous"),
    ("Commande avec sudo", re.compile(r"(^|[\s;&|`(])sudo\s"), "tous"),
    ("Suppression récursive large", re.compile(r"rm\s+-[a-zA-Z]*r[a-zA-Z]*f?\s+(/|~|\$HOME)(\s|$)"), "tous"),
    ("Droits 777", re.compile(r"chmod\s+(-R\s+)?777"), "tous"),
    ("Décodage base64 puis exécution",
     re.compile(r"(base64\s+(-d|--decode)[^\n]*\|\s*(ba)?sh)|(exec\s*\(\s*(base64\.)?b64decode)"), "tous"),
    ("Envoi de données vers l'extérieur",
     re.compile(r"(?i)\b(curl|wget|nc|ncat)\b[^\n]*(--data|--upload-file|\s-d\s|\s-F\s|\s-T\s)"), "exec"),
    ("Accès à des fichiers d'identifiants du poste",
     re.compile(r"(~|\$HOME|%USERPROFILE%)[/\\]\.(ssh|aws|gnupg|kube|docker)\b"), "exec"),
    ("eval / exec dynamique", re.compile(r"(^|[^.\w])(eval|exec)\s*\("), "code"),
    ("Shell activé dans subprocess", re.compile(r"shell\s*=\s*True"), "code"),
]
INJECTION = re.compile(r"(?i)(ignore[rz]?\s+(all\s+|the\s+|any\s+|toutes\s+)?(les\s+|tes\s+|vos\s+)?(previous|prior|above|"
                       r"précédentes|consignes|instructions)"
                       r"|disregard\s+(all|previous|the)|(do\s+not|don't)\s+(tell|inform|mention)[^.\n]{0,20}user"
                       r"|sans\s+(le\s+)?(dire|signaler|prévenir)[^.\n]{0,20}utilisat|ne\s+(le\s+)?(dis|signale)\s+pas\s+à\s+l'utilisat"
                       r"|you\s+are\s+now\s+|system\s+prompt\s*:)")
ABS_PATH = re.compile(r"(/Users/[A-Za-z0-9._-]+/|/home/[A-Za-z0-9._-]+/|[A-Za-z]:\\Users\\[A-Za-z0-9._ -]+\\)")
EMAIL = re.compile(r"(?<![\w.%+:/-])(?P<local>[A-Za-z0-9._%+-]+)@(?P<dom>[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.(?P<tld>[A-Za-z]{2,}))\b")
EXT_PAS_TLD = {"png", "jpg", "jpeg", "gif", "svg", "webp", "ico", "pdf", "js", "css", "ts", "py", "md", "json",
               "yaml", "yml", "txt", "html", "zip"}
URL = re.compile(r"https?://(?:[^\s/@'\"<>]+@)?([A-Za-z0-9.-]+)")
WHEN = re.compile(r"(?i)(à utiliser|a utiliser|utiliser quand|utilise[rz]? (ce|cette|le|la)|use (this )?when|use for|"
                  r"quand (on|l'utilisateur|tu|vous))")
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def stop(message):
    """Arrêt sans contrôle : message sur la sortie d'erreur, code 3 (distinct des codes de verdict)."""
    print(message, file=sys.stderr)
    sys.exit(CODE_IMPOSSIBLE)


class Parser(argparse.ArgumentParser):
    def error(self, message):  # argparse sortirait avec 2, confondu avec « point bloquant »
        self.print_usage(sys.stderr)
        stop(f"{self.prog} : {message}")


def nettoyer(texte, n=240):
    """Texte venant de l'asset ou d'un outil, rendu inoffensif pour le rapport : une seule ligne,
    sans caractère de contrôle ni invisible, sans accent grave, longueur bornée."""
    s = INVISIBLES.sub(lambda m: f"<U+{ord(m.group()):04X}>", str(texte))
    s = "".join(c if c.isprintable() else " " for c in s).replace("`", "'")
    return s if len(s) <= n else s[:n] + "…"


class Rapport:
    def __init__(self):
        self.points = []
        self.outils = {}

    def add(self, niveau, controle, message, fichier=None):
        self.points.append({"niveau": niveau, "controle": controle, "message": nettoyer(message, 400),
                            "fichier": nettoyer(fichier) if fichier else None})


def est_dans(chemin, parent):
    """Vrai si chemin est parent ou se trouve dessous, y compris sur un disque insensible à la casse."""
    parent = Path(parent)
    for a in [Path(chemin), *Path(chemin).parents]:
        if a.exists():
            try:
                if os.path.samefile(a, parent):
                    return True
            except OSError:
                pass
    return False


def rel(p, root):
    return p.relative_to(root).as_posix()


def extraire(archive, dest, r):
    """Vérifie toutes les entrées d'un zip, puis l'extrait sans chemin absolu, sans .. et sans lien symbolique."""
    dest = dest.resolve()
    with zipfile.ZipFile(archive) as z:
        infos = z.infolist()
        if len(infos) > MAX_ENTREES:
            raise ValueError(f"archive de {len(infos)} entrées : extraction refusée")
        total = sum(i.file_size for i in infos)
        if total > MAX_DECOMPRESSE:
            raise ValueError(f"archive de {total // 1_000_000} Mo une fois décompressée : extraction refusée")
        for i in infos:
            if i.flag_bits & 0x1:
                raise PermissionError("archive chiffrée")
            cible = (dest / i.filename).resolve()
            if not (str(cible).startswith(str(dest) + os.sep) or cible == dest):
                raise ValueError(f"chemin dangereux dans l'archive : {nettoyer(i.filename)}")
        liens = []
        for i in infos:
            if (i.external_attr >> 16) & 0o170000 == 0o120000:
                liens.append((i.filename, z.read(i).decode("utf-8", "replace")))
                continue
            z.extract(i, dest)
    for nom, cible in liens:
        dehors = cible.startswith(("/", "\\")) or ".." in Path(cible).parts or re.match(r"^[A-Za-z]:", cible)
        r.add(BLOQUANT if dehors else VERIFIER, "Liens", f"lien symbolique dans l'archive, non extrait (cible : {cible})", nom)
    return dest


def lister(root, r):
    """Fichiers ordinaires de l'asset. Liens symboliques et dossiers non analysés sont signalés, jamais suivis."""
    fichiers = []
    for dirpath, dirnames, filenames in os.walk(root):
        d = Path(dirpath)
        garder = []
        for dn in sorted(dirnames):
            p = d / dn
            if p.is_symlink():
                signaler_lien(p, root, r)
            elif dn in DOSSIERS_NON_ANALYSES:
                niveau, motif = DOSSIERS_NON_ANALYSES[dn]
                r.add(niveau, "Contenu non analysé", f"dossier {dn} : {motif}", rel(p, root))
                if dn == ".git" and (p / "config").is_file() and not (p / "config").is_symlink():
                    fichiers.append(p / "config")  # un jeton se cache souvent dans l'URL du dépôt
            else:
                garder.append(dn)
        dirnames[:] = garder
        for f in sorted(filenames):
            p = d / f
            if p.is_symlink():
                signaler_lien(p, root, r)
            elif p.is_file():
                fichiers.append(p)
    return fichiers


def signaler_lien(p, root, r):
    try:
        dehors = not est_dans(p.resolve(), root)
    except (OSError, RuntimeError):
        dehors = True
    if dehors:
        r.add(BLOQUANT, "Liens", "lien symbolique vers un fichier hors de l'asset : son contenu partirait avec un zip", rel(p, root))
    else:
        r.add(VERIFIER, "Liens", "lien symbolique : à remplacer par le fichier lui-même", rel(p, root))


def lire(p):
    """(texte, None) pour un fichier texte, (None, motif) sinon : binaire, trop gros ou illisible."""
    try:
        if p.stat().st_size > MAX_TEXTE:
            return None, "trop gros"
        data = p.read_bytes()
    except OSError:
        return None, "illisible"
    if b"\x00" in data[:8192]:
        return None, "binaire"
    return data.decode("utf-8", errors="replace"), None


def find_skills(root):
    if (root / "SKILL.md").is_file():
        return [root]
    return sorted({p.parent for p in root.rglob("SKILL.md")
                   if p.is_file() and not p.is_symlink()
                   and not any(s in p.relative_to(root).parts for s in DOSSIERS_NON_ANALYSES)})


def est_plugin(root):
    return any((root / m).exists() for m in (".claude-plugin", "hooks", ".mcp.json", "commands", "agents"))


def parse_frontmatter(text):
    """Retourne (dict ou None, erreur ou None, brut)."""
    text = text.lstrip(BOM)
    if not text.startswith("---"):
        return None, "pas d'en-tête YAML (le fichier doit commencer par ---)", ""
    end = text.find("\n---", 3)
    if end == -1:
        return None, "en-tête YAML non refermé", ""
    raw = text[3:end].strip("\n")
    try:
        import yaml  # PyYAML, présent dans la plupart des environnements
        data = yaml.safe_load(raw)
        if not isinstance(data, dict):
            return None, "l'en-tête YAML n'est pas un dictionnaire", raw
        return data, None, raw
    except ImportError:
        data, err, lignes, i = {}, None, raw.splitlines(), 0
        while i < len(lignes):
            m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", lignes[i])
            i += 1
            if not m:
                continue
            key, val = m.group(1), m.group(2).strip()
            if val[:1] in {"|", ">"}:  # bloc littéral ou replié : lignes indentées qui suivent
                bloc = []
                while i < len(lignes) and (lignes[i][:1] in {" ", "\t"} or not lignes[i].strip()):
                    bloc.append(lignes[i].strip())
                    i += 1
                val = ("\n" if val[0] == "|" else " ").join(bloc).strip()
            elif val and val[0] not in "\"'" and re.search(r":\s", val):
                err = f"la valeur de « {key} » contient « : » sans guillemets : YAML invalide pour un lecteur strict"
            else:
                val = val.strip("\"'")
            data[key] = val
        return (None if err else data), err, raw
    except Exception as e:  # yaml.YAMLError
        return None, f"YAML invalide ({str(e).splitlines()[0]})", raw


def check_skill(skill_dir, root, r, nom_attendu, racine_archive=False):
    md = skill_dir / "SKILL.md"
    mdrel = rel(md, root)
    label = nom_attendu
    text = md.read_text(encoding="utf-8", errors="replace")
    data, err, _ = parse_frontmatter(text)
    if err:
        r.add(BLOQUANT, "En-tête YAML", f"{label} : {err}. Plusieurs agents ignoreront la skill.", mdrel)
        return
    name, desc = data.get("name"), data.get("description")
    if not name:
        r.add(BLOQUANT, "En-tête YAML", f"{label} : champ name absent", mdrel)
    elif not NAME_RE.match(str(name)) or len(str(name)) > 64:
        r.add(VERIFIER, "En-tête YAML", f"{label} : name « {name} » devrait être en minuscules et tirets, 64 caractères max", mdrel)
    elif racine_archive:
        r.add(INFO, "En-tête YAML", f"{label} : dans Bob, le dossier d'installation devra s'appeler « {name} »", mdrel)
    elif str(name) != nom_attendu:
        r.add(VERIFIER, "En-tête YAML", f"{label} : name « {name} » différent du nom du dossier « {nom_attendu} » (obligatoire dans Bob)", mdrel)
    if not desc or not str(desc).strip():
        r.add(BLOQUANT, "En-tête YAML", f"{label} : description absente ou vide", mdrel)
    else:
        d = str(desc)
        if len(d) > 1024:
            r.add(BLOQUANT, "Description", f"{label} : description de {len(d)} caractères (1 024 max)", mdrel)
        if not WHEN.search(d):
            r.add(VERIFIER, "Description", f"{label} : la description ne dit pas quand utiliser la skill (« À utiliser quand… »)", mdrel)
    lines = text.count("\n") + 1
    if lines > 500 or len(text) > 20000:
        r.add(VERIFIER, "Taille", f"{label} : SKILL.md fait {lines} lignes et {len(text)} caractères ; déplacer code et références dans scripts/, assets/ ou references/", mdrel)


def invisibles(ligne):
    """Vrai si la ligne contient un caractère invisible suspect. Le ZWJ est toléré entre deux emoji."""
    if INVISIBLES.search(ligne) or SELECTEURS.search(ligne):
        return True
    for m in ZWJ.finditer(ligne):
        i = m.start()
        avant, apres = ligne[i - 1:i], ligne[i + 1:i + 2]
        if not (avant and apres and ord(avant) >= 0x2600 and ord(apres) >= 0x2600):
            return True
    return False


def est_vecteur(p, root):
    """Fichiers qu'un agent ou un plugin exécute : scripts shell, hooks, serveurs MCP, commandes, bin/."""
    parts = [x.lower() for x in p.relative_to(root).parts]
    return (p.suffix.lower() in SCRIPTS_SHELL or p.name.lower() in {"hooks.json", ".mcp.json", "mcp.json"}
            or any(x in parts[:-1] for x in ("hooks", "commands", "bin")))


def scan_files(root, fichiers, r, mode):
    domains, emails, licences = {}, {}, []
    images, polices, binaires, executables, non_lus, imbriquees = [], [], [], [], [], []
    for p in fichiers:
        relp = rel(p, root)
        low, ext = p.name.lower(), p.suffix.lower()
        if MODELE_ENV.match(low):
            r.add(VERIFIER, "Secrets", "modèle de fichier d'environnement : vérifier qu'il ne contient que des valeurs factices", relp)
        elif FICHIER_ENV.match(low):
            r.add(BLOQUANT, "Secrets", "fichier d'environnement présent dans l'asset", relp)
        if low in CLES_SSH:
            r.add(BLOQUANT, "Secrets", "fichier de clé privée SSH présent dans l'asset", relp)
        elif ext in EXT_CLES:
            r.add(VERIFIER, "Secrets", "fichier de clé ou de certificat : vérifier qu'il ne contient pas de clé privée", relp)
        if ACCES.match(low):
            r.add(VERIFIER, "Secrets", "fichier de configuration d'accès (registre, dépôt) : vérifier qu'il ne contient pas de jeton", relp)
        if ext in ARCHIVES or ext in AUTRES_ARCHIVES:
            imbriquees.append(relp)
        if re.match(r"(licen[cs]e|copying|ofl|notice)", low):
            licences.append(relp)
        if ext in POLICES:
            polices.append(relp)
        text, motif = lire(p)
        if text is None:
            if motif == "binaire":
                if ext in IMAGES:
                    images.append(relp)
                elif ext not in POLICES and ext not in ARCHIVES and ext not in AUTRES_ARCHIVES:
                    (executables if os.name != "nt" and os.access(p, os.X_OK) else binaires).append(relp)
            else:
                non_lus.append(f"{relp} ({motif})")
            continue
        is_code = ext not in DOCUMENTS
        vecteur = est_vecteur(p, root)
        injection_vue = False
        for n, line in enumerate(text.splitlines(), 1):
            if n == 1:
                line = line.lstrip(BOM)
            if invisibles(line):
                r.add(BLOQUANT, "Texte caché", "caractère Unicode invisible (peut masquer une instruction)", f"{relp}:{n}")
            for label, rx in SECRETS:
                if rx.search(line):
                    r.add(BLOQUANT, "Secrets", f"{label} probable (valeur non affichée)", f"{relp}:{n}")
            m = URL_IDENTIFIANTS.search(line)
            if m and not FACTICE.match(m.group("val")):
                r.add(BLOQUANT, "Secrets", "identifiant et mot de passe dans une URL (valeur non affichée)", f"{relp}:{n}")
            for m in SECRET_CLAIR.finditer(line):
                if not FACTICE.match(m.group("val")):
                    r.add(BLOQUANT, "Secrets", "secret en clair probable (valeur non affichée)", f"{relp}:{n}")
                    break
            for label, rx, portee in RISQUES:
                if (portee == "code" and not is_code) or (portee == "exec" and not vecteur):
                    continue
                if rx.search(line):
                    niveau = BLOQUANT if (vecteur and mode == "installer") else VERIFIER
                    r.add(niveau, "Scripts", label + (" (lancé automatiquement par l'agent ou le plugin)" if vecteur else ""), f"{relp}:{n}")
            if INJECTION.search(line):
                injection_vue = True
                r.add(VERIFIER, "Instructions", "formule typique d'injection : vérifier qu'elle ne détourne pas l'agent", f"{relp}:{n}")
            m = ABS_PATH.search(line)
            if m:
                r.add(VERIFIER, "Portabilité", f"chemin propre à un poste ({m.group(1)})", f"{relp}:{n}")
            for m in EMAIL.finditer(line):
                local, dom, tld = m.group("local"), m.group("dom"), m.group("tld").lower()
                if local.lower() == "git" or tld in EXT_PAS_TLD or re.match(r"(?i)no-?reply", local) \
                        or re.search(r"(?i)(^|\.)example\.(com|org|net)$", dom):
                    continue
                emails.setdefault(f"{local[:1]}***@{dom.lower()}", f"{relp}:{n}")
            for dom in URL.findall(line):
                domains.setdefault(dom.lower(), relp)
        if not injection_vue and INJECTION.search(re.sub(r"\s+", " ", text)):
            r.add(VERIFIER, "Instructions", "formule typique d'injection coupée sur plusieurs lignes", relp)
        if ext in {".md", ".html", ".htm"} and "<!--" in text:
            r.add(VERIFIER, "Texte caché", "commentaire HTML : vérifier qu'il ne contient pas d'instruction", relp)
    if polices and not licences:
        r.add(VERIFIER, "Licences", f"{len(polices)} fichier(s) de police sans fichier de licence", polices[0])
    for e, where in list(emails.items())[:20]:
        r.add(VERIFIER, "Données personnelles", f"adresse e-mail présente ({e}) : contact public ou donnée à retirer ?", where)
    if imbriquees:
        r.add(VERIFIER, "Contenu non analysé", f"{len(imbriquees)} archive(s) imbriquée(s), non ouvertes : les décompresser et les contrôler à part ({', '.join(imbriquees[:5])})")
    if executables:
        r.add(VERIFIER, "Scripts", f"{len(executables)} fichier(s) binaire(s) exécutable(s) : {', '.join(executables[:5])}")
    if binaires:
        r.add(VERIFIER, "Contenu non analysé", f"{len(binaires)} fichier(s) binaire(s) non analysé(s) (PDF, Office, autres) : à relire ({', '.join(binaires[:5])})")
    if non_lus:
        r.add(VERIFIER, "Contenu non analysé", f"{len(non_lus)} fichier(s) non lu(s) : {', '.join(non_lus[:5])}")
    if images:
        r.add(INFO, "Contenu non analysé", f"{len(images)} image(s) : vérifier à l'œil qu'aucune ne montre de donnée sensible (capture d'écran, client)", images[0])
    if domains:
        r.add(INFO, "Adresses externes", "domaines cités : " + ", ".join(sorted(domains)[:30]))


def commandes(obj):
    """Valeurs des clés « command » d'un JSON de hooks, à toute profondeur."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "command" and isinstance(v, str):
                yield v
            else:
                yield from commandes(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from commandes(v)


def check_plugin(root, fichiers, r):
    """Ce qu'un plugin exécute de lui-même : hooks, serveurs MCP, commandes slash avec shell, bin/."""
    for p in fichiers:
        relp, low = rel(p, root), p.name.lower()
        parts = [x.lower() for x in p.relative_to(root).parts]
        if low in {"hooks.json", "plugin.json", "settings.json", "settings.local.json", ".mcp.json", "mcp.json"}:
            text, _ = lire(p)
            try:
                data = json.loads(text or "")
            except ValueError:
                continue
            if not isinstance(data, dict):
                continue
            for cmd in commandes(data if low == "hooks.json" else data.get("hooks")):
                r.add(VERIFIER, "Plugin", f"hook lancé automatiquement par l'agent : {cmd}", relp)
            serveurs = data.get("mcpServers")
            if isinstance(serveurs, dict):
                for nom, conf in serveurs.items():
                    if isinstance(conf, dict):
                        ligne = " ".join([str(conf.get("command", ""))] + [str(x) for x in conf.get("args") or []]).strip()
                        r.add(VERIFIER, "Plugin", f"serveur MCP « {nom} » lancé par l'agent : {ligne or conf.get('url', '')}", relp)
        if "commands" in parts[:-1] and p.suffix.lower() == ".md":
            text, _ = lire(p)
            for n, ligne in enumerate((text or "").splitlines(), 1):
                if re.match(r"^\s*!", ligne) or "!`" in ligne:
                    r.add(VERIFIER, "Plugin", f"commande slash qui exécute du shell : {ligne.strip()}", f"{relp}:{n}")
        if "bin" in parts[:-1]:
            r.add(VERIFIER, "Plugin", "exécutable fourni dans bin/, que certains agents ajoutent au PATH", relp)


def which(tool, root):
    """Chemin de l'outil, jamais un fichier de l'asset contrôlé."""
    for p in (shutil.which(tool), shutil.which(tool, path=str(Path.home() / ".local" / "bin"))):
        if p and not est_dans(Path(p).resolve(), root):
            return p
    return None


def run(cmd, cwd=None):
    try:
        env_u = shutil.which("env") if os.name != "nt" else None
        if env_u:
            cmd = [env_u] + [x for k in CLES_API for x in ("-u", k)] + list(cmd)
        p = subprocess.run(cmd, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT)
        return p.returncode, p.stdout + p.stderr
    except subprocess.TimeoutExpired:
        return None, f"délai de {TIMEOUT} s dépassé"
    except OSError as e:
        return None, str(e)


def tool_version(exe, options=()):
    """Relève la version installée, pour le rapport."""
    code, txt = run([exe, *options, "--version"])
    m = re.search(r"(\d+\.\d+\.\d+\S*)", txt or "")
    return m.group(1) if m else "inconnue"


def tool_detect_secrets(root, fichiers, out, r):
    exe = which("detect-secrets", root)
    if not exe:
        r.outils["detect-secrets"] = {"statut": "non installé", "installation": INSTALL}
        return
    version = tool_version(exe, ["--no-version-check"])
    sortie = out / "detect-secrets-sortie.json"
    if sortie.exists():
        sortie.unlink()
    # « ./ » devant chaque chemin : un nom de fichier ne peut pas passer pour une option de l'outil.
    liste = ["./" + rel(p, root) for p in fichiers if p.stat().st_size <= 20_000_000]
    results, raw = {}, []
    for i in range(0, len(liste), 100):
        code, txt = run([exe, "--no-version-check", "scan", "--no-verify"] + liste[i:i + 100], cwd=root)
        raw.append(txt)
        try:
            results.update(json.JSONDecoder().raw_decode(txt[txt.index("{"):])[0].get("results", {}))
        except (ValueError, AttributeError):
            sortie.write_text("\n".join(raw), encoding="utf-8")
            r.outils["detect-secrets"] = {"statut": "erreur", "detail": nettoyer(txt[-300:])}
            return
    sortie.write_text("\n".join(raw), encoding="utf-8")
    n = 0
    for f, items in results.items():
        for it in items:
            n += 1
            f2 = f[2:] if f.startswith("./") else f
            r.add(BLOQUANT, "Secrets", f"detect-secrets : {it.get('type')} (valeur non affichée)", f"{f2}:{it.get('line_number')}")
    r.outils["detect-secrets"] = {"statut": "ok", "version": version, "fichiers": len(liste), "secrets": n}


def tool_harness(skill, label, root, out, r):
    exe = which("skillevaluator", root)
    if not exe:
        r.outils.setdefault("skillevaluator", {"statut": "non installé", "installation": INSTALL})
        return
    r.outils.setdefault("skillevaluator", {"statut": "ok", "version": tool_version(exe)})
    jf = out / f"harness-{label}.json"
    if jf.exists():
        jf.unlink()
    code, txt = run([exe, "harness-check", str(skill), "--json", str(jf)])
    (out / f"harness-{label}.txt").write_text(txt, encoding="utf-8")
    try:
        d = json.loads(jf.read_text(encoding="utf-8"))["harness_compatibility"]
        rows = next(iter(d.values()))
        res = {x["harness"]: x["status"] for x in rows}
    except Exception:
        r.outils[f"harness-check {label}"] = {"statut": "erreur", "detail": nettoyer(txt[-300:])}
        return
    r.outils[f"harness-check {label}"] = {"statut": "ok", "agents": res}
    for x in rows:
        if x.get("status") != "loads":
            msgs = "; ".join(str(f.get("message", "")) for f in (x.get("findings") or [])[:2] if isinstance(f, dict))
            lvl = BLOQUANT if x.get("harness") == "claude-code" and x.get("status") == "not_loaded" else VERIFIER
            r.add(lvl, "Chargement", f"{label} : {x.get('display_name', x.get('harness'))} = {x.get('status')} ({msgs})")


def tool_quality(skill, label, root, out, r):
    exe = which("skillevaluator", root)
    if not exe:
        return
    code, txt = run([exe, "quality-check", str(skill)])
    (out / f"quality-{label}.txt").write_text(txt, encoding="utf-8")
    m = re.search(r"Overall:\s*([\d.]+)/100\s*\(Grade:\s*(\w)\)", txt)
    if m:
        r.outils[f"quality-check {label}"] = {"statut": "ok", "score": float(m.group(1)), "note": m.group(2)}
        if float(m.group(1)) < 70:
            r.add(VERIFIER, "Qualité", f"{label} : score {m.group(1)}/100 sous le seuil de 70")
    else:
        r.outils[f"quality-check {label}"] = {"statut": "erreur", "detail": nettoyer(txt[-300:])}


def tool_skillspector(cible, label, root, out, r, deja=()):
    exe = which("skillspector", root)
    if not exe:
        r.outils.setdefault("skillspector", {"statut": "non installé", "installation": INSTALL})
        return
    r.outils.setdefault("skillspector", {"statut": "ok", "version": tool_version(exe)})
    jf = out / f"skillspector-{label}.json"
    if jf.exists():
        jf.unlink()
    code, txt = run([exe, "scan", str(cible), "--no-llm", "-f", "json", "-o", str(jf)])
    try:
        d = json.loads(jf.read_text(encoding="utf-8"))
    except Exception:
        r.outils[f"skillspector {label}"] = {"statut": "erreur", "detail": nettoyer(txt[-300:])}
        return
    ra = d.get("risk_assessment") or {}
    cov = (d.get("analysis_completeness") or {}).get("coverage_percent")
    rec = ra.get("recommendation")
    issues = [it for it in d.get("issues") or [] if isinstance(it, dict)]
    r.outils[f"skillspector {label}"] = {"statut": "ok", "score": ra.get("score"), "recommandation": rec,
                                         "couverture": cov, "alertes": len(issues)}
    vus = set()
    for it in issues:
        motif = it.get("pattern") or ""
        detail = it.get("finding") or it.get("explanation") or ""
        cle = (it.get("id"), detail)
        if cle in vus:
            continue
        vus.add(cle)
        sev = it.get("severity", "")
        lvl = BLOQUANT if sev == "CRITICAL" else VERIFIER if sev in {"HIGH", "MEDIUM"} else INFO
        note = " (souvent un faux positif : fichier que l'outil ne sait pas analyser)" if it.get("id") == "AE1" else ""
        loc = it.get("location") if isinstance(it.get("location"), dict) else {}
        if loc.get("file") and any(str(loc["file"]).startswith(d + "/") for d in deja):
            continue  # déjà signalé par l'analyse de la skill
        ou = f"{loc.get('file')}:{loc.get('start_line')}" if loc.get("file") else None
        r.add(lvl, "SkillSpector", f"{label} : [{sev}] {it.get('id')} {motif} : {detail}{note}", ou)
    if rec and rec not in {"SAFE", "CAUTION"}:
        r.add(BLOQUANT, "SkillSpector", f"{label} : recommandation {rec}")
    if isinstance(cov, (int, float)) and cov < 100:
        r.add(VERIFIER, "SkillSpector", f"{label} : analyse incomplète (couverture {cov} %)")


def render_md(r, asset, skills, mode, out):
    order = {BLOQUANT: 0, VERIFIER: 1, INFO: 2}
    n_b = sum(p["niveau"] == BLOQUANT for p in r.points)
    n_v = sum(p["niveau"] == VERIFIER for p in r.points)
    if n_b:
        verdict = "Ne pas partager en l'état" if mode == "partager" else "Ne pas installer en l'état"
    elif n_v:
        verdict = "Points à vérifier avant de partager" if mode == "partager" else "Points à vérifier avant d'installer"
    else:
        verdict = "Aucun point relevé par les contrôles automatiques"
    L = [f"# Contrôle de {nettoyer(asset.name)}", "",
         f"Date : {datetime.date.today().isoformat()} · mode : {mode} · skills trouvées : {len(skills)}", "",
         f"**Verdict automatique : {verdict}** ({n_b} bloquant(s), {n_v} à vérifier).",
         "Ce verdict ne couvre que ce qu'un script peut voir : la revue manuelle de la checklist reste à faire.", "",
         "## Outils", ""]
    if not r.outils:
        L.append("Aucun outil externe lancé.")
    for k, v in r.outils.items():
        details = ", ".join(f"{a} : {b}" for a, b in v.items() if a != "statut")
        L.append(f"- {nettoyer(k)} : {v['statut']}" + (f" ({nettoyer(details, 400)})" if details else ""))
    L += ["", "## Points relevés", ""]
    if not r.points:
        L.append("Aucun.")
    for p in sorted(r.points, key=lambda x: order[x["niveau"]]):
        where = f" `{p['fichier']}`" if p["fichier"] else ""
        L.append(f"- **{p['niveau']}** · {p['controle']} : {p['message']}{where}")
    L += ["", f"Fichiers bruts des outils : {out}"]
    return "\n".join(L) + "\n", (2 if n_b else 1 if n_v else 0), verdict


def terminer(r, src, skills, mode, out):
    md, code, verdict = render_md(r, src, skills, mode, out)
    (out / "rapport.md").write_text(md, encoding="utf-8")
    (out / "rapport.json").write_text(json.dumps({"asset": str(src), "mode": mode, "verdict": verdict, "code": code,
                                                  "outils": r.outils, "points": r.points},
                                                 ensure_ascii=False, indent=1), encoding="utf-8")
    print(md)
    sys.exit(code)


def securise(r, nom, fonction, *args):
    """Un outil qui plante ne fait pas planter le contrôle : il est noté en erreur."""
    try:
        fonction(*args)
    except Exception as e:
        r.outils[nom] = {"statut": "erreur", "detail": nettoyer(f"{type(e).__name__} : {e}", 300)}


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    ap = Parser(description="Contrôle d'un asset avant partage ou installation.")
    ap.add_argument("chemin")
    ap.add_argument("--sortie", help="dossier où écrire le rapport (par défaut : dossier temporaire)")
    ap.add_argument("--mode", choices=["partager", "installer"], default="partager")
    ap.add_argument("--sans-outils", action="store_true", help="contrôles internes seulement")
    a = ap.parse_args()

    src = Path(a.chemin).expanduser().resolve()
    if not src.exists():
        stop(f"Introuvable : {src}")
    archive = src.is_file() and src.suffix.lower() in ARCHIVES
    if src.is_file() and (src.suffix.lower() in AUTRES_ARCHIVES):
        stop(f"Format d'archive non pris en charge ({src.suffix}) : décompresser l'archive, puis contrôler le dossier obtenu.")
    out = Path(a.sortie).expanduser().resolve() if a.sortie else None
    if out and src.is_dir() and est_dans(out, src):
        stop("Le dossier de sortie doit être en dehors de l'asset contrôlé.")  # vérifié avant de créer quoi que ce soit
    try:
        out = out or Path(tempfile.mkdtemp(prefix="controle-asset-"))
        out.mkdir(parents=True, exist_ok=True)
        os.chdir(out)  # aucune commande n'est lancée depuis le dossier de l'asset
    except OSError as e:
        stop(f"Dossier de sortie inutilisable : {e}")

    r = Rapport()
    root, nom = src, src.name
    if archive:
        dest = Path(tempfile.mkdtemp(prefix="asset-", dir=out))  # dossier neuf : rien d'un passage précédent
        try:
            root = extraire(src, dest, r)
        except ValueError as e:  # chemin en ../, chemin absolu ou taille démesurée : signe d'une archive piégée
            r.add(BLOQUANT, "Archive", f"{e} : l'archive n'a pas été extraite, rien n'a été contrôlé")
            terminer(r, src, [], a.mode, out)
        except Exception as e:  # zip chiffré, corrompu ou nom de fichier impossible
            stop(f"Archive illisible ou impossible à extraire ({nettoyer(e, 120)}) : {src.name}")
        nom = src.stem
    elif src.is_file():
        # Fichier seul (prompt, gabarit, script) : contrôlé sur une copie, l'original n'est pas touché.
        root = Path(tempfile.mkdtemp(prefix="asset-", dir=out))
        shutil.copy2(src, root / src.name)
        nom = src.parent.name if src.name == "SKILL.md" else src.stem

    fichiers = lister(root, r)
    skills = find_skills(root)
    plugin = est_plugin(root)
    if not skills and not plugin:
        r.add(INFO, "Structure", "aucun SKILL.md trouvé : contrôles de fichiers seulement")
    labels = {s: (nom if s == root else s.name) for s in skills}
    for s in skills:
        check_skill(s, root, r, labels[s], racine_archive=(s == root and src.is_file()))
    scan_files(root, fichiers, r, a.mode)
    if plugin:
        check_plugin(root, fichiers, r)
    if a.sans_outils:
        r.add(VERIFIER, "Outils", "outils externes désactivés (--sans-outils) : contrôle incomplet")
    else:
        securise(r, "detect-secrets", tool_detect_secrets, root, fichiers, out, r)
        for s in skills:
            securise(r, f"harness-check {labels[s]}", tool_harness, s, labels[s], root, out, r)
            securise(r, f"quality-check {labels[s]}", tool_quality, s, labels[s], root, out, r)
            securise(r, f"skillspector {labels[s]}", tool_skillspector, s, labels[s], root, out, r)
        if plugin and root not in skills:
            # Hooks, serveurs MCP et commandes ne sont vus que si l'outil analyse le plugin entier.
            securise(r, "skillspector plugin", tool_skillspector, root, "plugin", root, out, r,
                     [rel(s, root) for s in skills])
        for nom_outil, v in list(r.outils.items()):
            if v.get("statut") != "ok":
                r.add(VERIFIER, "Outils", f"{nom_outil} : {v.get('statut')} : contrôle incomplet")
    terminer(r, src, skills, a.mode, out)


if __name__ == "__main__":
    main()
