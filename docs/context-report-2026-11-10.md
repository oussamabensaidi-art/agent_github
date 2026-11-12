# PR Review Agent — Context Report (state as of 2026-11-10)

Repository: `C:\Projects\agentGTIHUB` (local git, branch `main`, **no remote**).
Commits: `cb282f5` (prototype, weeks 1-2) and `388dac0` (e2e bench). The multi-provider
LLM clients (Calipso Qwen3 API, OpenRouter) and related changes are **uncommitted**
in the working tree.

Language note: all prompts, PR comments, logs and docs are in **French**. The code is Python.

---

## 1. Purpose and current state

**Goal (from the French spec, "cahier des charges").** Give Calipso pull requests a first automated review
before a human reviews them. The intended pipeline:

1. webhook;
2. filtered diff;
3. static checks: PHPStan, PHP-CS-Fixer, PHPUnit, composer audit, gitleaks;
4. context;
5. AI review;
6. verdict;
7. PR comments and status;
8. email alert if the PR is blocking.

The constraints:
- The bot never merges or modifies code.
- No code leaves the company infrastructure.
- Secrets are detected before any processing.
- Every analysis is logged.

The success targets:
- 100 % of PRs analysed in under 10 minutes;
- at least 70 % of remarks relevant;
- no code leak;
- reduced human review time.

**What it does today, end to end:**

1. A GitHub `pull_request` webhook hits FastAPI. The API checks the HMAC signature and filters the event: action in the allowed list, PR open, not a draft. It deduplicates and pushes a job to a Redis list.
2. A worker pops the job and runs a LangGraph graph:
   1. fetch the PR, and stop if the head commit moved;
   2. fetch the changed files' unified patches;
   3. drop ignored or oversized files;
   4. regex-scan added lines for secrets, and mask them in the patch;
   5. send the patch chunks to one LLM, which returns JSON findings;
   6. validate the findings;
   7. compute a rule-based verdict;
   8. post one GitHub review (event `COMMENT`) with inline comments, and complete a check run;
   9. send an email if the PR is blocking;
   10. append one JSONL audit line.

**Status by component:**

| Area | Status |
|---|---|
| Webhook receiver, signature check, filtering, dedup, Redis queue, DLQ | **Working.** Unit tests, plus e2e against a fake GitHub. |
| GitHub App auth (JWT → narrowed installation token), PAT mode | **Working against the fake GitHub only.** No real GitHub App has been created or installed yet. |
| Diff parsing, filtering, size limits, chunking | **Working.** Unit and e2e tests. |
| Regex secret scan and masking | **Working** for the listed patterns; minimal by design. Gaps in §8. |
| LLM review (Ollama / Calipso Qwen3 API / OpenRouter) | **Working.** Qwen3 and OpenRouter clients are uncommitted. Quality is in §8. |
| Finding validation, verdict, Markdown rendering | **Working.** |
| Publish review and check run / commit status | **Working against the fake GitHub only.** |
| SMTP alert | **Working against Mailpit only.** Never sent through a real SMTP server. |
| Audit JSONL | **Working.** |
| Manual CLI review (`cli.py`) | **Working.** Dry-run by default. |
| Static checks node (PHPStan, PHP-CS-Fixer, PHPUnit, composer audit, gitleaks) | **Not started** (planned weeks 3-4). |
| Context node (related code, routes, security config, per-repo rules) | **Not started** (planned weeks 5-6). |
| Pilot on a real repo, 30–50 PR benchmark | **Not started** (planned weeks 7-8). |
| Hicham's new requirements | **Not implemented.** These are the "manager review" requirements listed below. |

Hicham's new requirements:
- 4-state verdict;
- no AI-driven blocking during the pilot;
- commit-ordering guarantee;
- kill switch;
- traced exemptions;
- separation of the executor and the publisher;
- p95 latency including queue time;
- `composer.lock` sent to composer audit.

---

## 2. Architecture

### Processes

```
GitHub ──webhook──▶ api (FastAPI, :8020) ──LPUSH──▶ Redis ──BRPOP──▶ worker (LangGraph, 1 job at a time)
                                                                       ├─▶ GitHub REST API
                                                                       ├─▶ LLM (Ollama | Calipso Qwen3 API | OpenRouter)
                                                                       ├─▶ SMTP
                                                                       └─▶ /data/audit.jsonl
```

### LangGraph graph (`agent/graph.py`)

