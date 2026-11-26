# partage-securise

Un plugin qui contrôle une skill, un plugin, un prompt ou tout autre asset avant de le partager, ou une ressource téléchargée avant de l'installer. Il repère les secrets oubliés, les données personnelles, les instructions cachées et les scripts suspects, puis rend un verdict avec les points à corriger. Il fonctionne dans Claude (claude.ai, Cowork, Claude Code) et dans d'autres agents qui lisent le format des skills.

## Sur quoi il s'appuie

| Brique | Ce qu'elle contrôle |
|---|---|
| [SkillEvaluator](https://github.com/NVIDIA/SkillEvaluator) (NVIDIA) | La skill se charge-t-elle dans les principaux agents ? Quelle est sa qualité ? (`harness-check`, `quality-check`) |
| [SkillSpector](https://github.com/NVIDIA/SkillSpector) (NVIDIA) | Instructions cachées, envoi de données, scripts suspects, dépendances vulnérables, score de risque (`--no-llm`) |
| [detect-secrets](https://github.com/IBM/detect-secrets) | Clés d'API, mots de passe et jetons oubliés dans les fichiers (`--no-verify`) |
| La checklist « Avant de partager un asset » | Ce qu'aucun outil ne voit : données personnelles ou confidentielles, sens réel des scripts et des instructions |

Ces trois outils sont open source et facultatifs : sans eux, la skill fait ses propres contrôles et la revue manuelle, et le signale dans le verdict.

## Contenu

Une skill, `verifier-asset` :

- `SKILL.md` : la démarche (cadrer, préparer les outils, lancer le contrôle, interpréter, revue manuelle, verdict) ;
- `scripts/installer_outils.py` : indique quels outils manquent ou ont une mise à jour, puis les installe à leur dernière version ;
- `scripts/controle.py` : la commande unique, qui lance les trois outils, ajoute ses propres contrôles (Python 3 seul) et produit un rapport ;
- `references/checklist.md` : la checklist complète.

## Installer

### Claude Code, en une phrase

Ouvrir Claude Code et lui donner ce prompt :

> Installe la skill verifier-asset depuis https://github.com/LucaTmt/partage-securise. Clone le dépôt avec `git clone --depth 1` dans un dossier temporaire neuf, sans sous-modules. Montre-moi la liste des fichiers de `plugins/partage-securise/skills/verifier-asset` et attends mon accord. Ensuite, copie ce dossier dans `~/.claude/skills/verifier-asset` et supprime le dossier temporaire. N'exécute aucun script du dépôt.

Ouvrir ensuite une nouvelle session : la skill se déclenche seule (« vérifie cette skill avant que je la partage ») ou avec `/verifier-asset`.

### Claude Code, à la main

- **En skill personnelle** : copier `skills/verifier-asset` dans `~/.claude/skills/`. Appel direct : `/verifier-asset`.
- **En plugin** : ce dossier est le plugin. Pour l'essayer : `claude --plugin-dir ./partage-securise`. Appel direct : `/partage-securise:verifier-asset`.

### claude.ai et Cowork

Zipper le dossier `skills/verifier-asset` (le zip doit contenir le dossier `verifier-asset/` lui-même), puis l'importer dans Paramètres, Capacités.

### IBM Bob

Bob n'installe pas les plugins de Claude Code, mais il lit le format des skills : on installe donc la skill seule, sans le plugin. Bob charge les skills depuis `~/.bob/skills/` (tous les projets) ou depuis `.bob/skills/` à la racine d'un projet.

Donner ce prompt à Bob, dans un mode qui l'autorise à lancer des commandes :

> Installe la skill verifier-asset depuis https://github.com/LucaTmt/partage-securise. Clone le dépôt avec `git clone --depth 1` dans un dossier temporaire neuf, sans sous-modules. Montre-moi la liste des fichiers de `plugins/partage-securise/skills/verifier-asset` et attends mon accord. Ensuite, copie ce dossier dans `~/.bob/skills/verifier-asset` et supprime le dossier temporaire. N'exécute aucun script du dépôt.

Ou à la main, dans un terminal :

```bash
git clone --depth 1 https://github.com/LucaTmt/partage-securise.git /tmp/partage-securise
mkdir -p ~/.bob/skills
cp -R /tmp/partage-securise/plugins/partage-securise/skills/verifier-asset ~/.bob/skills/
```

Dans une nouvelle conversation, demander ensuite « vérifie cette skill avant que je la partage ». Bob active la skill de lui-même d'après la demande et demande l'autorisation avant de le faire. L'onglet Skills de ses réglages montre si elle a bien été trouvée.

### Autres agents

Les agents qui lisent le format des skills les chargent depuis un dossier qui leur est propre : il suffit d'y copier le dossier `skills/verifier-asset`.

## Utilisation

Demander simplement : « vérifie cette skill avant que je la partage » ou « est-ce que je peux installer ce plugin ? », en donnant le dossier, le zip ou le lien. Avec un lien, l'agent télécharge l'asset dans un dossier temporaire, sans rien exécuter ni installer, et supprime ce dossier après le verdict. L'agent rend un verdict et les points à corriger.

## Installer les outils, puis une seule commande

Il faut [uv](https://docs.astral.sh/uv/) (sur Mac : `brew install uv`), qui installe chaque outil dans son propre environnement isolé.

**1. Faire le point** (ne change rien) :

```bash
python3 partage-securise/skills/verifier-asset/scripts/installer_outils.py
```

| Outil | Où le script cherche la dernière version |
|---|---|
| SkillEvaluator (NVIDIA) | dernière version publiée sur PyPI |
| SkillSpector (NVIDIA) | dernière release du dépôt GitHub NVIDIA/SkillSpector |
| detect-secrets | dernière release du dépôt GitHub IBM/detect-secrets |

Il affiche pour chacun la version installée, la dernière version et les commandes `uv tool install` qu'il lancerait. Ce point lit PyPI et GitHub, sans rien envoyer de l'asset. Pour les dépôts GitHub, il installe le commit exact de la release ; le rapport du contrôle note la version de chaque outil.

**2. Installer ou mettre à jour** :

```bash
python3 partage-securise/skills/verifier-asset/scripts/installer_outils.py --installer
```

À relancer de temps en temps pour récupérer les nouvelles versions : les outils ne se mettent pas à jour seuls.

**3. Contrôler un asset, avec une seule commande** qui lance les trois outils et les contrôles internes :

```bash
python3 partage-securise/skills/verifier-asset/scripts/controle.py ./mon-asset --mode partager
```

L'asset peut être un dossier, une archive `.zip`, `.skill` ou `.plugin`, ou un fichier seul (prompt, gabarit, script). Codes de sortie : 0 = rien relevé, 1 = points à vérifier (dont un outil qui n'a pas tourné), 2 = au moins un point bloquant, 3 = contrôle impossible.

En pratique, il suffit de demander à l'agent « vérifie cette skill » : la skill fait le point sur les outils, propose l'installation et attend votre accord, puis lance le contrôle.

Le rapport indique la version de chaque outil, car une nouvelle version peut changer les résultats sur un même asset.

Sur un poste professionnel, vérifier d'abord les règles de votre organisation sur l'installation de logiciels open source. SkillEvaluator ne teste pas le chargement dans IBM Bob : la skill rappelle les règles de Bob à vérifier à la main.

## Sources

- [OWASP Top 10 for Agentic Applications 2026](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/)
- [IBM Bob : skills](https://bob.ibm.com/docs/ide/features/skills)
