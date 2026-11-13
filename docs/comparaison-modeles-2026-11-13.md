# Comparaison des modèles — banc vrai GitHub (30 PR, code fictif)

| Indicateur | Qwen3-14B | Qwen3-Coder-30B-A3B | Qwen3-Coder-Next |
|---|---|---|---|
| Verdicts conformes | **30/30** | **29/30** | **29/30** |
| Défauts trouvés **par l'IA** (hors outils et CI) | **14/15** | **11/15** | **14/15** |
| Défauts trouvés par les contrôles déterministes | 6/6 | 6/6 | 6/6 |
| PR propres sans remarque majeure | **7/8** | **8/8** | **6/8** |
| PR propres sans aucune remarque | 7/8 | 8/8 | 4/8 |
| Autres remarques de l'IA (à juger) | 7 (dont 7 majeures ou critiques) | 6 (dont 6 majeures ou critiques) | 10 (dont 7 majeures ou critiques) |
| Durée d'analyse p50 / p95 | 26 s / 56 s | 12 s / 69 s | 13 s / 86 s |
| Lots en échec (erreur du modèle) | 0/29 | 0/29 | 0/29 |
| Analyses en erreur | 0 | 0 | 0 |
| Coût (30 PR) | interne | 0.009 $ | 0.008 $ |

## Défauts attendus de l'IA : détail

