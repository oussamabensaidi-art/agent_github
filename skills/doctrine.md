---
name: doctrine
reviewer: code
applies: src/Repository/*.php, src/Entity/*.php, migrations/*.php
---
Doctrine ORM.
- QueryBuilder / DQL : valeurs toujours via `setParameter()` (la concaténation relève de la sécurité).
- Pas de `flush()` dans une boucle ; pas de requête dans une boucle (N+1) : jointure ou requête groupée.
- Migration : `down()` implémentée, ou justification ; pas de perte de données silencieuse.
- Entité : contraintes de validation cohérentes avec les colonnes (longueur, nullabilité, unicité).
- Une modification de calcul de numéro ou de compteur (ex. référence suivante) doit rester unique et croissante : un `+ 1` supprimé crée des doublons.
- `find()`, `findBy()`, `findOneBy()` sont paramétrés : ne pas les signaler.