It is a linear `StateGraph(ReviewState)`. It is compiled **without a checkpointer**, so there
is no persistence or resume, and it runs with `ainvoke`, with no streaming.

```
fetch_pr → load_diff → scan_secrets → ai_review → decide → publish → alert → audit → END
     │          │            │             │          │         │        │
     └──────────┴────────────┴──── error ──┴──────────┴─────────┴────────┴──▶ fail → END
fetch_pr ── stale ──▶ audit
```

**Conditional routing.** Each pipeline node has a conditional edge built by `_next()`:
- if `state["error"]` is set, go to `fail`;
- else, if the node is `fetch_pr` and `state["stale"]` is set, go to `audit`;
- else, go to the next node.

`audit` and `fail` both go to `END`.

**Error handling.** Every pipeline node is wrapped in `@guarded`, which catches any
exception and returns `{"error": "<node>: <Type>: <msg>"}`. There is one exception to this:
a failure of a **single LLM chunk** inside `ai_review` is caught locally, counted, and does
not stop the review.

**Dependency injection.** Services are passed as `config["configurable"]["services"]`, a
`Services` dataclass with these fields:
- `github`
- `llm`
- `mailer`
- `audit`
- `settings`
- `rules`

| Node | What it does | External calls |
|---|---|---|
| `fetch_pr` | `GET /repos/{repo}/pulls/{n}`. If the PR head sha ≠ the job sha, or the PR is not open, it sets `stale=True`. Otherwise, unless `DRY_RUN`, it creates a check run `in_progress` (App mode) or a `pending` commit status (token mode). | GitHub |
| `load_diff` | `GET .../pulls/{n}/files`, paginated at 100 per page, up to 30 pages. It parses each `patch` into lines with new-file line numbers. `filter_files` drops: ignored globs, removed files, files without a patch, files over `MAX_FILE_CHANGED_LINES` (1500), and files beyond `MAX_FILES` (100) or `MAX_TOTAL_CHANGED_LINES` (4000). "Too big" and "limit reached" add an `incomplete_reasons` entry. | GitHub |
| `scan_secrets` | Regex scan of **added lines of kept files**. Each hit is a `critical` finding with `source="secret-scan"`. Then every match in the patch is replaced by `[SECRET MASQUÉ]` and the patch is re-parsed. | none |
| `ai_review` | `build_chunks` packs the annotated diffs into chunks of at most `CHUNK_MAX_CHARS` (12 000). Files that are too big are split by hunk. Chunks are sent **sequentially**, one LLM call per chunk, with the same system prompt. A failed chunk increments `chunks_failed` and adds an incomplete reason. | **LLM** (the only node that calls a model) |
| `decide` | `validate_findings` keeps secret findings plus LLM findings. It drops:<br>• severities not in the enum and empty titles;<br>• LLM findings below `MIN_COMMENT_SEVERITY` (`minor`, so `info` is dropped);<br>• LLM findings on a line already flagged by the secret scan;<br>• findings on a file not in the analysed diff (treated as hallucination);<br>• duplicates on (path, line, title).<br>A line outside the diff is kept, but only in the summary (`inline=False`). Then it runs `compute_verdict`, caps inline comments at 30, and renders the Markdown summary. | none |
| `publish` | Skipped in `DRY_RUN`. `POST .../pulls/{n}/reviews` with `event: COMMENT`, `commit_id: head_sha`, the summary body and inline comments (`side: RIGHT`). On a 422 it re-posts with no inline comments and a fallback body listing all findings. Then it completes the check run (`success` / `neutral` / `failure`) or posts a commit status. | GitHub |
| `alert` | Only if the verdict is `BLOQUANTE` and not `DRY_RUN`. It emails `ALERT_EMAILS` with metadata and finding titles, never code. A send failure is logged and swallowed. | SMTP |
| `audit` | Appends one JSON line with status `ok` or `stale`. Fields are listed below. | file |
| `fail` | Sets the check or status to `neutral` with "Revue automatique en échec — relecture humaine requise", writes an audit line with status `error`, and returns. The worker then pushes the job to the DLQ. | GitHub, file |

Audit line fields:
- `ts`, `status`, `delivery_id`, `repo`, `pr_number`, `head_sha`;
- file counts, `secrets_found`, findings per severity;
- `chunks_total` and `chunks_failed`;
- `verdict`, `published`, `alert_sent`;
- `llm_model`, `llm_host`, `llm_served_by`, `llm_cost_usd`;
- `dry_run`, `duration_s`, `error`.

