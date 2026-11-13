# Banc vrai GitHub — série `m30b`

Généré le 2026-11-13T11:13:57 UTC · 30 PR ouvertes en 5.7 s sur 3 dépôts · 3 worker(s)

## Synthèse

- Verdicts conformes : **29/30**
- Défauts attendus détectés : **17/21**
- PR propres sans remarque majeure ou critique : **8/8**
- Check GitHub conforme au verdict : **30/30**
- Email d'alerte conforme (envoyé si et seulement si bloquante) : **30/30**
- Secrets des cas retrouvés dans le journal de l'agent : **0**
- Durée totale (attente comprise) : p50 **151.5 s**, p95 **205.5 s**, max 209.6 s
- Attente en file : p50 137.3 s, p95 192.4 s · exécution : p50 12.3 s, p95 68.6 s
- Lots en échec : 0 / 29

## Par PR

| Cas | PR | Verdict | Attendu | Détection | Autres remarques | Check | Mail | Attente | Total |
|---|---|---|---|---|---|---|---|---:|---:|
| `D1-sql-injection` | [project_test_1#37](https://github.com/test-agent-revue/project_test_1/pull/37) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ injection SQL (concaténation) | — | neutral | non | 186.5 s | 201.5 s |
| `D2-acces-suppression` | [project_test_1#36](https://github.com/test-agent-revue/project_test_1/pull/36) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ route de suppression sans contrôle de droits | major | neutral | non | 184.5 s | 197.4 s |
| `D3-dump-oublie` | [project_test_2#27](https://github.com/test-agent-revue/project_test_2/pull/27) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ dump() oublié | — | neutral | non | 0.5 s | 68.7 s |
| `D4-secret-en-dur` | [project_test_2#33](https://github.com/test-agent-revue/project_test_2/pull/33) | ✅ BLOQUANTE | BLOQUANTE | ✅ clé d'API en dur (détection déterministe) | critical, critical, major, major, major | failure | oui | 159.5 s | 175.9 s |
| `D5-montant-flottant` | [project_test_3#26](https://github.com/test-agent-revue/project_test_3/pull/26) | ✅ BLOQUANTE | A_VERIFIER / BLOQUANTE | ❌ flottant + troncature au lieu d'arrondi | critical | failure | oui | 119.3 s | 129.7 s |
| `D6-reference-dupliquee` | [project_test_3#28](https://github.com/test-agent-revue/project_test_3/pull/28) | ✅ BLOQUANTE | A_VERIFIER / BLOQUANTE | ❌ référence suivante non incrémentée (doublon) | critical | failure | oui | 175.7 s | 186.8 s |
| `D7-xss-raw` | [project_test_1#30](https://github.com/test-agent-revue/project_test_1/pull/30) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ |raw sur une donnée saisie (XSS) | — | neutral | non | 145.4 s | 159.9 s |
| `D8-secret-description` | [project_test_3#27](https://github.com/test-agent-revue/project_test_3/pull/27) | ✅ BLOQUANTE | BLOQUANTE | ✅ mot de passe dans la description de la PR | — | failure | oui | 116.6 s | 123.3 s |
| `C1-export-csv` | [project_test_2#30](https://github.com/test-agent-revue/project_test_2/pull/30) | ✅ CONTROLES_SATISFAITS | CONTROLES_SATISFAITS / A_VERIFIER | — | — | success | non | 139.7 s | 157.3 s |
| `C2-liste-pluriel` | [project_test_3#24](https://github.com/test-agent-revue/project_test_3/pull/24) | ✅ CONTROLES_SATISFAITS | CONTROLES_SATISFAITS / A_VERIFIER | — | — | success | non | 0.6 s | 36.8 s |
| `C3-filtre-twig-money` | [project_test_1#39](https://github.com/test-agent-revue/project_test_1/pull/39) | ✅ CONTROLES_SATISFAITS | CONTROLES_SATISFAITS / A_VERIFIER | — | — | success | non | 157.1 s | 170.2 s |
| `E1-gros-fichier` | [project_test_2#31](https://github.com/test-agent-revue/project_test_2/pull/31) | ✅ ANALYSE_INCOMPLETE | ANALYSE_INCOMPLETE | — | — | action_required | non | 114.6 s | 135.5 s |
| `S1-phpstan-methode` | [project_test_1#35](https://github.com/test-agent-revue/project_test_1/pull/35) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ méthode inexistante (PHPStan) | major, major | neutral | non | 159.3 s | 173.3 s |
| `S2-ci-en-echec` | [project_test_2#28](https://github.com/test-agent-revue/project_test_2/pull/28) | ✅ BLOQUANTE | BLOQUANTE | ✅ tests en échec dans la CI | critical | failure | oui | 123.1 s | 133.8 s |
| `S3-dependance-vulnerable` | [project_test_3#25](https://github.com/test-agent-revue/project_test_3/pull/25) | ✅ BLOQUANTE | BLOQUANTE | ✅ dépendance vulnérable (composer audit) | — | failure | oui | 0.5 s | 36.9 s |
| `S4-style` | [project_test_1#34](https://github.com/test-agent-revue/project_test_1/pull/34) | ✅ CONTROLES_SATISFAITS | CONTROLES_SATISFAITS / A_VERIFIER | ✅ style non conforme (PHP-CS-Fixer) | — | success | non | 134.9 s | 145.6 s |
| `S5-propre-php` | [project_test_2#29](https://github.com/test-agent-revue/project_test_2/pull/29) | ✅ CONTROLES_SATISFAITS | CONTROLES_SATISFAITS / A_VERIFIER | — | — | success | non | 68.2 s | 104.6 s |
| `X1-redirection-ouverte` | [project_test_1#38](https://github.com/test-agent-revue/project_test_1/pull/38) | ✅ BLOQUANTE | A_VERIFIER / BLOQUANTE | ✅ redirection ouverte (URL fournie par l'utilisateur) | critical | failure | oui | 140.3 s | 159.6 s |
| `X2-csrf-retire` | [project_test_2#35](https://github.com/test-agent-revue/project_test_2/pull/35) | ✅ BLOQUANTE | A_VERIFIER / BLOQUANTE | ❌ vérification CSRF supprimée | critical | failure | oui | 180.1 s | 186.7 s |
| `X3-droit-abaisse` | [project_test_3#32](https://github.com/test-agent-revue/project_test_3/pull/32) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ modification ouverte aux lecteurs (ROLE_USER) | — | neutral | non | 173.0 s | 184.9 s |
| `X4-donnees-dans-les-logs` | [project_test_1#40](https://github.com/test-agent-revue/project_test_1/pull/40) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ données du client écrites dans les logs | — | neutral | non | 198.0 s | 209.6 s |
| `X5-exception-avalee` | [project_test_2#36](https://github.com/test-agent-revue/project_test_2/pull/36) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ exception avalée (catch vide), succès affiché à tort | — | neutral | non | 197.2 s | 208.8 s |
| `X6-comparaison-hmac` | [project_test_3#30](https://github.com/test-agent-revue/project_test_3/pull/30) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ signature comparée avec == au lieu de hash_equals() | — | neutral | non | 36.7 s | 48.1 s |
| `X7-unserialize` | [project_test_1#32](https://github.com/test-agent-revue/project_test_1/pull/32) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ unserialize() sur le corps de la requête | — | neutral | non | 48.1 s | 117.0 s |
| `X8-logique-sans-test` | [project_test_2#32](https://github.com/test-agent-revue/project_test_2/pull/32) | ❌ CONTROLES_SATISFAITS | A_VERIFIER / BLOQUANTE | ❌ nouvelle logique métier sans test | — | success | non | 186.5 s | 198.2 s |
| `X9-dql-concatene` | [project_test_3#31](https://github.com/test-agent-revue/project_test_3/pull/31) | ✅ BLOQUANTE | A_VERIFIER / BLOQUANTE | ✅ DQL construite par concaténation (injection) | critical | failure | oui | 129.6 s | 140.5 s |
| `K1-doc-readme` | [project_test_1#33](https://github.com/test-agent-revue/project_test_1/pull/33) | ✅ CONTROLES_SATISFAITS | CONTROLES_SATISFAITS / A_VERIFIER | — | — | success | non | 36.3 s | 120.1 s |
| `K2-couleur-css` | [project_test_2#34](https://github.com/test-agent-revue/project_test_2/pull/34) | ✅ CONTROLES_SATISFAITS | CONTROLES_SATISFAITS / A_VERIFIER | — | — | success | non | 133.7 s | 139.8 s |
| `K3-constantes-arrondi` | [project_test_3#29](https://github.com/test-agent-revue/project_test_3/pull/29) | ✅ CONTROLES_SATISFAITS | CONTROLES_SATISFAITS / A_VERIFIER | — | — | success | non | 170.0 s | 180.4 s |
| `K4-test-supplementaire` | [project_test_1#31](https://github.com/test-agent-revue/project_test_1/pull/31) | ✅ CONTROLES_SATISFAITS | CONTROLES_SATISFAITS / A_VERIFIER | — | — | success | non | 104.6 s | 114.7 s |

## Remarques retenues

### `D1-sql-injection` — A_VERIFIER
- **critical** `src/Repository/ContractRepository.php:79` — Injection SQL potentielle
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `D2-acces-suppression` — A_VERIFIER
- **major** `src/Controller/ContractController.php:107` — Absence de protection CSRF sur la suppression de contrat
- **major** `src/Controller/ContractController.php:108` — Manque de vérification des droits sur la suppression de contrat
- **major** `templates/contract/show.html.twig:23` — Absence de jeton CSRF dans le formulaire de suppression
- écartées par la validation : 0 · commentaires en ligne publiés : 3

### `D3-dump-oublie` — A_VERIFIER
- **critical** `src/Controller/ContractController.php:55` — Dump oublie dans le code de production
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `D4-secret-en-dur` — BLOQUANTE
- **critical** `src/Service/CrmNotifier.php:12` — URL du CRM en dur
- **critical** `src/Service/CrmNotifier.php:22` — Clé API du CRM en dur
- **critical** `src/Service/CrmNotifier.php:13` — Secret en dur détecté(e) dans le code _(source : secret-scan)_
- **major** `src/Service/CrmNotifier.php:15` — PHPStan : Parameter $http of method App\Service\CrmNotifier::__construct() has invalid type Symfony\Contracts\HttpClient\HttpClientInterface. _(source : phpstan)_
- **major** `src/Service/CrmNotifier.php:15` — PHPStan : Property App\Service\CrmNotifier::$http has unknown class Symfony\Contracts\HttpClient\HttpClientInterface as its type. _(source : phpstan)_
- **major** `src/Service/CrmNotifier.php:21` — PHPStan : Call to method request() on an unknown class Symfony\Contracts\HttpClient\HttpClientInterface. _(source : phpstan)_
- écartées par la validation : 0 · commentaires en ligne publiés : 6

### `D5-montant-flottant` — BLOQUANTE
- **critical** `(intégration continue):None` — CI en échec : tests _(source : ci)_
- écartées par la validation : 0 · commentaires en ligne publiés : 0

### `D6-reference-dupliquee` — BLOQUANTE
- **critical** `(intégration continue):None` — CI en échec : tests _(source : ci)_
- écartées par la validation : 0 · commentaires en ligne publiés : 0

### `D7-xss-raw` — A_VERIFIER
- **critical** `templates/contract/show.html.twig:12` — Utilisation de |raw sur une donnée utilisateur
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `D8-secret-description` — BLOQUANTE
- **critical** `(titre / description de la PR):None` — Secret en dur détecté(e) dans le description de la PR _(source : secret-scan)_
- écartées par la validation : 0 · commentaires en ligne publiés : 0

### `C1-export-csv` — CONTROLES_SATISFAITS
- aucune
- écartées par la validation : 0 · commentaires en ligne publiés : 0

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
- **major** `src/Controller/ContractController.php:44` — Absence de vérification des droits d'accès pour l'export JSON
- **major** `src/Controller/ContractController.php:47` — Utilisation potentielle d'une variable non définie
- **major** `src/Controller/ContractController.php:48` — PHPStan : Call to an undefined method App\Service\PremiumCalculator::annualTotalCents(). _(source : phpstan)_
- écartées par la validation : 0 · commentaires en ligne publiés : 3

### `S2-ci-en-echec` — BLOQUANTE
- **critical** `src/Service/PremiumCalculator.php:26` — Logique inversée dans le plafonnement de la prime
- **critical** `(intégration continue):None` — CI en échec : tests _(source : ci)_
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `S3-dependance-vulnerable` — BLOQUANTE
- **critical** `composer.lock:None` — Dépendance vulnérable : guzzlehttp/guzzle (14 avis de sécurité) _(source : composer-audit)_
- écartées par la validation : 0 · commentaires en ligne publiés : 0

### `S4-style` — CONTROLES_SATISFAITS
- **minor** `src/Service/PremiumCalculator.php:29` — Style non conforme (2 ligne(s) ajoutée(s)) _(source : php-cs-fixer)_
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `S5-propre-php` — CONTROLES_SATISFAITS
- aucune
- écartées par la validation : 0 · commentaires en ligne publiés : 0

### `X1-redirection-ouverte` — BLOQUANTE
- **major** `src/Controller/ContractController.php:123` — Redirection non validée vers une URL fournie par l'utilisateur
- **critical** `(intégration continue):None` — CI en échec : tests _(source : ci)_
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `X2-csrf-retire` — BLOQUANTE
- **critical** `(intégration continue):None` — CI en échec : tests _(source : ci)_
- écartées par la validation : 0 · commentaires en ligne publiés : 0

### `X3-droit-abaisse` — A_VERIFIER
- **major** `src/Controller/ContractController.php:81` — Droits trop permissifs pour la modification d'un contrat
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `X4-donnees-dans-les-logs` — A_VERIFIER
- **major** `src/Controller/ContractController.php:55` — Données sensibles dans les logs
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `X5-exception-avalee` — A_VERIFIER
- **major** `src/Controller/ContractController.php:58` — Gestion insuffisante des exceptions lors de la persistence du contrat
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `X6-comparaison-hmac` — A_VERIFIER
- **critical** `src/Service/WebhookVerifier.php:15` — Comparaison de chaînes non sécurisée
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `X7-unserialize` — A_VERIFIER
- **critical** `src/Controller/ContractController.php:47` — Utilisation de `unserialize()` sur une entrée utilisateur non fiable
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `X8-logique-sans-test` — CONTROLES_SATISFAITS
- aucune
- écartées par la validation : 0 · commentaires en ligne publiés : 0

### `X9-dql-concatene` — BLOQUANTE
- **critical** `src/Repository/ContractRepository.php:34` — Concaténation SQL potentielle
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

