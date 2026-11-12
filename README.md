# Agent IA de revue des Pull Requests — Calipso

**v2** : webhook → diff filtré → masquage des secrets (code **et** texte de la PR)
→ revue IA en lots parallèles → verdict à 4 états par règles fixes et versionnées
→ commentaires + statut sur la PR (commit revérifié juste avant) → alerte email si
bloquante → journal d'audit et **journal d'événements rejouable**, suivi en direct
dans une interface web.

Le bot ne fusionne rien, ne modifie aucun code et publie seulement des revues
de type `COMMENT`. La fusion reste une décision humaine.

## Architecture

```
GitHub ──webhook──▶ api (FastAPI :8020) ──▶ Redis (file + dédup) ──▶ worker (LangGraph, graph.astream)
                    vérifie la signature        ▲                     │
                    crée le run (en file)       └── Redis Stream ◀────┤ événements (masqués)
                                                                      ├─▶ Postgres : runs, events, findings, avis, réglages
   navigateur ◀── SSE ── api /ui ◀── Redis Stream + Postgres          ├─▶ GitHub API (lecture PR, revue, check)
                                                                      ├─▶ modèle (Ollama | API LLM Calipso)
                                                                      ├─▶ SMTP (alerte PR bloquante)
                                                                      └─▶ /data/audit.jsonl
```

Graphe (`agent/graph.py`) — chaque nœud émet `node_started` / `node_finished` (durée) :

| Nœud | Rôle |
|---|---|
| `fetch_pr` | Lit la PR ; si un push plus récent existe → job obsolète, on s'arrête. Passe le check à « en cours » (sauf interrupteur coupé). |
| `load_diff` | Récupère les fichiers ; exclut lock files, générés, `vendor/`, supprimés, binaires ; applique les limites de taille. **Un fichier modifié dont GitHub n'a pas fourni le patch est « incomplet », jamais « exclu ».** |
| `scan_secrets` | Détecte les secrets dans les lignes ajoutées **et dans le titre / la description de la PR** (remarque critique déterministe) et les **masque avant** tout envoi au modèle. |
| `ai_review` | Découpe le diff en lots, analysés **en parallèle** (`LLM_CONCURRENCY`). Un lot raté n'arrête pas la revue. Chaque remarque est émise dès que son lot répond. |
| `decide` | Écarte les remarques inventées (fichier hors diff), sous le seuil de gravité, ou en double ; calcule le verdict. |
| `publish` | **Relit la PR** : si un commit plus récent est arrivé, rien n'est publié et le check est clos « remplacé ». Sinon revue GitHub avec commentaires en ligne + check run (ou statut de commit). |
| `alert` | Email si la PR est bloquante. |
| `audit` / `fail` | Journal d'audit ; en cas d'erreur, check « action requise » / statut `error` (jamais vert) et job en DLQ. |

Toute écriture vers l'extérieur (check, revue, statut, email) relit d'abord
l'**interrupteur de publication**.

### Verdict v2 (`agent/review.py`, version `verdict-v2`)

Ordre d'évaluation, par règles fixes :

| Verdict | Condition | Check run (App) | Statut de commit (jeton) |
|---|---|---|---|
| 🔴 **Bloquante** | remarque `critical` d'une source **déterministe** (secret). Hors mode pilote, une critique de l'IA aussi. | `failure` | `failure` |
| ⚪ **Analyse incomplète** | une partie n'a pas été relue : fichier trop gros, patch non fourni par GitHub, limite de taille, lot en échec | `action_required` | `error` |
| 🟠 **À vérifier** | remarque `major`, ou critique de l'IA en mode pilote | `neutral` | `failure` |
| 🟢 **Contrôles satisfaits** | sinon | `success` | `success` |
| échec de l'agent | l'analyse n'a pas abouti | `action_required` | `error` |
| remplacée | un commit plus récent est arrivé pendant l'analyse | `cancelled` | `error` |

- **Mode pilote** (`PILOT_MODE=true`, par défaut) : les remarques de l'IA sont des
  avis. Elles ne peuvent jamais, seules, rendre une PR bloquante.
- **Seul « Contrôles satisfaits » est vert.** Ce qui n'a pas été relu n'est jamais
  présenté comme réussi, en mode App comme en mode jeton (qui n'a pas d'état neutre).
- **Version des règles** publiée avec chaque verdict (résumé, check, audit, journal) :
  `verdict-v2+regles-<empreinte de rules/default.md>`.
- Les checks et statuts pointent vers la page de l'analyse (`UI_PUBLIC_URL`).