**Verdict rules** (`agent/review.py::compute_verdict`) are deterministic, with 3 states:

| Verdict | Condition | Check run conclusion | Commit status (token mode) |
|---|---|---|---|
| `BLOQUANTE` 🔴 | any `critical` finding, from the secret scan **or the LLM** | `failure` | `failure` |
| `A_VERIFIER` 🟠 | any `major` finding, or any incomplete reason | `neutral` | **`success`** (commit statuses have no neutral) |
| `PRETE` 🟢 | otherwise | `success` | `success` |

### State schema (`agent/state.py::ReviewState`, `TypedDict, total=False`)

- Input:
  - `delivery_id: str`
  - `repo: str`
  - `pr_number: int`
  - `head_sha: str`
  - `installation_id: int | None`
  - `started_at: float`
- PR:
  - `pr_title`
  - `pr_body`
  - `pr_author`
  - `pr_url`
  - `stale: bool`
  - `check_id: int | None`
- Diff:
  - `files: list[FileDiff]`
  - `skipped: list[tuple[path, reason]]`
  - `total_files: int`
- Analysis:
  - `secret_findings`, `llm_findings` and `findings`, each a `list[Finding]`
  - `chunks_total`
  - `chunks_failed`
  - `incomplete_reasons: list[str]`
- Result:
  - `verdict`
  - `summary`
  - `inline_count`
  - `published`
  - `alert_sent`
  - `error`

`Finding` is a dataclass with these fields:
- `path`
- `line`
- `severity` (`critical|major|minor|info`)
- `category`
- `title`
- `explanation`
- `suggestion`
- `source` (`llm` | `secret-scan`)
- `inline`

`FileDiff` has these fields:
- `path`
- `status`
- `patch`
- `additions`
- `deletions`
- `lines: list[DiffLine(kind, new_line, text)]`

### Which model each node calls

Only `ai_review` calls a model, and it calls a single one per run, chosen by `LLM_PROVIDER`:

| `LLM_PROVIDER` | Client | Endpoint | JSON enforcement |
|---|---|---|---|
| `ollama` (default) | `OllamaClient` | `POST {LLM_BASE_URL}/api/chat`. Default model `qwen2.5-coder:7b`, `num_ctx` 16384, temperature 0.1. | Ollama `format` = JSON schema (constrained decoding) |
| `qwen3api` | `Qwen3ApiClient` | Calipso LLM API `POST {QWEN3_API_URL}/api/qwen3/{chat\|think}`, header `x-api-key`. Model Qwen3-14B AWQ 4-bit. `max_tokens` 6144; `max_thinking_tokens` 3072 (think only). | Schema appended to the system prompt; the response is parsed by `extract_findings`, which strips `<think>` blocks and code fences and finds the outer `{}` |
| `openrouter` | `OpenRouterClient` | `https://openrouter.ai/api/v1/chat/completions` with `provider.data_collection=deny` and `usage.include=true` | Same as qwen3api |

Rules shared by all three clients:
- **Host allowlist.** Each client refuses to start unless the URL's host is in `LLM_ALLOWED_HOSTS`. The default is `localhost,127.0.0.1,ollama,host.docker.internal`.
- **Retries.** Retries use tenacity:
  - Ollama and Qwen3: 2 attempts, on timeout, connect error, 5xx or invalid JSON.
  - OpenRouter: 5 attempts, also on 429.
- **OpenRouter is for the test bench only.** It is only enabled in the e2e bench with fake code.

**Models benchmarked** (bench of 4 fake PRs, 3 runs each, 2026-11-09):
- `qwen2.5-coder:7b` (local CPU)
- Qwen3-14B AWQ via Calipso `/chat` and `/think`
- via OpenRouter:
  - `qwen3-coder-next`
  - `qwen3-coder-30b-a3b-instruct`
  - `qwen3-14b`

**Current recommendation:** Qwen3-14B via Calipso `/chat`. See §8.

---

## 3. Trigger and GitHub integration

**How a review starts:**
- **Webhook** (`POST /webhook/github`). It triggers only on `pull_request` with an action in `TRIGGER_ACTIONS` (default `opened,synchronize,reopened,ready_for_review`), on open PRs only, and drafts are skipped (`SKIP_DRAFTS=true`). It returns 202 with one of:
  - `queued`
  - `duplicate`
  - `ignored`
  - `pong`, for a ping
