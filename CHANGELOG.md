# Journal des versions

Les versions suivent le [versionnage sémantique](https://semver.org/lang/fr/) : le dernier chiffre pour une correction, le deuxième pour un ajout.

## 0.6.0 — 2026-11-26

### Ajouté

- **Installation en une commande dans Claude Code** : le dépôt est une marketplace (`.claude-plugin/marketplace.json`). `/plugin install partage-securise --marketplace LucaTmt/partage-securise`.
- **Tests** du contrôle sur 17 skills piégées exprès (secrets, texte caché, injection, scripts risqués, chemins personnels, adresses e-mail, liens symboliques, archive qui sort de son dossier, codes de sortie). Ils tournent à chaque push, sous Python 3.9 et 3.13, et la skill s'y contrôle elle-même.
- Dans la skill : sections « Prérequis », « Scripts », « En cas d'erreur » et « Limites » ; description bilingue ; licence et auteur dans l'en-tête.
- Pour un agent qui ne charge pas la skill, la consigne de lire d'abord le motif : il peut tenir au dossier où la skill est rangée, et non à son contenu.
- `SECURITY.md`, `CONTRIBUTING.md`, modèles de tickets « faux positif » et « cas non détecté ».
- README : section « Dépendances » avec une commande pour tout installer, principe de la skill, choix de sécurité, résumé en anglais.
- Le zip pour claude.ai est joint à chaque release.

### Modifié

- La skill se présente comme un contrôle de skills et de plugins. Un fichier seul (prompt, gabarit, script) reste accepté, en cas secondaire : sans `SKILL.md`, seuls detect-secrets, les contrôles internes et la checklist s'appliquent.
- La skill, sa checklist et la documentation ne renvoient plus à un contexte d'entreprise.

### Choix

- La skill ne déclare pas `allowed-tools` : dans Claude Code, ce champ autorise des outils sans demander au lieu de les restreindre. SkillSpector le signale (règle LP3) ; c'est assumé.

## 0.5.0 — 2026-11-22

Première version publiée : la skill `verifier-asset`, ses deux scripts (`installer_outils.py`, `controle.py`) et la checklist « Avant de partager un asset ».
