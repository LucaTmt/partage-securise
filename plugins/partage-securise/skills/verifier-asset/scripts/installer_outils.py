#!/usr/bin/env python3
"""Installe ou met à jour les trois outils de contrôle à leur dernière version publiée.

Usage :
    python3 installer_outils.py              # état : versions installées et dernières versions
    python3 installer_outils.py --installer  # installe ou met à jour ce qui n'est pas à jour

Outils et source de leur dernière version :
  - SkillEvaluator (NVIDIA) : dernière version publiée sur PyPI ;
  - SkillSpector (NVIDIA) : dernière release publiée sur GitHub (NVIDIA/SkillSpector) ;
  - detect-secrets (IBM) : dernière release publiée sur GitHub (IBM/detect-secrets).

Chaque outil est installé avec uv dans son propre environnement isolé, à la version
exacte trouvée (le commit de la release pour les dépôts GitHub), pour que le rapport
dise précisément ce qui a tourné. Sans --installer, le script ne change rien.
Une fois les outils installés, une seule commande lance les trois : controle.py.

Le point de versions lit PyPI et GitHub (rien d'autre n'est envoyé) ; l'installation ne se fait
qu'avec --installer.

Code de sortie : 0 = tout est à jour (ou installation réussie), 1 = installation ou mise à jour
disponible, 2 = échec (uv absent, installation ratée), 3 = dernière version non vérifiable, ou
outil absent dont la dernière version est inconnue (rien n'a pu être installé pour lui).
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

TIMEOUT = 600
OUTILS = {
    "skillevaluator": {"source": "pypi", "paquet": "skillevaluator"},
    "skillspector": {"source": "github", "depot": "NVIDIA/skillspector", "paquet": "skillspector"},
    "detect-secrets": {"source": "github", "depot": "IBM/detect-secrets", "paquet": "detect-secrets"},
}


def get_json(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "verifier-asset"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def run(cmd):
    try:
        p = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=TIMEOUT)
        return p.returncode, p.stdout + p.stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, str(e)


def which(tool):
    # ~/.local/bin : dossier par défaut des outils uv ; shutil.which gère aussi le .exe de Windows.
    return shutil.which(tool) or shutil.which(tool, path=str(Path.home() / ".local" / "bin"))


def version_installee(tool):
    exe = which(tool)
    if not exe:
        return None
    code, txt = run([exe, "--version"])
    m = re.search(r"(\d+\.\d+\.\d+\S*)", txt or "")
    return m.group(1) if m else "inconnue"


def commit_du_tag(depot, tag):
    code, txt = run(["git", "ls-remote", f"https://github.com/{depot}.git", f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}"])
    if code != 0 or not txt.strip():
        return None
    lignes = [l.split() for l in txt.strip().splitlines() if l.strip()]
    deref = [sha for sha, ref in lignes if ref.endswith("^{}")]  # tag annoté : le commit visé
    return deref[0] if deref else lignes[0][0]


def derniere_version(tool):
    """Retourne (version affichée, spécification uv) ou lève une exception."""
    o = OUTILS[tool]
    if o["source"] == "pypi":
        v = get_json(f"https://pypi.org/pypi/{o['paquet']}/json")["info"]["version"]
        return v, f"{o['paquet']}=={v}"
    tag = get_json(f"https://api.github.com/repos/{o['depot']}/releases/latest")["tag_name"]
    sha = commit_du_tag(o["depot"], tag)
    ref = sha or tag
    return tag.lstrip("v"), f"{o['paquet']} @ git+https://github.com/{o['depot']}.git@{ref}"


def meme_version(installee, derniere):
    return installee is not None and installee.lstrip("v") == derniere.lstrip("v")


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    os.chdir(tempfile.gettempdir())  # jamais de commande résolue depuis le dossier courant (asset éventuel)
    ap = argparse.ArgumentParser(description="Installe ou met à jour les outils de contrôle à leur dernière version.")
    ap.add_argument("--installer", action="store_true", help="installer ou mettre à jour ce qui n'est pas à jour")
    a = ap.parse_args()

    uv = shutil.which("uv")
    if not uv:
        print("uv n'est pas installé. C'est lui qui installe chaque outil dans un environnement isolé.\n"
              "Sur Mac : brew install uv   ·   ailleurs : python3 -m pip install --user uv\n"
              "Documentation : https://docs.astral.sh/uv/getting-started/installation/")
        sys.exit(2)
    if not shutil.which("git"):
        print("ATTENTION : git est absent. uv en a besoin pour installer SkillSpector et detect-secrets depuis GitHub :\n"
              "installer git d'abord (sur Mac : xcode-select --install).")

    etat, a_faire, inconnus = [], [], []
    for tool in OUTILS:
        inst = version_installee(tool)
        try:
            derniere, spec = derniere_version(tool)
        except Exception as e:
            inconnus.append((tool, inst, f"{type(e).__name__} : {str(e)[:120]}"))
            etat.append((tool, inst or "absent", "non vérifiable", "échec de la vérification"))
            continue
        if meme_version(inst, derniere):
            statut = "à jour"
        else:
            statut = "à installer" if inst is None else "mise à jour disponible"
            a_faire.append((tool, derniere, spec))
        etat.append((tool, inst or "absent", derniere, statut))

    print("Outil            Installée               Dernière version        État")
    for t, i, d, s in etat:
        print(f"{t:<16} {i:<23} {d:<23} {s}")

    absents_inconnus = [t for t, inst, _ in inconnus if inst is None]
    if inconnus:
        print("\nImpossible de connaître la dernière version de :")
        for t, inst, err in inconnus:
            print(f"  {t} ({'installé : ' + inst if inst else 'absent'}) : {err}")
        print("Causes fréquentes : pas de réseau, PyPI ou GitHub injoignable, limite de 60 requêtes par heure de l'API GitHub.")
        if absents_inconnus:
            print(f"{', '.join(absents_inconnus)} ne peut pas être installé pour l'instant : réessayer plus tard. "
                  "Le contrôle tournera sans, et le rapport l'indiquera.")
        else:
            print("Le contrôle peut continuer avec les versions installées ; le signaler dans le verdict.")
    if not a_faire and not inconnus:
        print("\nTout est à jour.")
    elif not a_faire:
        sys.exit(3)
    elif not a.installer and absents_inconnus:
        print("\nCommandes que --installer lancera :")
        for t, d, spec in a_faire:
            print(f'  uv tool install --force --python 3.13 "{spec}"')
        sys.exit(3)
    elif not a.installer:
        print("\nCommandes que --installer lancera :")
        for t, d, spec in a_faire:
            print(f'  uv tool install --force --python 3.13 "{spec}"')
        print("\nRelancer avec --installer pour les exécuter.")
        sys.exit(1)
    else:
        echecs = 0
        for t, d, spec in a_faire:
            print(f"\nInstallation de {t} {d}…")
            code, txt = run([uv, "tool", "install", "--force", "--python", "3.13", spec])
            if code == 0:
                print(f"  ok, version installée : {version_installee(t)}")
            else:
                echecs += 1
                print(f"  ÉCHEC :\n{txt[-800:]}")
        if echecs:
            sys.exit(2)
        if absents_inconnus:
            sys.exit(3)

    manquants = [t for t in OUTILS if not shutil.which(t) and which(t)]
    if manquants:
        print(f"\nLes outils sont installés dans {Path.home() / '.local' / 'bin'}, qui n'est pas dans le PATH du terminal.\n"
              "controle.py les trouve quand même ; pour les lancer aussi à la main : uv tool update-shell")
    print("\nCommande unique pour tout lancer ensuite :\n"
          f'  python3 "{Path(__file__).resolve().parent / "controle.py"}" <chemin de l\'asset> --mode partager (ou installer)')


if __name__ == "__main__":
    main()