- **Manual CLI:** `python cli.py owner/repo N [--publish] [--installation-id ID]`. It is dry-run by default and prints the summary and findings JSON.
- **No GitHub Action.** There is nothing under `.github/workflows`, either for the agent or as a trigger.

**Dedup.** Two Redis keys are set with `SET NX EX 86400`:
- `prreview:delivery:<X-GitHub-Delivery>`
- `prreview:sha:<repo>#<n>@<sha>`

A replay of the same delivery, or a second event for the same commit within 24 h, is
dropped.

**Authentication:**
- **App mode (target):**
  - It signs an RS256 JWT with the App private key (`/run/secrets/github_app.pem`, a Docker secret).
  - It calls `POST /app/installations/{id}/access_tokens` and requests a **narrowed** token: `contents:read, metadata:read, pull_requests:write, checks:write`.
  - The token is cached per installation for about 55 min, in the worker process memory.
  - Status is reported as **check runs**.
- **Token mode (dev):** a PAT in `GITHUB_TOKEN`. Status is reported as **commit statuses**.
- Webhook authenticity uses `X-Hub-Signature-256` (HMAC-SHA256) with a constant-time compare. An empty secret rejects everything.

**What it reads from the PR:**
- PR metadata: head sha, state, title, body (truncated to 2000 chars for the prompt), author login, html_url.
- The **per-file unified patch** from `/pulls/{n}/files` (**diff only**).
- It does **not** read:
  - full file contents;
  - the base-branch code;
  - the repo config (e.g. `security.yaml`, routes);
  - CI results;
  - existing review comments;
  - other PRs.

**What it writes back:**
- One **PR review** per analysed commit, always `event: COMMENT`. It never uses `APPROVE` or `REQUEST_CHANGES`. The review contains:
  - a summary body;
  - up to 30 inline comments on new-file lines (`side: RIGHT`).
- One **check run** named `calipso-pr-review`, or a commit status with that context:
  - `in_progress` at start;
  - then `success` / `neutral` / `failure` with a title and the summary.
- `@` in generated text is neutralised with a zero-width space, so the bot cannot ping people.
- Texts are truncated to 60 000 chars.
- Merge protection is **not** set by the bot. A human must add the check to the branch protection rules.

---

## 4. Prompts

There is one reviewer prompt, used for every chunk. The system prompt is the template below, with
`{rules}` replaced by the contents of `rules/default.md`. For `qwen3api` and
`openrouter`, a schema instruction is appended (shown after the template). For Ollama,
the schema is passed as the `format` parameter instead.

### System prompt (`agent/prompts.py::SYSTEM_PROMPT`, verbatim)

```text
Tu es un relecteur de code senior chez Calipso (PHP / Symfony, Python, JavaScript).
Tu fais une première revue d'une Pull Request avant la revue humaine.

Ce que tu reçois : un extrait de diff. Chaque ligne est préfixée par son numéro
dans le NOUVEAU fichier puis par "+" (ajoutée), " " (contexte) ou "-" (supprimée,
sans numéro).

Règles :
- Ne commente QUE les lignes ajoutées ("+"), et cite exactement leur numéro et le chemin du fichier.
- Signale seulement de vrais problèmes : bug, faille de sécurité, régression, test manquant
  pour une logique nouvelle, violation des règles d'équipe. Pas de remarques de goût.
- Si tu n'es pas sûr, n'écris rien. Aucune remarque vaut mieux qu'une fausse alerte.
- Gravité :
  critical = faille de sécurité exploitable, perte/corruption de données, plantage certain ;
  major    = bug probable, règle d'équipe importante violée, test manquant sur logique métier ;
  minor    = qualité / lisibilité qui mérite correction ;
  info     = remarque mineure.
- Une valeur "[SECRET MASQUÉ]" a déjà été traitée : ne la commente pas.
- Rédige title, explanation et suggestion en français, de façon concise.
- Réponds uniquement en JSON : {"findings": [...]}. Liste vide si rien à signaler.

Règles de l'équipe :
{rules}
```

### Team rules injected as `{rules}` (`rules/default.md`, verbatim)

```markdown
# Règles d'équipe Calipso — revue de code PHP / Symfony

Ces règles sont injectées dans le prompt de revue. Les modifier ici suffit,
sans changer de code.

## Sécurité (critique)
- Aucune requête SQL/DQL construite par concaténation de données utilisateur :
  paramètres liés obligatoires.
- Aucun secret, mot de passe, clé d'API ou jeton en dur dans le code.
- Toute route qui modifie des données vérifie l'authentification et les droits
  (`#[IsGranted]`, voters, ou contrôle explicite).
