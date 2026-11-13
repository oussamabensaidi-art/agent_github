# Banc vrai GitHub — série `m14b-skills`

Généré le 2026-11-13T12:33:53 UTC · 30 PR ouvertes en 5.5 s sur 3 dépôts · 3 worker(s)

## Synthèse

- Verdicts conformes : **30/30**
- Défauts attendus détectés : **21/21**
- PR propres sans remarque majeure ou critique : **8/8**
- Check GitHub conforme au verdict : **30/30**
- Email d'alerte conforme (envoyé si et seulement si bloquante) : **30/30**
- Secrets des cas retrouvés dans le journal de l'agent : **0**
- Durée totale (attente comprise) : p50 **208.7 s**, p95 **358.9 s**, max 369.4 s
- Attente en file : p50 181.4 s, p95 322.4 s · exécution : p50 30.0 s, p95 68.9 s
- Lots en échec : 0 / 55

## Par PR

| Cas | PR | Verdict | Attendu | Détection | Autres remarques | Check | Mail | Attente | Total |
|---|---|---|---|---|---|---|---|---:|---:|
| `D1-sql-injection` | [project_test_1#53](https://github.com/test-agent-revue/project_test_1/pull/53) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ injection SQL (concaténation) | — | neutral | non | 38.1 s | 106.8 s |
| `D2-acces-suppression` | [project_test_1#58](https://github.com/test-agent-revue/project_test_1/pull/58) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ route de suppression sans contrôle de droits | critical | neutral | non | 234.4 s | 268.3 s |
| `D3-dump-oublie` | [project_test_2#55](https://github.com/test-agent-revue/project_test_2/pull/55) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ dump() oublié | — | neutral | non | 165.7 s | 191.3 s |
| `D4-secret-en-dur` | [project_test_2#51](https://github.com/test-agent-revue/project_test_2/pull/51) | ✅ BLOQUANTE | BLOQUANTE | ✅ clé d'API en dur (détection déterministe) | major, major, major, major | failure | oui | 266.2 s | 328.2 s |
| `D5-montant-flottant` | [project_test_3#47](https://github.com/test-agent-revue/project_test_3/pull/47) | ✅ BLOQUANTE | A_VERIFIER / BLOQUANTE | ✅ flottant + troncature au lieu d'arrondi | critical | failure | oui | 232.7 s | 266.3 s |
| `D6-reference-dupliquee` | [project_test_3#48](https://github.com/test-agent-revue/project_test_3/pull/48) | ✅ BLOQUANTE | A_VERIFIER / BLOQUANTE | ✅ référence suivante non incrémentée (doublon) | critical | failure | oui | 294.1 s | 324.0 s |
| `D7-xss-raw` | [project_test_1#61](https://github.com/test-agent-revue/project_test_1/pull/61) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ |raw sur une donnée saisie (XSS) | — | neutral | non | 176.2 s | 204.5 s |
| `D8-secret-description` | [project_test_3#43](https://github.com/test-agent-revue/project_test_3/pull/43) | ✅ BLOQUANTE | BLOQUANTE | ✅ mot de passe dans la description de la PR | — | failure | oui | 94.9 s | 117.6 s |
| `C1-export-csv` | [project_test_2#47](https://github.com/test-agent-revue/project_test_2/pull/47) | ✅ CONTROLES_SATISFAITS | CONTROLES_SATISFAITS / A_VERIFIER | — | — | success | non | 126.9 s | 165.9 s |
| `C2-liste-pluriel` | [project_test_3#45](https://github.com/test-agent-revue/project_test_3/pull/45) | ✅ CONTROLES_SATISFAITS | CONTROLES_SATISFAITS / A_VERIFIER | — | — | success | non | 117.4 s | 146.8 s |
| `C3-filtre-twig-money` | [project_test_1#62](https://github.com/test-agent-revue/project_test_1/pull/62) | ✅ CONTROLES_SATISFAITS | CONTROLES_SATISFAITS / A_VERIFIER | — | — | success | non | 191.2 s | 236.8 s |
| `E1-gros-fichier` | [project_test_2#50](https://github.com/test-agent-revue/project_test_2/pull/50) | ✅ ANALYSE_INCOMPLETE | ANALYSE_INCOMPLETE | — | — | action_required | non | 136.2 s | 142.6 s |
| `S1-phpstan-methode` | [project_test_1#60](https://github.com/test-agent-revue/project_test_1/pull/60) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ méthode inexistante (PHPStan) | critical, major | neutral | non | 142.5 s | 186.8 s |
| `S2-ci-en-echec` | [project_test_2#53](https://github.com/test-agent-revue/project_test_2/pull/53) | ✅ BLOQUANTE | BLOQUANTE | ✅ tests en échec dans la CI | major | failure | oui | 320.7 s | 364.3 s |
| `S3-dependance-vulnerable` | [project_test_3#49](https://github.com/test-agent-revue/project_test_3/pull/49) | ✅ BLOQUANTE | BLOQUANTE | ✅ dépendance vulnérable (composer audit) | — | failure | oui | 262.7 s | 294.2 s |
| `S4-style` | [project_test_1#55](https://github.com/test-agent-revue/project_test_1/pull/55) | ✅ A_VERIFIER | CONTROLES_SATISFAITS / A_VERIFIER | ✅ style non conforme (PHP-CS-Fixer) | major | neutral | non | 0.5 s | 69.7 s |
| `S5-propre-php` | [project_test_2#48](https://github.com/test-agent-revue/project_test_2/pull/48) | ✅ CONTROLES_SATISFAITS | CONTROLES_SATISFAITS / A_VERIFIER | — | — | success | non | 327.9 s | 369.4 s |
| `X1-redirection-ouverte` | [project_test_1#54](https://github.com/test-agent-revue/project_test_1/pull/54) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ redirection ouverte (URL fournie par l'utilisateur) | minor | neutral | non | 0.6 s | 70.0 s |
| `X2-csrf-retire` | [project_test_2#56](https://github.com/test-agent-revue/project_test_2/pull/56) | ✅ BLOQUANTE | A_VERIFIER / BLOQUANTE | ✅ vérification CSRF supprimée | critical | failure | oui | 268.0 s | 295.5 s |
| `X3-droit-abaisse` | [project_test_3#50](https://github.com/test-agent-revue/project_test_3/pull/50) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ modification ouverte aux lecteurs (ROLE_USER) | — | neutral | non | 323.8 s | 352.4 s |
| `X4-donnees-dans-les-logs` | [project_test_1#56](https://github.com/test-agent-revue/project_test_1/pull/56) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ données du client écrites dans les logs | — | neutral | non | 146.4 s | 176.3 s |
| `X5-exception-avalee` | [project_test_2#49](https://github.com/test-agent-revue/project_test_2/pull/49) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ exception avalée (catch vide), succès affiché à tort | — | neutral | non | 186.6 s | 212.9 s |
| `X6-comparaison-hmac` | [project_test_3#44](https://github.com/test-agent-revue/project_test_3/pull/44) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ signature comparée avec == au lieu de hash_equals() | — | neutral | non | 106.4 s | 127.0 s |
| `X7-unserialize` | [project_test_1#59](https://github.com/test-agent-revue/project_test_1/pull/59) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ unserialize() sur le corps de la requête | — | neutral | non | 295.5 s | 320.8 s |
| `X8-logique-sans-test` | [project_test_2#52](https://github.com/test-agent-revue/project_test_2/pull/52) | ✅ A_VERIFIER | A_VERIFIER / BLOQUANTE | ✅ nouvelle logique métier sans test | — | neutral | non | 236.6 s | 262.7 s |
| `X9-dql-concatene` | [project_test_3#42](https://github.com/test-agent-revue/project_test_3/pull/42) | ✅ BLOQUANTE | A_VERIFIER / BLOQUANTE | ✅ DQL construite par concaténation (injection) | critical | failure | oui | 69.4 s | 95.0 s |
| `K1-doc-readme` | [project_test_1#57](https://github.com/test-agent-revue/project_test_1/pull/57) | ✅ CONTROLES_SATISFAITS | CONTROLES_SATISFAITS / A_VERIFIER | — | — | success | non | 69.3 s | 136.8 s |
| `K2-couleur-css` | [project_test_2#54](https://github.com/test-agent-revue/project_test_2/pull/54) | ✅ CONTROLES_SATISFAITS | CONTROLES_SATISFAITS / A_VERIFIER | — | — | success | non | 212.8 s | 232.7 s |
| `K3-constantes-arrondi` | [project_test_3#46](https://github.com/test-agent-revue/project_test_3/pull/46) | ✅ CONTROLES_SATISFAITS | CONTROLES_SATISFAITS / A_VERIFIER | — | — | success | non | 204.4 s | 234.5 s |
| `K4-test-supplementaire` | [project_test_1#52](https://github.com/test-agent-revue/project_test_1/pull/52) | ✅ CONTROLES_SATISFAITS | CONTROLES_SATISFAITS / A_VERIFIER | — | — | success | non | 0.5 s | 38.3 s |

## Remarques retenues

### `D1-sql-injection` — A_VERIFIER
- **critical** `src/Repository/ContractRepository.php:79` — Injection SQL via concaténation de paramètre utilisateur
- écartées par la validation : 1 · commentaires en ligne publiés : 1

### `D2-acces-suppression` — A_VERIFIER
- **critical** `src/Controller/ContractController.php:108` — Accès non restreint à l'action de suppression
- **critical** `templates/contract/show.html.twig:24` — Manque de protection CSRF sur le formulaire de suppression
- écartées par la validation : 2 · commentaires en ligne publiés : 2

### `D3-dump-oublie` — A_VERIFIER
- **major** `src/Controller/ContractController.php:55` — Appel à dump() dans un contrôleur de production
- **major** `src/Controller/ContractController.php:55` — Appel à dump() oublié
- écartées par la validation : 0 · commentaires en ligne publiés : 2

### `D4-secret-en-dur` — BLOQUANTE
- **major** `src/Service/CrmNotifier.php:21` — Appel HTTP sans gestion des erreurs
- **critical** `src/Service/CrmNotifier.php:13` — Secret en dur détecté(e) dans le code _(source : secret-scan)_
- **major** `src/Service/CrmNotifier.php:15` — PHPStan : Parameter $http of method App\Service\CrmNotifier::__construct() has invalid type Symfony\Contracts\HttpClient\HttpClientInterface. _(source : phpstan)_
- **major** `src/Service/CrmNotifier.php:15` — PHPStan : Property App\Service\CrmNotifier::$http has unknown class Symfony\Contracts\HttpClient\HttpClientInterface as its type. _(source : phpstan)_
- **major** `src/Service/CrmNotifier.php:21` — PHPStan : Call to method request() on an unknown class Symfony\Contracts\HttpClient\HttpClientInterface. _(source : phpstan)_
- écartées par la validation : 0 · commentaires en ligne publiés : 5

### `D5-montant-flottant` — BLOQUANTE
- **major** `src/Service/PremiumCalculator.php:24` — Calcul de prime avec perte de précision en flottant
- **critical** `(intégration continue):None` — CI en échec : tests _(source : ci)_
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `D6-reference-dupliquee` — BLOQUANTE
- **major** `src/Repository/ContractRepository.php:83` — Suppression de l'incrémentation du numéro de référence
- **critical** `(intégration continue):None` — CI en échec : tests _(source : ci)_
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `D7-xss-raw` — A_VERIFIER
- **critical** `templates/contract/show.html.twig:12` — XSS vulnérabilité par utilisation de |raw sur donnée utilisateur
- écartées par la validation : 1 · commentaires en ligne publiés : 1

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
- **critical** `src/Controller/ContractController.php:43` — Accès non contrôlé à un endpoint sensible
- **major** `src/Controller/ContractController.php:44` — Nouvelle logique métier sans test
- **major** `src/Controller/ContractController.php:48` — PHPStan : Call to an undefined method App\Service\PremiumCalculator::annualTotalCents(). _(source : phpstan)_
- écartées par la validation : 0 · commentaires en ligne publiés : 3

### `S2-ci-en-echec` — BLOQUANTE
- **major** `src/Service/PremiumCalculator.php:26` — Logique inversée du plafonnement
- **critical** `(intégration continue):None` — CI en échec : tests _(source : ci)_
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `S3-dependance-vulnerable` — BLOQUANTE
- **critical** `composer.lock:None` — Dépendance vulnérable : guzzlehttp/guzzle (14 avis de sécurité) _(source : composer-audit)_
- écartées par la validation : 0 · commentaires en ligne publiés : 0

### `S4-style` — A_VERIFIER
- **major** `src/Service/PremiumCalculator.php:30` — Nouvelle logique métier sans test
- **minor** `src/Service/PremiumCalculator.php:29` — Style non conforme (2 ligne(s) ajoutée(s)) _(source : php-cs-fixer)_
- écartées par la validation : 0 · commentaires en ligne publiés : 2

### `S5-propre-php` — CONTROLES_SATISFAITS
- aucune
- écartées par la validation : 0 · commentaires en ligne publiés : 0

### `X1-redirection-ouverte` — A_VERIFIER
- **critical** `src/Controller/ContractController.php:123` — Redirection ouverte vers une URL provenant du paramètre de requête
- **minor** `src/Controller/ContractController.php:123` — Utilisation d'une URL brute au lieu d'une route nommée
- écartées par la validation : 0 · commentaires en ligne publiés : 2

### `X2-csrf-retire` — BLOQUANTE
- **critical** `src/Controller/ContractController.php:109` — Absence de protection CSRF dans une action modifiant des données
- **critical** `src/Controller/ContractController.php:108` — Suppression de la vérification CSRF dans une action modifiant des données
- **critical** `(intégration continue):None` — CI en échec : tests _(source : ci)_
- écartées par la validation : 0 · commentaires en ligne publiés : 2

### `X3-droit-abaisse` — A_VERIFIER
- **critical** `src/Controller/ContractController.php:81` — Contrôle d'accès insuffisant sur l'action de modification
- écartées par la validation : 1 · commentaires en ligne publiés : 1

### `X4-donnees-dans-les-logs` — A_VERIFIER
- **critical** `src/Controller/ContractController.php:55` — Données personnelles (SIREN) écrites dans les logs
- **major** `src/Controller/ContractController.php:55` — Données sensibles logguées en clair
- écartées par la validation : 0 · commentaires en ligne publiés : 2

### `X5-exception-avalee` — A_VERIFIER
- **major** `src/Controller/ContractController.php:58` — Exception avalée sans traitement
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `X6-comparaison-hmac` — A_VERIFIER
- **critical** `src/Service/WebhookVerifier.php:15` — Comparaison de signature HMAC avec '==' au lieu de hash_equals()
- écartées par la validation : 1 · commentaires en ligne publiés : 1

### `X7-unserialize` — A_VERIFIER
- **critical** `src/Controller/ContractController.php:47` — Utilisation de unserialize() sur une entrée externe
- écartées par la validation : 1 · commentaires en ligne publiés : 1

### `X8-logique-sans-test` — A_VERIFIER
- **major** `src/Service/PremiumCalculator.php:35` — Nouvelle logique métier sans test
- écartées par la validation : 0 · commentaires en ligne publiés : 1

### `X9-dql-concatene` — BLOQUANTE
- **critical** `src/Repository/ContractRepository.php:34` — Injection SQL via concaténation de paramètre utilisateur
- **critical** `(intégration continue):None` — CI en échec : tests _(source : ci)_
- écartées par la validation : 1 · commentaires en ligne publiés : 1

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

