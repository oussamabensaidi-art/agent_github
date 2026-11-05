# Règles d'équipe Calipso — revue de code PHP / Symfony

Ces règles sont injectées dans le prompt de revue. Les modifier ici suffit,
sans changer de code.

## Sécurité (critique)
- Aucune requête SQL/DQL construite par concaténation de données utilisateur :
  paramètres liés obligatoires.
- Aucun secret, mot de passe, clé d'API ou jeton en dur dans le code.
- Toute route qui modifie des données vérifie l'authentification et les droits
  (`#[IsGranted]`, voters, ou contrôle explicite).
- Pas de `unserialize()`, `eval()`, `shell_exec()`, `exec()` sur des entrées externes.
- Sortie Twig : pas de `|raw` sur une donnée utilisateur.
- Les signatures HMAC se comparent avec `hash_equals()`, jamais `==`.

## Fiabilité (majeur)
- Pas de `dd()`, `dump()`, `var_dump()`, `print_r()` oubliés.
- Les appels HTTP sortants ont un timeout et gèrent l'erreur.
- Les exceptions ne sont pas avalées silencieusement (`catch {}` vide).
- Les migrations Doctrine sont réversibles (`down()` implémenté) ou le justifient.
- Données personnelles (assurés, IBAN, emails) jamais écrites dans les logs.

## Qualité (mineur)
- `declare(strict_types=1);` en tête des nouveaux fichiers PHP.
- Typage des paramètres et retours ; pas de `mixed` sans raison.
- Injection de dépendances par constructeur, pas d'accès au conteneur.
- Noms explicites ; méthodes courtes et à responsabilité unique.

## Tests
- Toute nouvelle logique métier (service, calcul, règle) est accompagnée d'un test.
- Un correctif de bug ajoute un test qui reproduit le bug.