- Pas de `unserialize()`, `eval()`, `shell_exec()`, `exec()` sur des entrées externes.
- Sortie Twig : pas de `|raw` sur une donnée utilisateur.
- Les signatures HMAC se comparent avec `hash_equals()`, jamais `==`.

## Fiabilité (majeur)
- Pas de `dd()`, `dump()`, `var_dump()`, `print_r()` oubliés.
- Les appels HTTP sortants ont un timeout et gèrent l'erreur.
- Les exceptions ne sont pas avalées silencieusement (`catch {}` vide).
- Les migrations Doctrine sont réversibles (`down()` implémenté) ou le justifient.
- Données personnelles (assurés, IBAN, emails) jamais écrites dans les logs.

## Qualité (mineur)
- `declare(strict_types=1);` en tête des nouveaux fichiers PHP.
- Typage des paramètres et retours ; pas de `mixed` sans raison.
- Injection de dépendances par constructeur, pas d'accès au conteneur.
- Noms explicites ; méthodes courtes et à responsabilité unique.

## Tests
- Toute nouvelle logique métier (service, calcul, règle) est accompagnée d'un test.
- Un correctif de bug ajoute un test qui reproduit le bug.
```

There is a single global rules file. **Per-repo rules are not implemented.**

### Schema instruction appended for qwen3api / openrouter

```text

Format de sortie OBLIGATOIRE : un unique objet JSON, sans texte autour, conforme à ce schéma JSON :
<FINDINGS_SCHEMA as JSON>
```

### User prompt (per chunk)

```text
Titre de la PR : {title}
Description : {PR body, stripped, first 2000 chars, or "(pas de description)"}

Diff (partie {i}/{n}) :

{chunk}
```

Each file in a chunk is rendered like this:

```text
### src/Controller/ContractController.php (added)
@@ -0,0 +1,25 @@
    1 + <?php
   ...
   17 +     #[Route('/contracts/delete', methods: ['POST'])]
   ...
      - <removed line text>
```

Each line is the new-file line number (right-aligned, 5 characters), then the kind (`+` or a space),
then the text. Removed lines have no number.

### Model output format (`FINDINGS_SCHEMA`)

```json
{"findings": [{
  "path": "string",
  "line": 0,
  "severity": "critical|major|minor|info",
  "category": "security|bug|tests|quality|performance",
  "title": "string",
  "explanation": "string",
  "suggestion": "string (optional)"
}]}
```

Required fields are `path`, `line`, `severity`, `category`, `title` and `explanation`.
The secret scanner creates findings with category `secret`, which is outside the LLM enum.

### Verdict / output produced by the agent (not by the model)

The model only produces findings. The verdict is computed in code (§2), and the posted
summary looks like this:

```markdown
<!-- calipso-pr-review -->
## Revue automatique — 🔴 PR bloquante
Commit analysé : `abc1234` · modèle : `qwen3-14b-awq/chat`

| Bloquant | Majeur | Mineur | Info |
|---:|---:|---:|---:|
| 2 | 1 | 0 | 0 |

### Remarques hors commentaires en ligne        (only if any)
- **[MAJEUR]** `path` ligne N — title

### ⚠️ Revue incomplète                          (only if any)
- `big.php` non analysé : trop volumineux (2000 lignes)

<details><summary>N fichier(s) non analysé(s)</summary> … </details>
---
<sub>Cette revue est un premier filtre … La décision de fusion reste humaine.</sub>
```

Each inline comment looks like this:

```markdown
**[BLOQUANT · security] title**

explanation

**Suggestion :** suggestion

