# Banc vrai GitHub — série `r3`

Généré le 2026-11-13T10:37:15 UTC · 17 PR ouvertes en 4.4 s sur 3 dépôts · 3 worker(s)

## Synthèse

- Verdicts conformes : **17/17**
- Défauts attendus détectés : **12/12**
- PR propres sans remarque majeure ou critique : **4/4**
- Check GitHub conforme au verdict : **17/17**
- Email d'alerte conforme (envoyé si et seulement si bloquante) : **17/17**
- Secrets des cas retrouvés dans le journal de l'agent : **0**
- Durée totale (attente comprise) : p50 **107.4 s**, p95 **204.4 s**, max 206.1 s
- Attente en file : p50 85.2 s, p95 161.3 s · exécution : p50 32.4 s, p95 56.1 s
- Lots en échec : 0 / 16

## Par PR

| Cas | PR | Verdict | Attendu | Détection | Autres remarques | Check | Mail | Attente | Total |
|---|---|---|---|---|---|---|---|---:|---:|
| `D1-sql-injection` | [project_test_1#16](https://github.com/test-agent-revue/project_test_1/pull/16) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ injection SQL (concaténation) | — | neutral | non | 85.2 s | 107.4 s |
| `D2-acces-suppression` | [project_test_1#14](https://github.com/test-agent-revue/project_test_1/pull/14) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ route de suppression sans contrôle de droits | critical | neutral | non | 103.5 s | 135.9 s |
| `D3-dump-oublie` | [project_test_2#16](https://github.com/test-agent-revue/project_test_2/pull/16) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ dump() oublié | — | neutral | non | 134.7 s | 158.0 s |
| `D4-secret-en-dur` | [project_test_2#11](https://github.com/test-agent-revue/project_test_2/pull/11) | ✅ BLOQUANTE | BLOQUANTE | ✅ clé d'API en dur (détection déterministe) | major, major, major, major | failure | oui | 0.6 s | 86.6 s |
| `D5-montant-flottant` | [project_test_3#14](https://github.com/test-agent-revue/project_test_3/pull/14) | ✅ BLOQUANTE | A_VERIFIER / BLOQUANTE | ✅ flottant + troncature au lieu d'arrondi | critical | failure | oui | 175.1 s | 206.1 s |
| `D6-reference-dupliquee` | [project_test_3#12](https://github.com/test-agent-revue/project_test_3/pull/12) | ✅ BLOQUANTE | A_VERIFIER / BLOQUANTE | ✅ référence suivante non incrémentée (doublon) | critical | failure | oui | 79.9 s | 102.4 s |
| `D7-xss-raw` | [project_test_1#15](https://github.com/test-agent-revue/project_test_1/pull/15) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ |raw sur une donnée saisie (XSS) | — | neutral | non | 102.1 s | 127.2 s |
| `D8-secret-description` | [project_test_3#13](https://github.com/test-agent-revue/project_test_3/pull/13) | ✅ BLOQUANTE | BLOQUANTE | ✅ mot de passe dans la description de la PR | — | failure | oui | 0.5 s | 23.4 s |
| `C1-export-csv` | [project_test_2#15](https://github.com/test-agent-revue/project_test_2/pull/15) | ✅ CONTROLES_SATISFAITS | CONTROLES_SATISFAITS / A_VERIFIER | — | — | success | non | 69.7 s | 104.0 s |
| `C2-liste-pluriel` | [project_test_3#11](https://github.com/test-agent-revue/project_test_3/pull/11) | ✅ CONTROLES_SATISFAITS | CONTROLES_SATISFAITS / A_VERIFIER | — | — | success | non | 23.2 s | 42.6 s |
| `C3-filtre-twig-money` | [project_test_1#13](https://github.com/test-agent-revue/project_test_1/pull/13) | ✅ CONTROLES_SATISFAITS | CONTROLES_SATISFAITS / A_VERIFIER | — | — | success | non | 36.5 s | 69.9 s |
| `E1-gros-fichier` | [project_test_2#12](https://github.com/test-agent-revue/project_test_2/pull/12) | ✅ ANALYSE_INCOMPLETE | ANALYSE_INCOMPLETE | — | — | action_required | non | 0.5 s | 37.1 s |
| `S1-phpstan-methode` | [project_test_1#18](https://github.com/test-agent-revue/project_test_1/pull/18) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ méthode inexistante (PHPStan) | critical | neutral | non | 135.4 s | 180.8 s |
| `S2-ci-en-echec` | [project_test_2#13](https://github.com/test-agent-revue/project_test_2/pull/13) | ✅ BLOQUANTE | BLOQUANTE | ✅ tests en échec dans la CI | major | failure | oui | 157.9 s | 204.0 s |
| `S3-dependance-vulnerable` | [project_test_3#10](https://github.com/test-agent-revue/project_test_3/pull/10) | ✅ BLOQUANTE | BLOQUANTE | ✅ dépendance vulnérable (composer audit) | major, major | failure | oui | 126.8 s | 175.5 s |
| `S4-style` | [project_test_1#17](https://github.com/test-agent-revue/project_test_1/pull/17) | ✅ A_VERIFIER | CONTROLES_SATISFAITS / A_VERIFIER | ✅ style non conforme (PHP-CS-Fixer) | major | neutral | non | 107.1 s | 135.0 s |
| `S5-propre-php` | [project_test_2#14](https://github.com/test-agent-revue/project_test_2/pull/14) | ✅ CONTROLES_SATISFAITS | CONTROLES_SATISFAITS / A_VERIFIER | — | — | success | non | 42.3 s | 80.2 s |

## Remarques retenues

### `D1-sql-injection` — A_VERIFIER
- **critical** `src/Repository/ContractRepository.php:79` — Injection SQL potentielle dans findByReferencePrefix
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `D2-acces-suppression` — A_VERIFIER
- **critical** `src/Controller/ContractController.php:108` — Manque de vérification des droits pour l'action de suppression
- **critical** `templates/contract/show.html.twig:24` — Manque de jeton CSRF dans le formulaire de suppression
- écartées par la validation : 0 · commentaires en ligne publiés : 2

### `D3-dump-oublie` — A_VERIFIER
- **major** `src/Controller/ContractController.php:55` — Appel à dump() non supprimé
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `D4-secret-en-dur` — BLOQUANTE
- **major** `src/Service/CrmNotifier.php:21` — Aucun traitement des erreurs HTTP
- **critical** `src/Service/CrmNotifier.php:13` — Secret en dur détecté(e) dans le code _(source : secret-scan)_
- **major** `src/Service/CrmNotifier.php:15` — PHPStan : Parameter $http of method App\Service\CrmNotifier::__construct() has invalid type Symfony\Contracts\HttpClient\HttpClientInterface. _(source : phpstan)_
- **major** `src/Service/CrmNotifier.php:15` — PHPStan : Property App\Service\CrmNotifier::$http has unknown class Symfony\Contracts\HttpClient\HttpClientInterface as its type. _(source : phpstan)_
- **major** `src/Service/CrmNotifier.php:21` — PHPStan : Call to method request() on an unknown class Symfony\Contracts\HttpClient\HttpClientInterface. _(source : phpstan)_
- écartées par la validation : 1 · commentaires en ligne publiés : 5

### `D5-montant-flottant` — BLOQUANTE
- **major** `src/Service/PremiumCalculator.php:24` — Calcul de prime : perte de précision due à l'arithmétique flottante
- **critical** `(intégration continue):None` — CI en échec : tests _(source : ci)_
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `D6-reference-dupliquee` — BLOQUANTE
- **major** `src/Repository/ContractRepository.php:83` — Calcul incorrect du prochain numéro de référence
- **critical** `(intégration continue):None` — CI en échec : tests _(source : ci)_
- écartées par la validation : 0 · commentaires en ligne publiés : 1

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
- **critical** `src/Controller/ContractController.php:47` — Utilisation incorrecte de $this->contracts sans injection de dépendance
- **major** `src/Controller/ContractController.php:48` — PHPStan : Call to an undefined method App\Service\PremiumCalculator::annualTotalCents(). _(source : phpstan)_
- écartées par la validation : 0 · commentaires en ligne publiés : 2

### `S2-ci-en-echec` — BLOQUANTE
- **major** `src/Service/PremiumCalculator.php:26` — Logique inversée du plafonnement
- **critical** `(intégration continue):None` — CI en échec : tests _(source : ci)_
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `S3-dependance-vulnerable` — BLOQUANTE
- **major** `composer.json:13` — Dépendance potentielle vulnérable
- **major** `composer.json:36` — Configuration d'audit inappropriée
- **critical** `composer.lock:None` — Dépendance vulnérable : guzzlehttp/guzzle (14 avis de sécurité) _(source : composer-audit)_
- écartées par la validation : 0 · commentaires en ligne publiés : 2

### `S4-style` — A_VERIFIER
- **major** `src/Service/PremiumCalculator.php:30` — Nouvelle logique métier sans test
- **minor** `src/Service/PremiumCalculator.php:29` — Style non conforme (2 ligne(s) ajoutée(s)) _(source : php-cs-fixer)_
- écartées par la validation : 0 · commentaires en ligne publiés : 2

### `S5-propre-php` — CONTROLES_SATISFAITS
- aucune
- écartées par la validation : 0 · commentaires en ligne publiés : 0

