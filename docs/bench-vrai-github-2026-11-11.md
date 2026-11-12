# Banc « vrai GitHub » — 11 novembre 2026

Premier test de l'agent de revue PR contre **le vrai GitHub**, avec de vraies PR
ouvertes en même temps sur plusieurs dépôts.

## Dispositif

| Élément | Valeur |
|---|---|
| Organisation GitHub | `test-agent-revue` (organisation de test, dépôts privés) |
| Dépôts | `project_test_1`, `project_test_2`, `project_test_3` : même application Symfony 7.4 « Portefeuille démo » (contrats d'assurance fictifs, 2 rôles, CRUD, calcul de prime, 19 tests PHPUnit, CI GitHub Actions) |
| GitHub App | `calipso-revue-pr-test` : checks et PR en écriture, contenu et métadonnées en lecture, événement `pull_request`, installée sur tous les dépôts de l'organisation |
| Webhooks | GitHub → relais smee.io → API locale (signature HMAC vérifiée par l'API) |
| Modèle | Qwen3-14B AWQ, API Calipso, point d'accès `/chat` |
| Mode | pilote : les remarques de l'IA sont consultatives, seule la détection de secrets peut bloquer |
| Alertes | Mailpit local (aucune vraie boîte mail) |
| Banc | `bench_real/cases.py` (12 cas avec vérité terrain), `bench_real/run_bench.py` (pousse, ouvre les PR en parallèle, attend, note) |

Les **12 cas** :

| Cas | Dépôt | Contenu | Attendu |
|---|---|---|---|
| D1 | 1 | requête SQL construite par concaténation | injection SQL |
| D2 | 1 | route de suppression sans `IsGranted` gestionnaire | contrôle de droits manquant |
| D3 | 2 | `dump()` oublié dans le contrôleur | dump oublié |
| D4 | 2 | clé d'API en dur dans un service | **Bloquante** (secret, détection déterministe) |
| D5 | 3 | calcul de prime en flottant + troncature | précision / arrondi |
| D6 | 3 | référence suivante non incrémentée (doublons) | régression |
| D7 | 1 | `|raw` sur le nom du client | XSS |
| D8 | 3 | mot de passe dans la **description** de la PR | **Bloquante** (secret dans le texte de la PR) |
| C1 | 2 | export CSV réservé aux gestionnaires, testé | propre |
| C2 | 3 | accord singulier/pluriel dans un template | propre |
| C3 | 1 | filtre Twig `money` testé | propre |
| E1 | 2 | fichier de données de 6 000 lignes | **Analyse incomplète** (GitHub ne fournit pas ce diff) |

Les 12 PR ont été ouvertes **en moins de 5 secondes** sur les 3 dépôts, deux fois :
série `r1` avec 1 worker, série `r2` avec 3 workers (24 analyses au total).

## Résultats

| | r1 · 1 worker | r2 · 3 workers |
|---|---|---|
| Verdicts conformes | **12/12** | **12/12** |
| Défauts attendus détectés | **8/8** | **8/8** |
| PR propres sans remarque majeure | 2/3 | **3/3** |
| Check GitHub conforme au verdict | 12/12 | 12/12 |
| Email d'alerte si et seulement si bloquante | 12/12 | 12/12 |
| Secrets retrouvés dans le journal de l'agent | **0** | **0** |
| Lots en échec (erreur modèle) | 0/11 | 0/11 |
| Durée totale p50 / p95 (attente comprise) | 3 min 55 / 5 min 39 | **1 min 08 / 2 min 22** |
| Attente en file p50 / p95 | 3 min 17 / 5 min 18 | 35 s / 1 min 47 |
| Exécution p50 / p95 | 24 s / 1 min 04 | 32 s / 1 min 00 |

Détail par PR : `bench_real/results/r1/report.md` et `bench_real/results/r2/report.md`.

### Pertinence des remarques (relecture manuelle)

26 remarques retenues sur les deux séries : 16 correspondent aux défauts attendus.
Les 10 autres :

| Remarque | Séries | Jugement |
|---|---|---|
| D2 : formulaire de suppression sans jeton CSRF | r1, r2 | **juste** (vrai défaut non prévu par le cas) |
| D4 / D5 : nouvelle logique sans test | r1, r2 | **juste** (règle d'équipe « Tests ») |
| D4 : URL du CRM en dur | r2 | discutable |
| D4 : « constante non définie » (critique) | r1 | **fausse alerte** |
| C1 : « nombre de lignes du test incorrect » (majeur) | r1 | **fausse alerte** (25 lignes = en-tête + 24 contrats) |
| D2 : « existence du contrat non vérifiée » (majeur) | r2 | **fausse alerte** (Symfony renvoie 404) |
| D8 : « libellé amélioré » (mineur) | r1, r2 | bruit (constat, pas un problème) |

**Taux de pertinence ≈ 77 %** (20 remarques utiles sur 26, 21 avec la remarque discutable),
au-dessus de l'objectif de 70 %. Hors détection de secrets (déterministe) : ≈ 73 %.
Sur les 6 analyses de PR propres, une seule a reçu une remarque majeure (fausse).

### Constats

- **Mode pilote respecté** : les défauts trouvés par l'IA donnent « À vérifier » (check neutre),
  jamais « Bloquante ». Seuls les deux secrets (code et description de PR) bloquent, avec email.
- **Stabilité** : mêmes 8 détections dans les deux séries ; les remarques annexes varient.
- **Charge** : l'attente en file domine. 3 workers divisent la durée totale p95 par 2,4,
  sans ralentir l'exécution de manière notable (le serveur Qwen3 a tenu jusqu'à 9 requêtes simultanées).
- **Sécurité** : aucun des secrets des cas n'apparaît dans le journal (événements, remarques) ;
  ils sont masqués avant tout stockage et avant l'envoi au modèle.

## Cas limites vérifiés

| Cas | Résultat |
|---|---|
| Force-push pendant l'analyse ([project_test_1#10](https://github.com/test-agent-revue/project_test_1/pull/10)) | check de l'ancien commit clos **« annulé : analyse remplacée par un commit plus récent »**, rien publié pour lui ; le nouveau commit a son propre check vert et sa revue |
| PR fermée puis rouverte (même commit) | webhooks reçus, **pas de seconde analyse** (dédoublonnage par commit) |
| Webhook falsifié / sans signature | **401** |
| Interrupteur de publication coupé | analyse journalisée, **aucune écriture GitHub** ; réactivé : check + revue publiés |
| Fichier trop gros pour GitHub (E1) | **« Analyse incomplète »** (check `action_required`), jamais vert |

## Défaut trouvé et corrigé pendant le banc

Première PR réelle : l'API Qwen3 renvoyait **502**. Cause : la fenêtre du modèle servi est de
**8 192 jetons** (prompt + réponse) et l'agent demandait toujours 6 144 jetons de réponse.
Correctif (`agent/llm.py`) : `max_tokens` calculé à chaque appel selon la taille du prompt,
nouvelle tentative avec un budget divisé par deux si le serveur refuse encore, nouveau réglage
`QWEN3_CONTEXT_TOKENS` ; lots de 8 000 caractères pour ce modèle. 3 tests ajoutés (77 au total).
L'agent avait bien réagi avant le correctif : « Analyse incomplète », jamais de vert.

## Captures

Dossier `bench_real/results/r1/screens/` :

1. `01-live-file-attente.jpg` — vue en direct pendant la série r1 : 1 analyse en cours, 11 en file.
2. `02-run-acces-suppression.jpg` — analyse D2 : graphe d'exécution, attente 57 s, exécution 24 s.
3. `03-remarques-acces-csrf.jpg` — remarques D2 avec extrait du diff et boutons d'avis.
4. `04-run-secret-bloquante.jpg` — analyse D4 « Bloquante » (secret).
5. `05-alertes-mailpit.jpg` — emails d'alerte reçus pour les PR bloquantes.

## Limites de ce banc

- 12 cas distincts joués deux fois : en dessous des 30 à 50 PR demandées pour le benchmark de comparaison des modèles.
- Cas écrits par l'équipe qui connaît l'agent : défauts plutôt nets ; à compléter par des PR réelles d'équipe.
- Une seule application cible (Symfony), un seul modèle (Qwen3-14B `/chat`).
- Relais smee.io et API Qwen3 en HTTP sur IP publique : acceptables pour du code fictif, **pas pour du code Calipso**.
  En production : webhook direct vers l'API en HTTPS, modèle sur réseau privé.
- Les liens « Détails » des checks pointent vers `http://localhost:8020/ui` (utilisables seulement sur ce poste).