<sub>source : llm</sub>
```

---

## 5. Stack and deployment

- **Language:** Python. The Docker image uses `python:3.12-slim`; the local dev venv runs Python 3.14.4.
- **Key dependencies.** `requirements.txt` has floor-only pins (`>=`). The versions currently installed in the dev venv are:
  - `fastapi 0.162.0`
  - `uvicorn 0.54.0`
  - `langgraph 1.2.20`, with `langgraph-checkpoint 4.3.1` and `langchain-core 1.7.6` installed transitively (unused)
  - `httpx 0.28.1`
  - `tenacity 9.2.1`
  - `redis 8.1.0`
  - `pydantic 2.14.3`
  - `pydantic-settings 2.16.2`
  - `PyJWT[crypto] 2.15.1`
  - `pytest 9.2.0`
  - `pytest-asyncio 1.4.1`

  There is **no lock file.**
- **Configuration:** `pydantic-settings` reads `.env` (git-ignored). `.env.example` documents the variables, but it does **not** yet list the `OPENROUTER_*` variables.
- **Where it runs:** today it runs **only on the developer's Windows PC** in Docker Desktop. It has **never been deployed** to a Calipso server.
- **Docker Compose** (`docker-compose.yml`):
  - **services:**
    - `api`: uvicorn on `:8020`, published on all host interfaces, with a healthcheck on `/health`.
    - `worker`: `python -m worker`, the App key mounted as a Docker secret, audit volume at `/data`.
    - `redis:7-alpine` with AOF.
    - `ollama/ollama:latest`.
  - `docker-compose.gpu.yml` adds an NVIDIA GPU reservation to ollama.
  - `docker-compose.override.yml` (dev only) exposes ollama on `:11434`.
  - The image runs as a non-root user (uid 10001).
  - `LANGSMITH_TRACING=false` and `LANGCHAIN_TRACING_V2=false` are set in the image.
- **Scaling:** `docker compose up --scale worker=N`. Each worker processes one job at a time.
- **External model host.** The Calipso Qwen3 API is at `http://188.40.58.26:8085`. It is **plain HTTP on a public IP**, and the infra team owns it.
- **Persistence:**
  - Redis holds the queue (`prreview:queue`), the DLQ (`prreview:dlq`) and the dedup keys, with AOF on.
  - The audit log is a JSONL file at `/data/audit.jsonl` on a Docker volume, with **no rotation**.
  - The worker writes stdout logs.
  - **No database. No LangGraph checkpointer.**
- **CI/CD for the agent itself:** none. There is no remote, no pipeline and no image registry.

---

## 6. Repo layout

```
agentGTIHUB/
├── main.py                 FastAPI app: /health, /webhook/github (signature check, filter, enqueue)
├── worker.py               Redis consumer loop; runs the graph per job; DLQ on error; Redis-outage backoff
├── jobqueue.py             JobQueue: dedup (delivery id + repo#pr@sha), LPUSH/BRPOP, dead_letter
├── cli.py                  Manual review of a PR without a webhook (dry-run unless --publish)
├── config.py               All settings (pydantic-settings), defaults and CSV helpers
├── agent/
│   ├── graph.py            LangGraph StateGraph, linear pipeline plus error/stale routing
│   ├── nodes.py            The 9 node functions, @guarded error wrapper, audit record builder
│   ├── state.py            ReviewState TypedDict and the Services dataclass (dependency injection)
│   ├── diff.py             Unified patch parsing (new-file line numbers), filtering, LLM rendering, chunking
│   ├── secrets_scan.py     Regex secret detection on added lines and masking before the LLM
│   ├── prompts.py          FINDINGS_SCHEMA, French system prompt, user prompt, rules loader
│   ├── llm.py              OllamaClient, Qwen3ApiClient, OpenRouterClient, host allowlist, JSON extraction, retries
│   ├── review.py           Finding model, anti-hallucination validation, verdict, Markdown rendering
│   ├── github.py           GitHubAppAuth (JWT → narrowed token) and GitHubClient (PR, files, review, check/status)
│   ├── runner.py           Builds services and the LLM client from settings; run_review() → graph.ainvoke
│   ├── notify.py           Alert email builder (metadata only) and SMTP mailer
│   └── audit.py            JSONL audit writer
├── rules/default.md        Team review rules injected into the prompt
├── tests/                  39 pytest tests, all passing: test_diff, test_secrets, test_review,
│                           test_webhook, test_graph (with fakes), test_clients (LLM/GitHub with httpx MockTransport)
├── e2e/
│   ├── run_e2e.py          Bench runner: brings up the stack, sends signed webhooks, asserts, reports model relevance
│   ├── fake_github.py      Fake GitHub API (verifies the App JWT, enforces the token, 422 on bad lines, records calls and violations)
│   ├── fixtures.py         4 fake PRs (#101–#104), expected outcomes, human reference for #101
│   ├── docker-compose.e2e.yml  Overrides: fake GitHub, Mailpit, provider/model env switches
│   └── .keys/              Generated test App key pair (git-ignored)
├── docs/                   Progress report (PDF), Qwen3 test report (PDF), model benchmark (MD), this file
├── Dockerfile, docker-compose.yml, docker-compose.gpu.yml, docker-compose.override.yml
├── requirements.txt, pytest.ini, .env.example, .gitignore, .gitattributes
└── README.md               Architecture, verdicts, security, setup, e2e, known limits, roadmap
```

