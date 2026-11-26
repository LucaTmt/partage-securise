# partage-securise

Avant de partager une skill, un plugin ou un prompt, ou avant d'installer une ressource téléchargée, on vérifie qu'il ne contient ni secret oublié, ni donnée personnelle, ni instruction cachée, ni script suspect. Ce dépôt fournit la skill **`verifier-asset`**, qui fait ce contrôle et rend un verdict avec les points à corriger.

Elle fonctionne dans Claude (claude.ai, Cowork, Claude Code) et dans d'autres agents qui lisent le format des skills.

## Installer

- **Claude Code** : un prompt suffit, il est dans [Installer › Claude Code, en une phrase](plugins/partage-securise/README.md#claude-code-en-une-phrase).
- **claude.ai, Cowork et autres agents** : voir la section [Installer](plugins/partage-securise/README.md#installer) du plugin.

Une fois installée, il suffit de demander : « vérifie cette skill avant que je la partage ».

## Contenu du dépôt

| Chemin | Rôle |
|---|---|
| [`plugins/partage-securise/`](plugins/partage-securise/) | le plugin, avec son [README](plugins/partage-securise/README.md) : fonctionnement, installation, outils |
| [`plugins/partage-securise/skills/verifier-asset/`](plugins/partage-securise/skills/verifier-asset/) | la skill : démarche, scripts de contrôle et [checklist](plugins/partage-securise/skills/verifier-asset/references/checklist.md) |
| [`distribution/`](distribution/) | une note d'installation au format texte, jointe aux paquets distribués |

## Licence

[MIT](LICENSE) : chacun peut utiliser, modifier et redistribuer ce dépôt, à condition de conserver la mention de copyright et le texte de la licence.
