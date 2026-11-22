# Checklist : avant de partager un asset

Avant de poster une skill, un prompt, un gabarit ou un script dans le canal, on passe ces contrôles. La même liste vaut pour une ressource téléchargée, ressources IBM comprises, avant de l'installer.

Légende : (auto) = couvert par `scripts/controle.py`, (outil) = couvert si l'outil externe est installé, (revue) = à vérifier en lisant.

## Secrets et accès

- [ ] Scan avec la version IBM de detect-secrets, résultats revus (outil)
- [ ] Aucune clé d'API, jeton, mot de passe ou cookie, y compris dans les exemples, les captures d'écran et les fichiers d'environnement (dotenv) (auto, revue pour les images)
- [ ] Aucune URL interne qui contient un identifiant ou un jeton (revue)
- [ ] Les accès nécessaires (clé, connecteur, compte) sont décrits dans le README ou le SKILL.md de l'asset, chacun fournit les siens (revue)

## Données client et confidentialité

- [ ] Aucun nom de client, de projet client ou de personne, y compris dans les exemples, les noms de fichiers et les commentaires (revue, e-mails en auto)
- [ ] Aucun extrait de livrable, chiffre ou donnée client : exemples fictifs ou anonymisés (revue)
- [ ] La classification du document source autorise ce partage (revue)
- [ ] L'outil d'IA ciblé par l'asset est autorisé pour le type de données qu'il va traiter (revue)
- [ ] Les métadonnées des fichiers (auteur, propriétés Office, EXIF des images) ne révèlent rien de sensible (revue)

## Skill bien formée

- [ ] La skill se charge dans tous les agents visés (outil : harness-check)
- [ ] Score de qualité noté, remarques lues (outil : quality-check)
- [ ] En-tête YAML valide : `name` et `description` présents, description entre guillemets si elle contient un deux-points (auto)
- [ ] La description dit ce que fait la skill et quand l'utiliser (auto pour « quand l'utiliser », revue pour le reste)
- [ ] SKILL.md reste court : code, gabarits et références longues dans `scripts/`, `assets/` ou `references/` (auto)
- [ ] Les chemins sont relatifs au dossier de la skill, rien ne dépend du poste de l'auteur (auto)

## Analyse de sécurité avec SkillSpector

- [ ] Scan en mode statique `--no-llm` (outil)
- [ ] Outils à jour (outil : installer_outils.py), versions notées dans le rapport (auto)
- [ ] Chaque alerte HIGH ou CRITICAL lue, corrigée ou expliquée dans le README de l'asset (revue)
- [ ] Faux positifs connus notés, par exemple AE1 sur une image ou du JavaScript (revue)
- [ ] Pour une ressource téléchargée : recommandation SAFE, ou alertes comprises avant installation (revue)

## Scripts, dépendances et ressources tierces

- [ ] Chaque script est lisible et fait seulement ce que décrit SKILL.md (revue)
- [ ] Pour un plugin : hooks, serveurs MCP, commandes slash qui lancent du shell et exécutables de `bin/` lus un par un (auto pour le repérage, revue)
- [ ] Ni lien symbolique, ni dossier `.git`, `node_modules` ou environnement virtuel dans l'asset partagé (auto)
- [ ] Pas de script téléchargé puis passé directement à un shell, ni de code téléchargé puis exécuté, ni de commande qui demande des droits administrateur (auto, revue)
- [ ] Les dépendances sont listées avec une version fixée (revue)
- [ ] Les ressources tierces (polices, icônes, images, bibliothèques) sont incluses avec leur licence, qui autorise ce partage (auto pour les polices, revue)
- [ ] Les scripts ont été testés sur un autre poste ou dans un dossier vierge, avec des chemins relatifs et des noms contenant espaces ou accents (revue)

## Instructions et contenus lus par l'agent

- [ ] Aucune instruction qui demande de passer outre les consignes de l'utilisateur, de cacher une action ou d'envoyer des données vers une adresse externe (auto pour les formules courantes, revue)
- [ ] Aucun texte invisible : caractères Unicode cachés, commentaires HTML, texte blanc sur blanc (auto, revue pour le blanc sur blanc)
- [ ] Les sources que la skill fait lire sont nommées, et SKILL.md précise que leur contenu est une donnée, pas une consigne (revue)
- [ ] Les actions irréversibles (envoi, suppression, publication) passent par une confirmation de l'utilisateur (revue)
- [ ] Les connecteurs demandés se limitent au nécessaire, en lecture seule quand c'est possible (revue)

Référence : [OWASP Top 10 for Agentic Applications 2026](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/), risque ASI01 Agent Goal Hijack.