`secrets/` and `.env` exist locally and are git-ignored. The full codebase is about 2 600 lines of Python, tests included.

---

## 7. Target repos

- **None is connected yet.** No real repository has been reviewed through the webhook,
  and no GitHub App is installed anywhere. All end-to-end runs used the fake GitHub
  and the 4 fake PRs in `e2e/fixtures.py`.
- **Intended targets:** Calipso internal repositories on **GitHub.com**, mainly
  **PHP / Symfony**. The spec mentions PHPStan, PHP-CS-Fixer, PHPUnit and composer, and the
  prompt also mentions Python and JavaScript. The pilot repository has **not been chosen**.
- **Tests and CI in target repos:** **unknown.** This has not been surveyed. The planned static checks
  assume `composer` and PHPUnit can run, but nothing has been checked against a real repo.
  The agent also does not read existing CI results.

---

## 8. Known problems

### Review quality (bench of 2026-11-09: 4 fake PRs, 3 runs per model)

The bench PRs:
- **#101:** SQL injection, a leftover `dump()`, a delete route without an access check, and a hard-coded AWS key.
- **#102:** a clean service with its test.
- **#103:** a 2000-line file, plus a service without a test.
- **#104:** a stale commit.

| Model | SQL injection | Missing access check | Noise on clean #102 | Call failures | Latency per PR |
|---|---|---|---|---|---|
| qwen2.5-coder:7b (CPU) | found, `major` only | 0 | 1 | 0 | 40–215 s |
| **Qwen3-14B AWQ, Calipso `/chat`** | 3/3 critical | **1/3** | **0** | 0/7 | 17–40 s |
| Qwen3-14B AWQ, Calipso `/think` | 3/3 | 1/3 | 0 (1 run completed) | **2/7** (502, connection cut) | 19–76 s |
| Qwen3-Coder-Next (OpenRouter) | 3/3 | **3/3** critical | 1 every run (float rounding) | 0 after the 429 retry | 5–22 s |
| Qwen3-Coder-30B-A3B (OpenRouter) | 3/3 | 0/3 | 2 in 2/3 runs | 0 | 1–18 s |
| Qwen3-14B (OpenRouter) | 3/3 | 2/3 | 1 in 1/3 runs | 0 | 7–15 s |

- `dump()` was found by every model in every run.
- The test missing on #103 was found by the Qwen3-14B variants only.
- **Main quality gap: missing-authorization bugs.** The model sees only the diff, not the routes,
  `security.yaml`, voters or related code, so it rarely flags absent checks.
- **The sample is tiny and is not significant.** The 30–50 labelled PR benchmark has not been built.
- OpenRouter serves different quantisations than the Calipso AWQ server, so the comparisons
  are not like for like.

### Cost and latency

- With local or Calipso models, the marginal cost is 0, but GPU sizing is open:
  - the current GPU is 20 GB;
  - Coder-Next would need 80–96 GB.
- The whole OpenRouter series cost about $0.006, i.e. less than $0.001 per PR.
- No load test has been run. There is no p95 measurement and no queue-time measurement. Chunks are reviewed
  **sequentially**, so latency grows linearly with PR size.

### Bugs and weak spots (verified in code)

1. **GitHub-omitted patches count as "excluded" instead of "incomplete".** GitHub omits `patch` for large text diffs. `filter_files` labels any file without a patch "exclu (binaire ou sans diff)", which is not an incomplete reason. A large text change can therefore be silently unreviewed and still get `PRETE`.
2. **The secret scan covers only reviewed files and only added lines.** It does not scan:
   - files skipped as ignored (`vendor/*`, `var/*`, `build/*`, `dist/*`, `*.generated.*`, lock files);
   - files skipped as too big or over the limit;
   - the PR title and body, which are sent to the LLM unscanned.

   There is also no gitleaks.
3. **Token mode reports green for "à vérifier" and for agent failures.** Commit statuses have no `neutral`, so `neutral` maps to `success`. This applies to the `fail` node too.
4. **Commit ordering.** The stale check runs only at the start, in `fetch_pr`.
   - With several workers, an analysis of an older commit can publish after a newer one.
   - A push made during an analysis does not cancel it.

   Results are attached to their `commit_id` / `head_sha`, but nothing guarantees that
   "an older analysis never overwrites a newer one" (a manager requirement).