Pour que « bloquante » empêche réellement la fusion, ajoutez le check
`calipso-pr-review` aux règles de protection de branche : c'est un réglage
humain, pas une action du bot.

### Interrupteur de publication (kill switch)

Un seul réglage, en base (`settings.publishing_enabled`), modifiable depuis
l'interface par un admin, **sans redéploiement**, tracé (`settings_history` : qui,
quand). Coupé : l'agent continue d'analyser et de tout journaliser, mais **n'écrit
plus rien** sur GitHub (check, revue, statut, y compris le statut d'échec) et
n'envoie plus d'email. Il est relu avant chaque écriture. `PUBLISH_ENABLED` ne
donne que la valeur initiale. Base injoignable : la dernière valeur lue s'applique.

### Journal d'événements et interface de suivi

- Le worker exécute le graphe en flux (`astream`, modes `custom` + `values`).
  Événements : `run_queued`, `run_started` (attente), `node_started/finished`,
  `chunks_planned`, `chunk_started/finished/failed`, `finding`,
  `findings_validated`, `verdict`, `publication_skipped`, `superseded`,
  `published`, `alert_sent`, `error`, `run_finished` (exécution, attente, total).
- Écrits dans **Postgres** (durable, rejouable) puis diffusés sur un **Redis
  Stream** ; l'api les relaie aux navigateurs en **SSE**.
- **Aucun secret dans le journal** : seuls des contenus déjà masqués sont émis, et
  tout est masqué une seconde fois à l'écriture.
- Le suivi ne fait jamais échouer une revue : une erreur d'écriture est journalisée
  et ignorée.

Interface (`/ui`, en français, derrière authentification, sans CDN) :

- **En direct** : graphe qui s'allume nœud par nœud, lots en parallèle, remarques à
  leur arrivée, chronologie avec l'attente.
- **Analyse** : verdict, remarques par gravité avec les lignes du diff, couverture
  (fichiers relus / incomplets / exclus), modèle, durées, coût, relecture des
  événements (×1, ×4, ×16).
- **Historique** filtrable (dépôt, verdict, dates, démo) ; **Statistiques** :
  volume, verdicts, p50 / p95 attente comprise (objectif < 10 min), taux d'échec des
  lots, DLQ, **pertinence** des remarques à partir des avis « pertinente / fausse
  alerte » (objectif 70 %).
- Comptes : `UI_USERS` (`login:role:empreinte`, rôle `admin` ou `lecteur`),
  empreinte via `python -m ui.auth`. Sessions Redis, cookie HttpOnly SameSite=Strict,
  en-tête anti-CSRF sur toute écriture, 5 essais de connexion par 5 minutes.

### Démo (faux GitHub)

```bash
docker compose -f docker-compose.yml -f docker-compose.override.yml -f e2e/docker-compose.e2e.yml -f docker-compose.demo.yml up -d --build
```

Puis http://localhost:8020/ui, compte admin. Le bouton « Lancer la démo » envoie de
vrais webhooks signés à l'api pour les PR fictives de `e2e/fixtures.py` : tout le
pipeline tourne, contre le faux GitHub. Refusé si l'api pointe vers le vrai GitHub.

### Garde-fous sécurité

- **Signature webhook** HMAC-SHA256 vérifiée ; secret vide = tout est refusé.
- **Aucun code ne sort de l'infra** : l'hôte du modèle doit figurer dans
  `LLM_ALLOWED_HOSTS`, sinon l'appel est refusé avant envoi. Passer au cloud =
  ajouter l'hôte, donc une décision explicite. Le traçage LangSmith est coupé.
- **Secrets** masqués avant le modèle, jamais recopiés dans les commentaires,
  l'email ou le journal.
- **Droits minimaux** : jeton d'installation restreint à `contents:read`,
  `metadata:read`, `pull_requests:write`, `checks:write`.
- **Journal d'audit** : une ligne JSON par analyse, sans code (compteurs,
  verdict, modèle, hôte du modèle, durée, erreur).
- Le texte généré ne peut pas notifier (`@mention` neutralisées).

## Mise en route

### 1. GitHub App (compte bot)

Créer une GitHub App dans l'organisation :

- **Webhook URL** : `https://<hôte interne exposé>/webhook/github`, secret = `GITHUB_WEBHOOK_SECRET`
- **Permissions** : Contents *Read*, Metadata *Read*, Pull requests *Read & write*, Checks *Read & write*. Rien d'autre (pas d'Administration, pas de Contents write).
- **Événements** : *Pull request*
- Générer une clé privée → `secrets/github_app.pem` (jamais commitée), noter l'App ID, installer l'App sur le dépôt pilote.

