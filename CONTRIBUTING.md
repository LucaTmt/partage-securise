# Contribuer

Merci de vouloir améliorer `partage-securise`. Un faux positif ou un piège non détecté, signalé avec un exemple minimal, est aussi utile qu'une modification du code.

## Signaler

- Faux positif ou cas non détecté : ouvrir un ticket avec le modèle correspondant.
- Faille de sécurité : jamais en public, voir [SECURITY.md](SECURITY.md).
- Ne jamais coller un vrai secret, une donnée client ou une donnée personnelle dans un ticket : un exemple factice du même format suffit.

## Modifier le code

Les scripts de la skill (`plugins/partage-securise/skills/verifier-asset/scripts/`) suivent trois règles :

- Python 3.9 ou plus récent, bibliothèque standard seule : faire tourner le contrôle ne demande aucune dépendance.
- Rien n'est envoyé en ligne pendant le contrôle, et aucun script de l'asset contrôlé n'est exécuté.
- Une valeur de secret n'est jamais affichée : fichier, ligne et type suffisent.

### Lancer les tests

Depuis la racine du dépôt :

```bash
python3 -m unittest discover -s tests -v
```

Les tests fabriquent des skills piégées dans un dossier temporaire et vérifient que chaque piège est attrapé. Ils tournent aussi à chaque push, sous Python 3.9 et 3.13.

### Ajouter une détection

1. Écrire d'abord le test : une skill qui contient le piège, et le point attendu dans le rapport (catégorie et niveau).
2. Vérifier que le test échoue, puis ajouter la détection dans `controle.py`.
3. Vérifier qu'une skill propre ne déclenche toujours rien de bloquant.

Un faux secret ne s'écrit jamais en clair dans un test : l'assembler à l'exécution (`"AKIA" + "…"`), pour que le dépôt n'en contienne aucun.

### Avant de proposer une modification

- Les tests passent.
- La skill se contrôle elle-même sans point bloquant :

  ```bash
  python3 plugins/partage-securise/skills/verifier-asset/scripts/controle.py plugins/partage-securise/skills/verifier-asset --mode partager --sans-outils
  ```

- Le `CHANGELOG.md` décrit le changement.
