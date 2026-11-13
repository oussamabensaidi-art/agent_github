# Banc vrai GitHub — série `m14b`

Généré le 2026-11-13T11:23:50 UTC · 30 PR ouvertes en 5.3 s sur 3 dépôts · 3 worker(s)

## Synthèse

- Verdicts conformes : **30/30**
- Défauts attendus détectés : **20/21**
- PR propres sans remarque majeure ou critique : **7/8**
- Check GitHub conforme au verdict : **30/30**
- Email d'alerte conforme (envoyé si et seulement si bloquante) : **30/30**
- Secrets des cas retrouvés dans le journal de l'agent : **0**
- Durée totale (attente comprise) : p50 **171.3 s**, p95 **306.0 s**, max 328.0 s
- Attente en file : p50 138.6 s, p95 274.1 s · exécution : p50 26.1 s, p95 56.5 s
- Lots en échec : 0 / 29

## Par PR

| Cas | PR | Verdict | Attendu | Détection | Autres remarques | Check | Mail | Attente | Total |
|---|---|---|---|---|---|---|---|---:|---:|
| `D1-sql-injection` | [project_test_1#24](https://github.com/test-agent-revue/project_test_1/pull/24) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ injection SQL (concaténation) | — | neutral | non | 192.2 s | 213.4 s |
| `D2-acces-suppression` | [project_test_1#29](https://github.com/test-agent-revue/project_test_1/pull/29) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ route de suppression sans contrôle de droits | critical | neutral | non | 289.9 s | 328.0 s |
| `D3-dump-oublie` | [project_test_2#24](https://github.com/test-agent-revue/project_test_2/pull/24) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ dump() oublié | — | neutral | non | 142.3 s | 166.3 s |
| `D4-secret-en-dur` | [project_test_2#26](https://github.com/test-agent-revue/project_test_2/pull/26) | ✅ BLOQUANTE | BLOQUANTE | ✅ clé d'API en dur (détection déterministe) | major, major, major | failure | oui | 255.6 s | 311.2 s |
| `D5-montant-flottant` | [project_test_3#19](https://github.com/test-agent-revue/project_test_3/pull/19) | ✅ BLOQUANTE | A_VERIFIER / BLOQUANTE | ✅ flottant + troncature au lieu d'arrondi | critical | failure | oui | 109.3 s | 135.3 s |
| `D6-reference-dupliquee` | [project_test_3#15](https://github.com/test-agent-revue/project_test_3/pull/15) | ✅ BLOQUANTE | A_VERIFIER / BLOQUANTE | ✅ référence suivante non incrémentée (doublon) | critical | failure | oui | 37.3 s | 61.0 s |
| `D7-xss-raw` | [project_test_1#23](https://github.com/test-agent-revue/project_test_1/pull/23) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ |raw sur une donnée saisie (XSS) | — | neutral | non | 198.7 s | 223.9 s |
| `D8-secret-description` | [project_test_3#16](https://github.com/test-agent-revue/project_test_3/pull/16) | ✅ BLOQUANTE | BLOQUANTE | ✅ mot de passe dans la description de la PR | — | failure | oui | 0.6 s | 37.7 s |
| `C1-export-csv` | [project_test_2#23](https://github.com/test-agent-revue/project_test_2/pull/23) | ✅ A_VERIFIER | CONTROLES_SATISFAITS / A_VERIFIER | — | major | neutral | non | 60.7 s | 111.0 s |
| `C2-liste-pluriel` | [project_test_3#22](https://github.com/test-agent-revue/project_test_3/pull/22) | ✅ CONTROLES_SATISFAITS | CONTROLES_SATISFAITS / A_VERIFIER | — | — | success | non | 279.7 s | 299.7 s |
| `C3-filtre-twig-money` | [project_test_1#27](https://github.com/test-agent-revue/project_test_1/pull/27) | ✅ CONTROLES_SATISFAITS | CONTROLES_SATISFAITS / A_VERIFIER | — | — | success | non | 62.7 s | 114.4 s |
| `E1-gros-fichier` | [project_test_2#19](https://github.com/test-agent-revue/project_test_2/pull/19) | ✅ ANALYSE_INCOMPLETE | ANALYSE_INCOMPLETE | — | — | action_required | non | 56.5 s | 62.9 s |
| `S1-phpstan-methode` | [project_test_1#19](https://github.com/test-agent-revue/project_test_1/pull/19) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ méthode inexistante (PHPStan) | major | neutral | non | 0.5 s | 38.2 s |
| `S2-ci-en-echec` | [project_test_2#25](https://github.com/test-agent-revue/project_test_2/pull/25) | ✅ BLOQUANTE | BLOQUANTE | ✅ tests en échec dans la CI | major | failure | oui | 133.8 s | 175.5 s |
| `S3-dependance-vulnerable` | [project_test_3#17](https://github.com/test-agent-revue/project_test_3/pull/17) | ✅ BLOQUANTE | BLOQUANTE | ✅ dépendance vulnérable (composer audit) | — | failure | oui | 57.0 s | 87.0 s |
| `S4-style` | [project_test_1#26](https://github.com/test-agent-revue/project_test_1/pull/26) | ✅ A_VERIFIER | CONTROLES_SATISFAITS / A_VERIFIER | ✅ style non conforme (PHP-CS-Fixer) | major | neutral | non | 110.7 s | 142.6 s |
| `S5-propre-php` | [project_test_2#18](https://github.com/test-agent-revue/project_test_2/pull/18) | ✅ CONTROLES_SATISFAITS | CONTROLES_SATISFAITS / A_VERIFIER | — | — | success | non | 227.6 s | 260.1 s |
| `X1-redirection-ouverte` | [project_test_1#20](https://github.com/test-agent-revue/project_test_1/pull/20) | ✅ BLOQUANTE | A_VERIFIER / BLOQUANTE | ✅ redirection ouverte (URL fournie par l'utilisateur) | major, critical | failure | oui | 0.5 s | 57.6 s |
| `X2-csrf-retire` | [project_test_2#22](https://github.com/test-agent-revue/project_test_2/pull/22) | ✅ BLOQUANTE | A_VERIFIER / BLOQUANTE | ❌ vérification CSRF supprimée | critical | failure | oui | 166.9 s | 228.1 s |
| `X3-droit-abaisse` | [project_test_3#18](https://github.com/test-agent-revue/project_test_3/pull/18) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ modification ouverte aux lecteurs (ROLE_USER) | — | neutral | non | 175.2 s | 198.9 s |
| `X4-donnees-dans-les-logs` | [project_test_1#28](https://github.com/test-agent-revue/project_test_1/pull/28) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ données du client écrites dans les logs | — | neutral | non | 267.3 s | 290.0 s |
| `X5-exception-avalee` | [project_test_2#20](https://github.com/test-agent-revue/project_test_2/pull/20) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ exception avalée (catch vide), succès affiché à tort | — | neutral | non | 114.1 s | 133.8 s |
| `X6-comparaison-hmac` | [project_test_3#20](https://github.com/test-agent-revue/project_test_3/pull/20) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ signature comparée avec == au lieu de hash_equals() | — | neutral | non | 223.8 s | 242.6 s |
| `X7-unserialize` | [project_test_1#25](https://github.com/test-agent-revue/project_test_1/pull/25) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ unserialize() sur le corps de la requête | major | neutral | non | 166.2 s | 192.4 s |
| `X8-logique-sans-test` | [project_test_2#21](https://github.com/test-agent-revue/project_test_2/pull/21) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ nouvelle logique métier sans test | — | neutral | non | 134.9 s | 167.1 s |
| `X9-dql-concatene` | [project_test_3#23](https://github.com/test-agent-revue/project_test_3/pull/23) | ✅ BLOQUANTE | A_VERIFIER / BLOQUANTE | ✅ DQL construite par concaténation (injection) | critical | failure | oui | 213.3 s | 255.9 s |
| `K1-doc-readme` | [project_test_1#22](https://github.com/test-agent-revue/project_test_1/pull/22) | ✅ CONTROLES_SATISFAITS | CONTROLES_SATISFAITS / A_VERIFIER | — | — | success | non | 242.4 s | 267.7 s |
| `K2-couleur-css` | [project_test_2#17](https://github.com/test-agent-revue/project_test_2/pull/17) | ✅ CONTROLES_SATISFAITS | CONTROLES_SATISFAITS / A_VERIFIER | — | — | success | non | 38.0 s | 56.6 s |
| `K3-constantes-arrondi` | [project_test_3#21](https://github.com/test-agent-revue/project_test_3/pull/21) | ✅ CONTROLES_SATISFAITS | CONTROLES_SATISFAITS / A_VERIFIER | — | — | success | non | 86.8 s | 109.3 s |
| `K4-test-supplementaire` | [project_test_1#21](https://github.com/test-agent-revue/project_test_1/pull/21) | ✅ CONTROLES_SATISFAITS | CONTROLES_SATISFAITS / A_VERIFIER | — | — | success | non | 259.8 s | 279.8 s |

## Remarques retenues

### `D1-sql-injection` — A_VERIFIER
- **critical** `src/Repository/ContractRepository.php:79` — Vulnérabilité d'injection SQL
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `D2-acces-suppression` — A_VERIFIER
- **critical** `src/Controller/ContractController.php:108` — Manque de vérification des droits pour la suppression
- **critical** `templates/contract/show.html.twig:24` — Manque de jeton CSRF dans le formulaire de suppression
- écartées par la validation : 0 · commentaires en ligne publiés : 2

### `D3-dump-oublie` — A_VERIFIER
- **major** `src/Controller/ContractController.php:55` — Debug dump laissé en production
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `D4-secret-en-dur` — BLOQUANTE
- **critical** `src/Service/CrmNotifier.php:13` — Secret en dur détecté(e) dans le code _(source : secret-scan)_
- **major** `src/Service/CrmNotifier.php:15` — PHPStan : Parameter $http of method App\Service\CrmNotifier::__construct() has invalid type Symfony\Contracts\HttpClient\HttpClientInterface. _(source : phpstan)_
- **major** `src/Service/CrmNotifier.php:15` — PHPStan : Property App\Service\CrmNotifier::$http has unknown class Symfony\Contracts\HttpClient\HttpClientInterface as its type. _(source : phpstan)_
- **major** `src/Service/CrmNotifier.php:21` — PHPStan : Call to method request() on an unknown class Symfony\Contracts\HttpClient\HttpClientInterface. _(source : phpstan)_
- écartées par la validation : 0 · commentaires en ligne publiés : 4

### `D5-montant-flottant` — BLOQUANTE
- **major** `src/Service/PremiumCalculator.php:24` — Calcul de prime : perte de précision d'arrondi
- **critical** `(intégration continue):None` — CI en échec : tests _(source : ci)_
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `D6-reference-dupliquee` — BLOQUANTE
- **major** `src/Repository/ContractRepository.php:83` — Calcul incorrect du prochain numéro de référence
- **critical** `(intégration continue):None` — CI en échec : tests _(source : ci)_
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `D7-xss-raw` — A_VERIFIER
- **critical** `templates/contract/show.html.twig:12` — Utilisation de |raw sur une donnée utilisateur sans contrôle
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `D8-secret-description` — BLOQUANTE
- **critical** `(titre / description de la PR):None` — Secret en dur détecté(e) dans le description de la PR _(source : secret-scan)_
- écartées par la validation : 0 · commentaires en ligne publiés : 0

### `C1-export-csv` — A_VERIFIER
- **major** `src/Controller/ContractController.php:48` — Utilisation de findBy sans QueryBuilder
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `C2-liste-pluriel` — CONTROLES_SATISFAITS
- aucune
- écartées par la validation : 0 · commentaires en ligne publiés : 0

### `C3-filtre-twig-money` — CONTROLES_SATISFAITS
- aucune
- écartées par la validation : 0 · commentaires en ligne publiés : 0

### `E1-gros-fichier` — ANALYSE_INCOMPLETE
- Incomplet : `tests/fixtures/portefeuille_2025.csv` non analysé : diff non fourni par GitHub (6001 lignes modifiées)
- aucune
- écartées par la validation : 0 · commentaires en ligne publiés : 0

### `S1-phpstan-methode` — A_VERIFIER
- **major** `src/Controller/ContractController.php:47` — Dépendances non injectées
- **major** `src/Controller/ContractController.php:48` — PHPStan : Call to an undefined method App\Service\PremiumCalculator::annualTotalCents(). _(source : phpstan)_
- écartées par la validation : 0 · commentaires en ligne publiés : 2

### `S2-ci-en-echec` — BLOQUANTE
- **major** `src/Service/PremiumCalculator.php:26` — Logique de plafonnement incorrecte
- **critical** `(intégration continue):None` — CI en échec : tests _(source : ci)_
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `S3-dependance-vulnerable` — BLOQUANTE
- **critical** `composer.lock:None` — Dépendance vulnérable : guzzlehttp/guzzle (14 avis de sécurité) _(source : composer-audit)_
- écartées par la validation : 0 · commentaires en ligne publiés : 0

### `S4-style` — A_VERIFIER
- **major** `src/Service/PremiumCalculator.php:29` — Nouvelle logique métier sans test unitaire
- **minor** `src/Service/PremiumCalculator.php:29` — Style non conforme (2 ligne(s) ajoutée(s)) _(source : php-cs-fixer)_
- écartées par la validation : 0 · commentaires en ligne publiés : 2

### `S5-propre-php` — CONTROLES_SATISFAITS
- aucune
- écartées par la validation : 0 · commentaires en ligne publiés : 0

### `X1-redirection-ouverte` — BLOQUANTE
- **critical** `src/Controller/ContractController.php:123` — Redirection ouverte possible via paramètre utilisateur
- **major** `src/Controller/ContractController.php:123` — Manque de vérification des droits ROLE_GESTIONNAIRE
- **critical** `(intégration continue):None` — CI en échec : tests _(source : ci)_
- écartées par la validation : 0 · commentaires en ligne publiés : 2

### `X2-csrf-retire` — BLOQUANTE
- **critical** `(intégration continue):None` — CI en échec : tests _(source : ci)_
- écartées par la validation : 0 · commentaires en ligne publiés : 0

### `X3-droit-abaisse` — A_VERIFIER
- **major** `src/Controller/ContractController.php:81` — Droit d'édition insuffisant pour une action modifiante
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `X4-donnees-dans-les-logs` — A_VERIFIER
- **major** `src/Controller/ContractController.php:55` — Données personnelles dans les logs
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `X5-exception-avalee` — A_VERIFIER
- **major** `src/Controller/ContractController.php:59` — Exception avalée silencieusement
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `X6-comparaison-hmac` — A_VERIFIER
- **critical** `src/Service/WebhookVerifier.php:15` — Comparaison de signature HMAC non sécurisée
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `X7-unserialize` — A_VERIFIER
- **critical** `src/Controller/ContractController.php:47` — Utilisation de unserialize() sur des données utilisateur
- **major** `src/Controller/ContractController.php:45` — Manque de test pour la logique d'import
- écartées par la validation : 0 · commentaires en ligne publiés : 2

### `X8-logique-sans-test` — A_VERIFIER
- **major** `src/Service/PremiumCalculator.php:35` — Nouvelle logique métier sans test
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `X9-dql-concatene` — BLOQUANTE
- **critical** `src/Repository/ContractRepository.php:34` — Requête DQL vulnérable à l'injection SQL
- **critical** `(intégration continue):None` — CI en échec : tests _(source : ci)_
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `K1-doc-readme` — CONTROLES_SATISFAITS
- aucune
- écartées par la validation : 0 · commentaires en ligne publiés : 0

### `K2-couleur-css` — CONTROLES_SATISFAITS
- aucune
- écartées par la validation : 0 · commentaires en ligne publiés : 0

### `K3-constantes-arrondi` — CONTROLES_SATISFAITS
- aucune
- écartées par la validation : 0 · commentaires en ligne publiés : 0

### `K4-test-supplementaire` — CONTROLES_SATISFAITS
- aucune
- écartées par la validation : 0 · commentaires en ligne publiés : 0

