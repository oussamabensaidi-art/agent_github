# Comparaison des modèles — banc vrai GitHub (30 PR, code fictif)

| Indicateur | 14B sans compétences | 14B + relecteurs spécialisés |
|---|---|---|
| Verdicts conformes | **30/30** | **30/30** |
| Défauts trouvés **par l'IA** (hors outils et CI) | **14/15** | **15/15** |
| Défauts trouvés par les contrôles déterministes | 6/6 | 6/6 |
| PR propres sans remarque majeure | **7/8** | **8/8** |
| PR propres sans aucune remarque | 7/8 | 8/8 |
| Autres remarques de l'IA (à juger) | 7 (dont 7 majeures ou critiques) | 7 (dont 6 majeures ou critiques) |
| Durée d'analyse p50 / p95 | 26 s / 56 s | 30 s / 69 s |
| Lots en échec (erreur du modèle) | 0/29 | 0/55 |
| Analyses en erreur | 0 | 0 |
| Coût (30 PR) | interne | interne |

## Défauts attendus de l'IA : détail

| Cas | Défaut | 14B sans compétences | 14B + relecteurs spécialisés |
|---|---|---|---|
| `D1-sql-injection` | injection SQL (concaténation) | ✅ | ✅ |
| `D2-acces-suppression` | route de suppression sans contrôle de droits | ✅ | ✅ |
| `D3-dump-oublie` | dump() oublié | ✅ | ✅ |
| `D5-montant-flottant` | flottant + troncature au lieu d'arrondi | ✅ | ✅ |
| `D6-reference-dupliquee` | référence suivante non incrémentée (doublon) | ✅ | ✅ |
| `D7-xss-raw` | |raw sur une donnée saisie (XSS) | ✅ | ✅ |
| `X1-redirection-ouverte` | redirection ouverte (URL fournie par l'utilisateur) | ✅ | ✅ |
| `X2-csrf-retire` | vérification CSRF supprimée | ❌ | ✅ |
| `X3-droit-abaisse` | modification ouverte aux lecteurs (ROLE_USER) | ✅ | ✅ |
| `X4-donnees-dans-les-logs` | données du client écrites dans les logs | ✅ | ✅ |
| `X5-exception-avalee` | exception avalée (catch vide), succès affiché à tort | ✅ | ✅ |
| `X6-comparaison-hmac` | signature comparée avec == au lieu de hash_equals() | ✅ | ✅ |
| `X7-unserialize` | unserialize() sur le corps de la requête | ✅ | ✅ |
| `X8-logique-sans-test` | nouvelle logique métier sans test | ✅ | ✅ |
| `X9-dql-concatene` | DQL construite par concaténation (injection) | ✅ | ✅ |

## Verdicts non conformes

- **14B sans compétences** : aucun
- **14B + relecteurs spécialisés** : aucun

## Autres remarques de l'IA (hors défauts attendus)

### 14B sans compétences
- `D2-acces-suppression` (defect) **critical** `templates/contract/show.html.twig:24` — Manque de jeton CSRF dans le formulaire de suppression
- `C1-export-csv` (clean) **major** `src/Controller/ContractController.php:48` — Utilisation de findBy sans QueryBuilder
- `S1-phpstan-methode` (defect) **major** `src/Controller/ContractController.php:47` — Dépendances non injectées
- `S2-ci-en-echec` (defect) **major** `src/Service/PremiumCalculator.php:26` — Logique de plafonnement incorrecte
- `S4-style` (defect) **major** `src/Service/PremiumCalculator.php:29` — Nouvelle logique métier sans test unitaire
- `X1-redirection-ouverte` (defect) **major** `src/Controller/ContractController.php:123` — Manque de vérification des droits ROLE_GESTIONNAIRE
- `X7-unserialize` (defect) **major** `src/Controller/ContractController.php:45` — Manque de test pour la logique d'import

### 14B + relecteurs spécialisés
- `D2-acces-suppression` (defect) **critical** `templates/contract/show.html.twig:24` — Manque de protection CSRF sur le formulaire de suppression
- `D4-secret-en-dur` (defect) **major** `src/Service/CrmNotifier.php:21` — Appel HTTP sans gestion des erreurs
- `S1-phpstan-methode` (defect) **critical** `src/Controller/ContractController.php:43` — Accès non contrôlé à un endpoint sensible
- `S1-phpstan-methode` (defect) **major** `src/Controller/ContractController.php:44` — Nouvelle logique métier sans test
- `S2-ci-en-echec` (defect) **major** `src/Service/PremiumCalculator.php:26` — Logique inversée du plafonnement
- `S4-style` (defect) **major** `src/Service/PremiumCalculator.php:30` — Nouvelle logique métier sans test
- `X1-redirection-ouverte` (defect) **minor** `src/Controller/ContractController.php:123` — Utilisation d'une URL brute au lieu d'une route nommée

## Lecture (relecture manuelle des « autres remarques »)

| | Sans compétences | Avec relecteurs spécialisés |
|---|---|---|
| Défauts attendus trouvés par l'IA | 14/15 | **15/15** (CSRF supprimé trouvé) |
| PR propres commentées | 1/8 | **0/8** |
| Fausses alertes | 3 (« findBy sans QueryBuilder », « dépendances non injectées », droits « manquants » sur une action protégée) | **1** (accès « non contrôlé » à une route en lecture déjà protégée par la classe) |
| Remarques utiles non prévues par les cas | 4 | 6 (dont « appel HTTP sans gestion d'erreur », règle d'équipe) |
| Passages du modèle | 29 | 55 (×1,9) |
| Durée d'analyse p50 / p95 | 26 s / 56 s | 30 s / 69 s |
| Durée totale p95 (30 PR en même temps, 3 workers) | 5 min 06 | 5 min 59 |

Les trois fausses alertes visées par les fiches « ne pas signaler » ont disparu. Le prix : presque deux
fois plus d'appels au modèle ; l'analyse elle-même ne s'allonge que de quelques secondes (passages en
parallèle), mais la file s'allonge quand beaucoup de PR arrivent ensemble.

Limite : une seule exécution par configuration ; code fictif écrit par l'équipe.