5. **Reviews pile up.** Each analysed commit posts a new review. Old reviews and comments are never updated or resolved. The `<!-- calipso-pr-review -->` marker is written but never used for upserts.
6. **The queue is not reliable.**
   - `BRPOP` removes the job before processing, so a worker crash loses it.
   - The dedup keys are set before `LPUSH`, so if `LPUSH` fails, redeliveries are blocked for 24 h.
   - Nothing replays or inspects the DLQ.
7. **Re-runs on the same commit are impossible for 24 h** because of the sha dedup key (e.g. after a rules change, or `reopened`).
8. **The verdict model doesn't match the new requirements.**
   - There are 3 states, while Hicham asks for 4 (Bloquante / À vérifier / Contrôles satisfaits / Analyse incomplète).
   - "Incomplete" is merged into À vérifier.
   - An LLM `critical` finding alone makes the PR `BLOQUANTE`, while the pilot is supposed to have **no AI-driven blocking**.
   - The rules are not versioned in the output.
9. **Missing safety and operations features:**
   - no kill switch;
   - no exemption mechanism;
   - no per-repo config;
   - no executor/publisher separation (the same worker process holds the GitHub write token and calls the LLM).
10. **Prompt injection is not mitigated beyond the output contract.** The PR title, body and diff go straight into the prompt. The model has no tools and its output is schema-validated and filtered to diff files, which limits the damage. But a PR could still steer the review, for example by suppressing findings.
11. **`composer.lock` is ignored entirely.** It should still go to `composer audit` (manager requirement), which does not exist yet.
12. **Smaller issues:**
    - The worker startup log always prints `LLM_MODEL`/`LLM_BASE_URL` (Ollama settings), whatever the provider.
    - The `worker` service `depends_on: ollama` even when using `qwen3api`.
    - `ollama:latest` and `mailpit:latest` are unpinned.
    - The requirements are floor-only.
    - Port 8020 is published on all host interfaces.
    - There is no audit log rotation.
    - The README does not document `qwen3api`/`openrouter`.
    - The multi-provider code is uncommitted.
13. **The Calipso LLM API is plain HTTP on a public IP.** It must move to HTTPS or a private network before any real code is sent.
14. **Authors are not emailed.** GitHub does not expose their email, so alerts only go to `ALERT_EMAILS`.

### What I would change first

- Add the context node: routes, security config, related classes, per-repo rules.
- Move to the 4-state verdict, with AI findings that are advisory-only during the pilot.
- Fix bug 1 (missing patch counted as incomplete).
- Scan everything for secrets with gitleaks, including skipped files and the PR text.
- Use a reliable queue (`BLMOVE` with a processing list), plus a re-check of the head sha before publishing.
- Upsert one summary comment per PR instead of stacking reviews.
- Run static checks in a sandbox.
- Build the 30–50 PR benchmark, and measure p95 under load.

---

## 9. Sandbox, browser testing, streaming, monitoring

- **Running PR code in a sandbox: nothing exists.** The planned `static_checks` node is described
  only in comments and the README:
  - tools: PHPStan, PHP-CS-Fixer, PHPUnit, composer audit, gitleaks;
  - an isolated container per PR, with no production secrets, as Hicham requires;
  - inserted between `scan_secrets` and `ai_review`.

  There is no code, no container image and no checkout of the PR code. The agent never clones the repo.
- **Browser or screenshot testing: nothing exists.** It is not in the spec or the roadmap.
- **Streaming graph events: nothing exists.** The graph runs with `review_graph.ainvoke(...)`, with no
  `astream`/`astream_events`, no checkpointer and no per-node event output. Progress is visible only through:
  - the GitHub check run (`in_progress` → completed);
  - worker log lines (`analyse <label>`, then `terminée`/`en échec`).
- **Monitoring UI: nothing exists.** The available signals:
  - `GET /health` (checks Redis only);
  - the JSONL audit file;
  - worker logs;
  - the Redis DLQ list (no tooling to read it);
  - in the e2e bench only, the Mailpit web UI (`:8025`) and the fake GitHub's `/_recorded` endpoint.

  There are no metrics, no dashboard, no alerting on DLQ growth or latency, and no LangSmith (deliberately off).