### 2. Configuration

```bash
cp .env.example .env   # puis renseigner les valeurs
```

### 3. Lancement

```bash
docker compose up -d --build
docker compose exec ollama ollama pull qwen2.5-coder:7b
```

Serveur GPU :

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

`docker-compose.override.yml` (exposition d'Ollama sur l'hôte) est réservé au
poste de dev.

### 4. Revue à la main (sans webhook)

Utile pour le pilote et pour comparer des modèles. En `DRY_RUN`, rien n'est publié.

```bash
python cli.py owner/repo 42             # analyse et affiche
python cli.py owner/repo 42 --publish   # publie aussi sur la PR
```

## Développement

```bash
py -3 -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m pytest -q
```

Les règles d'équipe injectées dans le prompt sont dans `rules/default.md`.

### Banc de test de bout en bout (e2e)

Vraie API, vrai worker, vrai Redis, vrai Ollama ; **faux GitHub** (`e2e/fake_github.py`)
et **Mailpit** à la place du SMTP : rien ne part vers GitHub ni vers une vraie boîte.

```bash
.venv/Scripts/python e2e/run_e2e.py                                         # modèle 0.5b
E2E_MODEL=qwen2.5-coder:7b .venv/Scripts/python e2e/run_e2e.py --only 101 102  # modèle cible
```

Le faux GitHub applique les contrôles du vrai (JWT de l'App, jeton obligatoire,
422 sur une ligne hors diff) et signale toute action interdite au bot (fusion,
écriture de code, APPROVE). Les mails reçus sont visibles sur http://localhost:8025.

| PR de test | Vérifié (indépendant du modèle) |
|---|---|
| #101 contrôleur avec clé AWS en dur, injection SQL, `dump()` | check `failure`, email envoyé, commentaire inline ligne 12, **le secret n'apparaît nulle part** (appels GitHub, email, audit, logs) |
| #102 service propre + test | revue publiée ; mail ⇔ check `failure` |
| #103 fichier de 2000 lignes + service | fichier signalé « trop volumineux », jamais `success` |
| #104 webhook sur un ancien commit | job obsolète : rien publié, audit `stale` |
| relivraison du webhook #101 | refusée (`duplicate`) |

La pertinence des remarques du modèle sur #101 est **rapportée** (référence :
injection SQL L20, `dump()` L21, contrôle d'accès L17), pas assertée.

## Limites connues (à traiter dans les phases suivantes)

- Une nouvelle revue est publiée à chaque nouveau commit analysé ; pas encore
  de suppression des remarques déjà faites sur un commit précédent.
- Le scanner de secrets intégré est un garde-fou minimal ; gitleaks arrive avec
  les contrôles statiques.
- File simple (`LPUSH`/`BRPOP`) : si un worker meurt pendant une analyse, ce
  job est perdu (pas de DLQ). Passer à une file fiable (`BLMOVE` vers une liste
  « en cours » + reprise) avant la production.
- Les auteurs ne sont pas joints par email : GitHub ne fournit pas leur adresse.
  L'alerte va à `ALERT_EMAILS`.
- Interrupteur coupé **pendant** une analyse dont le check est déjà « en cours » :
  ce check reste « en cours » sur GitHub (plus aucune écriture n'est permise).
- Re-vérification du commit avant publication : il reste une fenêtre de quelques
  centaines de millisecondes entre la relecture de la PR et l'envoi de la revue.
- Les remarques arrivent lot par lot (le modèle renvoie un JSON complet par lot),
  pas mot à mot.
- Le scanner ne couvre pas encore les fichiers exclus ou trop gros (gitleaks, à venir).
- Interface : servir en HTTPS et passer `UI_COOKIE_SECURE=true` hors poste local.

## Feuille de route

| Semaines | Lot | État |
|---|---|---|
| 1-2 | Prototype : webhook, diff, revue IA, commentaire, verdict, alerte, audit | ✅ ce dépôt |
| 3-4 | Contrôles statiques : PHPStan, PHP-CS-Fixer, PHPUnit, composer audit, gitleaks, dans un conteneur isolé par PR (nœud `static_checks`) | à faire |
| 5-6 | Contexte : code lié, règles par dépôt (`.github/pr-review.md`), calibrage du verdict | à faire |
| 7-8 | Pilote sur un dépôt réel ; mesure de la pertinence (≥ 70 %), du délai (< 10 min) et du temps de revue | à faire |