| Cas | Défaut | Qwen3-14B | Qwen3-Coder-30B-A3B | Qwen3-Coder-Next |
|---|---|---|---|---|
| `D1-sql-injection` | injection SQL (concaténation) | ✅ | ✅ | ✅ |
| `D2-acces-suppression` | route de suppression sans contrôle de droits | ✅ | ✅ | ✅ |
| `D3-dump-oublie` | dump() oublié | ✅ | ✅ | ✅ |
| `D5-montant-flottant` | flottant + troncature au lieu d'arrondi | ✅ | ❌ | ✅ |
| `D6-reference-dupliquee` | référence suivante non incrémentée (doublon) | ✅ | ❌ | ✅ |
| `D7-xss-raw` | |raw sur une donnée saisie (XSS) | ✅ | ✅ | ✅ |
| `X1-redirection-ouverte` | redirection ouverte (URL fournie par l'utilisateur) | ✅ | ✅ | ✅ |
| `X2-csrf-retire` | vérification CSRF supprimée | ❌ | ❌ | ✅ |
| `X3-droit-abaisse` | modification ouverte aux lecteurs (ROLE_USER) | ✅ | ✅ | ✅ |
| `X4-donnees-dans-les-logs` | données du client écrites dans les logs | ✅ | ✅ | ✅ |
| `X5-exception-avalee` | exception avalée (catch vide), succès affiché à tort | ✅ | ✅ | ✅ |
| `X6-comparaison-hmac` | signature comparée avec == au lieu de hash_equals() | ✅ | ✅ | ✅ |
| `X7-unserialize` | unserialize() sur le corps de la requête | ✅ | ✅ | ✅ |
| `X8-logique-sans-test` | nouvelle logique métier sans test | ✅ | ❌ | ❌ |
| `X9-dql-concatene` | DQL construite par concaténation (injection) | ✅ | ✅ | ✅ |

## Verdicts non conformes

- **Qwen3-14B** : aucun
- **Qwen3-Coder-30B-A3B** : `X8-logique-sans-test` → CONTROLES_SATISFAITS
- **Qwen3-Coder-Next** : `X8-logique-sans-test` → CONTROLES_SATISFAITS

## Autres remarques de l'IA (hors défauts attendus)

### Qwen3-14B
- `D2-acces-suppression` (defect) **critical** `templates/contract/show.html.twig:24` — Manque de jeton CSRF dans le formulaire de suppression
- `C1-export-csv` (clean) **major** `src/Controller/ContractController.php:48` — Utilisation de findBy sans QueryBuilder
- `S1-phpstan-methode` (defect) **major** `src/Controller/ContractController.php:47` — Dépendances non injectées
- `S2-ci-en-echec` (defect) **major** `src/Service/PremiumCalculator.php:26` — Logique de plafonnement incorrecte
- `S4-style` (defect) **major** `src/Service/PremiumCalculator.php:29` — Nouvelle logique métier sans test unitaire
- `X1-redirection-ouverte` (defect) **major** `src/Controller/ContractController.php:123` — Manque de vérification des droits ROLE_GESTIONNAIRE
- `X7-unserialize` (defect) **major** `src/Controller/ContractController.php:45` — Manque de test pour la logique d'import

### Qwen3-Coder-30B-A3B
- `D2-acces-suppression` (defect) **major** `templates/contract/show.html.twig:23` — Absence de jeton CSRF dans le formulaire de suppression
- `D4-secret-en-dur` (defect) **critical** `src/Service/CrmNotifier.php:12` — URL du CRM en dur
- `D4-secret-en-dur` (defect) **critical** `src/Service/CrmNotifier.php:22` — Clé API du CRM en dur
- `S1-phpstan-methode` (defect) **major** `src/Controller/ContractController.php:44` — Absence de vérification des droits d'accès pour l'export JSON
- `S1-phpstan-methode` (defect) **major** `src/Controller/ContractController.php:47` — Utilisation potentielle d'une variable non définie
- `S2-ci-en-echec` (defect) **critical** `src/Service/PremiumCalculator.php:26` — Logique inversée dans le plafonnement de la prime

### Qwen3-Coder-Next
- `C1-export-csv` (clean) **major** `src/Controller/ContractController.php:48` — Accès direct à un repository non injecté
- `C1-export-csv` (clean) **major** `tests/Functional/ContractControllerTest.php:82` — Test fragile sur le nombre de lignes d'export
- `C3-filtre-twig-money` (clean) **minor** `src/Twig/MoneyExtension.php:18` — Type hint manquant sur la méthode format
- `S1-phpstan-methode` (defect) **critical** `src/Controller/ContractController.php:43` — Route exposant des données sensibles sans autorisation explicite
- `S2-ci-en-echec` (defect) **major** `src/Service/PremiumCalculator.php:26` — Plafonnement incorrect : utilisation de min au lieu de max
- `S3-dependance-vulnerable` (defect) **critical** `composer.json:13` — Version de Guzzle non vérifiée pour vulnérabilités connues
- `S3-dependance-vulnerable` (defect) **major** `composer.json:37` — Désactivation de la vérification des dépendances insegures
- `S4-style` (defect) **minor** `src/Service/PremiumCalculator.php:29` — Typage manquant pour le paramètre $premiumCents
- `S5-propre-php` (clean) **minor** `src/Twig/MoneyExtension.php:18` — Type hint manquant sur le paramètre
- `K4-test-supplementaire` (clean) **major** `tests/Unit/PremiumCalculatorTest.php:22` — Test manquant pour la logique de prime minimale multirisque

## Lecture (relecture manuelle des « autres remarques »)

| | Qwen3-14B | Qwen3-Coder-30B-A3B | Qwen3-Coder-Next |
|---|---|---|---|
| Remarques de l'IA au total | 21 | 17 | 24 |
| Fausses alertes | 3 | 2 (+1 discutable) | 7 |
| Fausses alertes sur les PR propres | 1 | 0 | 5 |
| Défauts manqués par l'IA | 1 (CSRF retiré, rattrapé par la CI) | 4 | 1 (logique sans test) |

- **Qwen3-14B (Calipso)** : meilleur équilibre. Seul modèle à 30/30 verdicts ; le seul défaut qu'il manque
  (vérification CSRF supprimée : une suppression pure, sans ligne ajoutée à commenter) est bloqué par la CI.
- **Qwen3-Coder-30B-A3B** : le plus silencieux (aucune remarque sur les 8 PR propres) mais manque 4 défauts,
  dont deux bogues de calcul et l'absence de test.
- **Qwen3-Coder-Next** : trouve autant de défauts que le 14B et est le seul à voir le CSRF retiré, mais
  commente 4 PR propres sur 8 (typage « manquant » alors qu'il est présent, tests jugés fragiles).
- Fausses alertes communes : droits ou dépendances « manquants » alors qu'ils sont déclarés ailleurs dans la
  classe (constructeur, attribut de méthode) : le contexte ne donne aujourd'hui que l'en-tête du fichier.

Limites : une seule exécution par modèle (les formulations varient d'une exécution à l'autre) ; code fictif
écrit par l'équipe ; les deux modèles Coder ont été servis par OpenRouter (versions non quantifiées), le 14B
par le serveur Calipso (AWQ) ; durées non comparables entre les deux infrastructures.
