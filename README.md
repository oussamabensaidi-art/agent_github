# Agent IA de revue des Pull Requests — Calipso

Prototype des semaines 1-2 du cahier des charges : **webhook → diff filtré →
masquage des secrets → revue par modèle local → commentaires + statut sur la
PR → alerte email si bloquante → journal d'audit**.

Le bot ne fusionne rien, ne modifie aucun code et publie seulement des revues
de type `COMMENT`. La fusion reste une décision humaine.

## Architecture

```
GitHub ──webhook──▶ api (FastAPI :8020) ──▶ Redis (file + dédup) ──▶ worker (LangGraph)
                    vérifie la signature                              │
                                                                       ├─▶ GitHub API (lecture PR, revue, check)
                                                                       ├─▶ Ollama (modèle local, réseau interne)
                                                                       ├─▶ SMTP (alerte PR bloquante)
                                                                       └─▶ /data/audit.jsonl
```

Graphe (`agent/graph.py`) :

| Nœud | Rôle |
|---|---|
| `fetch_pr` | Lit la PR ; si un push plus récent existe → job obsolète, on s'arrête. Passe le check à « en cours ». |
| `load_diff` | Récupère les fichiers ; exclut lock files, générés, `vendor/`, supprimés, binaires ; applique les limites de taille. |
| `scan_secrets` | Détecte les secrets dans les lignes ajoutées (remarque **bloquante**) et les **masque avant** tout envoi au modèle. |
| `ai_review` | Découpe le diff en lots et demande au modèle des remarques JSON (schéma imposé). Un lot raté n'arrête pas la revue. |
| `decide` | Écarte les remarques inventées (fichier hors diff), sous le seuil de gravité, ou en double ; calcule le verdict. |
| `publish` | Revue GitHub avec commentaires en ligne + check run (ou statut de commit). |
| `alert` | Email si la PR est bloquante. |
| `audit` / `fail` | Journal d'audit ; en cas d'erreur, statut neutre (ne bloque pas la PR) et job en DLQ. |

### Verdict

| Verdict | Condition | Check GitHub |
|---|---|---|
| 🔴 **Bloquante** | au moins une remarque `critical` (dont tout secret détecté) | `failure` |
| 🟠 **À vérifier** | au moins une remarque `major`, ou revue incomplète (fichier trop gros, lot non analysé) | `neutral` |
| 🟢 **Prête** | sinon | `success` |

Pour que « bloquante » empêche réellement la fusion, ajoutez le check
`calipso-pr-review` aux règles de protection de branche : c'est un réglage
humain, pas une action du bot.

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

## Limites connues du prototype (à traiter dans les phases suivantes)

- Une nouvelle revue est publiée à chaque nouveau commit analysé ; pas encore
  de suppression des remarques déjà faites sur un commit précédent.
- Le scanner de secrets intégré est un garde-fou minimal ; gitleaks arrive avec
  les contrôles statiques.
- File simple (`LPUSH`/`BRPOP`) : si un worker meurt pendant une analyse, ce
  job est perdu (pas de DLQ). Passer à une file fiable (`BLMOVE` vers une liste
  « en cours » + reprise) avant la production.
- Les auteurs ne sont pas joints par email : GitHub ne fournit pas leur adresse.
  L'alerte va à `ALERT_EMAILS`.

## Feuille de route

| Semaines | Lot | État |
|---|---|---|
| 1-2 | Prototype : webhook, diff, revue IA, commentaire, verdict, alerte, audit | ✅ ce dépôt |
| 3-4 | Contrôles statiques : PHPStan, PHP-CS-Fixer, PHPUnit, composer audit, gitleaks, dans un conteneur isolé par PR (nœud `static_checks`) | à faire |
| 5-6 | Contexte : code lié, règles par dépôt (`.github/pr-review.md`), calibrage du verdict | à faire |
| 7-8 | Pilote sur un dépôt réel ; mesure de la pertinence (≥ 70 %), du délai (< 10 min) et du temps de revue | à faire |
