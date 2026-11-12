# Banc vrai GitHub — série `s1`

Généré le 2026-11-12T12:13:47 UTC · 5 PR ouvertes en 4.4 s sur 3 dépôts · 2 worker(s)

## Synthèse

- Verdicts conformes : **5/5**
- Défauts attendus détectés : **4/4**
- PR propres sans remarque majeure ou critique : **1/1**
- Check GitHub conforme au verdict : **5/5**
- Email d'alerte conforme (envoyé si et seulement si bloquante) : **5/5**
- Secrets des cas retrouvés dans le journal de l'agent : **0**
- Durée totale (attente comprise) : p50 **79.7 s**, p95 **104.8 s**, max 106.6 s
- Attente en file : p50 53.2 s, p95 74.3 s · exécution : p50 44.4 s, p95 53.2 s
- Lots en échec : 0 / 5

## Par PR

| Cas | PR | Verdict | Attendu | Détection | Autres remarques | Check | Mail | Attente | Total |
|---|---|---|---|---|---|---|---|---:|---:|
| `S1-phpstan-methode` | [project_test_1#12](https://github.com/test-agent-revue/project_test_1/pull/12) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ méthode inexistante (PHPStan) | major | neutral | non | 79.5 s | 106.6 s |
| `S2-ci-en-echec` | [project_test_2#9](https://github.com/test-agent-revue/project_test_2/pull/9) | ✅ BLOQUANTE | BLOQUANTE | ✅ tests en échec dans la CI | — | failure | oui | 0.6 s | 53.4 s |
| `S3-dependance-vulnerable` | [project_test_3#9](https://github.com/test-agent-revue/project_test_3/pull/9) | ✅ BLOQUANTE | BLOQUANTE | ✅ dépendance vulnérable (composer audit) | major, major, major, major, major, major, major, major | failure | oui | 53.2 s | 97.6 s |
| `S4-style` | [project_test_1#11](https://github.com/test-agent-revue/project_test_1/pull/11) | ✅ A_VERIFIER | CONTROLES_SATISFAITS / A_VERIFIER | ✅ style non conforme (PHP-CS-Fixer) | major | neutral | non | 53.5 s | 79.7 s |
| `S5-propre-php` | [project_test_2#10](https://github.com/test-agent-revue/project_test_2/pull/10) | ✅ CONTROLES_SATISFAITS | CONTROLES_SATISFAITS / A_VERIFIER | — | — | success | non | 0.8 s | 54.1 s |

## Remarques retenues

### `S1-phpstan-methode` — A_VERIFIER
- **major** `src/Controller/ContractController.php:44` — Route non protégée par vérification d'autorisation
- **major** `src/Controller/ContractController.php:48` — PHPStan : Call to an undefined method App\Service\PremiumCalculator::annualTotalCents(). _(source : phpstan)_
- écartées par la validation : 0 · commentaires en ligne publiés : 2

### `S2-ci-en-echec` — BLOQUANTE
- **critical** `(intégration continue):None` — CI en échec : tests _(source : ci)_
- écartées par la validation : 0 · commentaires en ligne publiés : 0

### `S3-dependance-vulnerable` — BLOQUANTE
- **critical** `composer.lock:None` — Dépendance vulnérable : guzzlehttp/guzzle (CVE-2026-69246) _(source : composer-audit)_
- **critical** `composer.lock:None` — Dépendance vulnérable : guzzlehttp/guzzle (CVE-2022-31091) _(source : composer-audit)_
- **critical** `composer.lock:None` — Dépendance vulnérable : guzzlehttp/guzzle (CVE-2022-31090) _(source : composer-audit)_
- **critical** `composer.lock:None` — Dépendance vulnérable : guzzlehttp/guzzle (CVE-2022-31043) _(source : composer-audit)_
- **critical** `composer.lock:None` — Dépendance vulnérable : guzzlehttp/guzzle (CVE-2022-31042) _(source : composer-audit)_
- **critical** `composer.lock:None` — Dépendance vulnérable : guzzlehttp/guzzle (CVE-2022-29248) _(source : composer-audit)_
- **major** `composer.lock:None` — Dépendance vulnérable : guzzlehttp/guzzle (CVE-2026-69245) _(source : composer-audit)_
- **major** `composer.lock:None` — Dépendance vulnérable : guzzlehttp/guzzle (CVE-2026-67354) _(source : composer-audit)_
- **major** `composer.lock:None` — Dépendance vulnérable : guzzlehttp/guzzle (CVE-2026-67355) _(source : composer-audit)_
- **major** `composer.lock:None` — Dépendance vulnérable : guzzlehttp/guzzle (CVE-2026-67353) _(source : composer-audit)_
- **major** `composer.lock:None` — Dépendance vulnérable : guzzlehttp/guzzle (CVE-2026-59883) _(source : composer-audit)_
- **major** `composer.lock:None` — Dépendance vulnérable : guzzlehttp/guzzle (CVE-2026-67339) _(source : composer-audit)_
- **major** `composer.lock:None` — Dépendance vulnérable : guzzlehttp/guzzle (CVE-2026-55767) _(source : composer-audit)_
- **major** `composer.lock:None` — Dépendance vulnérable : guzzlehttp/guzzle (CVE-2026-55568) _(source : composer-audit)_
- écartées par la validation : 0 · commentaires en ligne publiés : 0

### `S4-style` — A_VERIFIER
- **major** `src/Service/PremiumCalculator.php:30` — Nouvelle logique métier sans test
- **minor** `src/Service/PremiumCalculator.php:29` — Style non conforme (2 ligne(s) ajoutée(s)) _(source : php-cs-fixer)_
- écartées par la validation : 0 · commentaires en ligne publiés : 2

### `S5-propre-php` — CONTROLES_SATISFAITS
- aucune
- écartées par la validation : 0 · commentaires en ligne publiés : 0

