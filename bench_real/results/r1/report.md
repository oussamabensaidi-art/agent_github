# Banc vrai GitHub — série `r1`

Généré le 2026-11-11T09:46:19 UTC · 12 PR ouvertes en 4.3 s sur 3 dépôts · 1 worker(s)

## Synthèse

- Verdicts conformes : **12/12**
- Défauts attendus détectés : **8/8**
- PR propres sans remarque majeure ou critique : **2/3**
- Check GitHub conforme au verdict : **12/12**
- Email d'alerte conforme (envoyé si et seulement si bloquante) : **12/12**
- Secrets des cas retrouvés dans le journal de l'agent : **0**
- Durée totale (attente comprise) : p50 **234.9 s**, p95 **339.3 s**, max 351.9 s
- Attente en file : p50 197.0 s, p95 317.7 s · exécution : p50 24.2 s, p95 64.4 s
- Lots en échec : 0 / 11

## Par PR

| Cas | PR | Verdict | Attendu | Détection | Autres remarques | Check | Mail | Attente | Total |
|---|---|---|---|---|---|---|---|---:|---:|
| `D1-sql-injection` | [project_test_1#2](https://github.com/test-agent-revue/project_test_1/pull/2) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ injection SQL (concaténation) | — | neutral | non | 36.5 s | 56.7 s |
| `D2-acces-suppression` | [project_test_1#3](https://github.com/test-agent-revue/project_test_1/pull/3) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ route de suppression sans contrôle de droits | critical | neutral | non | 56.6 s | 80.8 s |
| `D3-dump-oublie` | [project_test_2#1](https://github.com/test-agent-revue/project_test_2/pull/1) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ dump() oublié | — | neutral | non | 280.6 s | 310.3 s |
| `D4-secret-en-dur` | [project_test_2#4](https://github.com/test-agent-revue/project_test_2/pull/4) | ✅ BLOQUANTE | BLOQUANTE | ✅ clé d'API en dur (détection déterministe) | critical | failure | oui | 309.5 s | 329.1 s |
| `D5-montant-flottant` | [project_test_3#1](https://github.com/test-agent-revue/project_test_3/pull/1) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ flottant + troncature au lieu d'arrondi | — | neutral | non | 0.0 s | 37.3 s |
| `D6-reference-dupliquee` | [project_test_3#2](https://github.com/test-agent-revue/project_test_3/pull/2) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ référence suivante non incrémentée (doublon) | — | neutral | non | 327.7 s | 351.9 s |
| `D7-xss-raw` | [project_test_1#4](https://github.com/test-agent-revue/project_test_1/pull/4) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ |raw sur une donnée saisie (XSS) | — | neutral | non | 236.9 s | 255.1 s |
| `D8-secret-description` | [project_test_3#4](https://github.com/test-agent-revue/project_test_3/pull/4) | ✅ BLOQUANTE | BLOQUANTE | ✅ mot de passe dans la description de la PR | minor | failure | oui | 254.7 s | 280.6 s |
| `C1-export-csv` | [project_test_2#2](https://github.com/test-agent-revue/project_test_2/pull/2) | ✅ A_VERIFIER | CONTROLES_SATISFAITS / A_VERIFIER | — | major | neutral | non | 161.2 s | 232.8 s |
| `C2-liste-pluriel` | [project_test_3#3](https://github.com/test-agent-revue/project_test_3/pull/3) | ✅ CONTROLES_SATISFAITS | CONTROLES_SATISFAITS / A_VERIFIER | — | — | success | non | 139.3 s | 161.2 s |
| `C3-filtre-twig-money` | [project_test_1#5](https://github.com/test-agent-revue/project_test_1/pull/5) | ✅ CONTROLES_SATISFAITS | CONTROLES_SATISFAITS / A_VERIFIER | — | — | success | non | 80.8 s | 139.3 s |
| `E1-gros-fichier` | [project_test_2#3](https://github.com/test-agent-revue/project_test_2/pull/3) | ✅ ANALYSE_INCOMPLETE | ANALYSE_INCOMPLETE | — | — | action_required | non | 232.7 s | 236.9 s |

## Remarques retenues

### `D1-sql-injection` — A_VERIFIER
- **critical** `src/Repository/ContractRepository.php:79` — SQL injection vulnérabilité dans findByReferencePrefix
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `D2-acces-suppression` — A_VERIFIER
- **critical** `src/Controller/ContractController.php:108` — Manque de vérification des droits avant suppression
- **critical** `templates/contract/show.html.twig:24` — Manque de token CSRF dans le formulaire de suppression
- écartées par la validation : 0 · commentaires en ligne publiés : 2

### `D3-dump-oublie` — A_VERIFIER
- **major** `src/Controller/ContractController.php:55` — Appel à dump() non supprimé
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `D4-secret-en-dur` — BLOQUANTE
- **critical** `src/Service/CrmNotifier.php:22` — Utilisation d'une constante non définie pour une clé API
- **critical** `src/Service/CrmNotifier.php:13` — Secret en dur détecté(e) dans le code _(source : secret-scan)_
- écartées par la validation : 0 · commentaires en ligne publiés : 2

### `D5-montant-flottant` — A_VERIFIER
- **major** `src/Service/PremiumCalculator.php:24` — Calcul de prime : perte de précision avec les flottants
- **major** `src/Service/PremiumCalculator.php:24` — Manque de test pour vérifier la précision du calcul
- écartées par la validation : 0 · commentaires en ligne publiés : 2

### `D6-reference-dupliquee` — A_VERIFIER
- **major** `src/Repository/ContractRepository.php:83` — Régression : suppression de l'incrémentation du numéro de référence
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `D7-xss-raw` — A_VERIFIER
- **critical** `templates/contract/show.html.twig:12` — Risque XSS par utilisation de |raw sur donnée utilisateur
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `D8-secret-description` — BLOQUANTE
- **minor** `templates/contract/show.html.twig:13` — Amélioration de la clarté du libellé
- **critical** `(titre / description de la PR):None` — Secret en dur détecté(e) dans le description de la PR _(source : secret-scan)_
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `C1-export-csv` — A_VERIFIER
- **major** `tests/Functional/ContractControllerTest.php:82` — Test vérification du nombre de lignes incorrect
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

