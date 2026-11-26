# Sécurité

`partage-securise` est un outil de sécurité : une faille dans le contrôle, ou un piège qu'il laisse passer, compte autant qu'un bogue ordinaire.

## Signaler une faille

Pour une faille qui pourrait servir à quelqu'un de malveillant (une façon de faire passer un secret ou une instruction cachée sans alerte, un moyen de faire exécuter du code par le contrôle, une archive qui écrit hors de son dossier…), **ne pas ouvrir de ticket public**. Utiliser le signalement privé de GitHub : onglet **Security**, puis **Report a vulnerability**.

Indiquer la version concernée, un exemple minimal qui reproduit le problème, et ce que le contrôle aurait dû signaler. Ne jamais joindre un vrai secret : un exemple factice du même format suffit.

## Signaler un cas non dangereux

Un faux positif, ou un cas non détecté sans enjeu d'exploitation, peut faire l'objet d'un ticket public, avec les modèles proposés.

## Versions suivies

Seule la dernière version publiée reçoit des corrections.

| Version | Corrections |
|---|---|
| 0.6.x | oui |
| antérieures | non |

## Ce que l'outil ne promet pas

Un verdict « prêt » aide à décider ; il ne garantit pas l'absence de problème. Les limites connues sont décrites dans la section « Limites » de [`SKILL.md`](plugins/partage-securise/skills/verifier-asset/SKILL.md).
