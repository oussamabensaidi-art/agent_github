# Déploiement de l'agent de revue PR — guide et liste de contrôle

Ce document **prépare** le déploiement. Le déploiement lui-même est fait par une
personne de l'équipe, après validation de Hicham. Rien ici n'a été exécuté sur
un serveur Calipso.

## 1. Décisions à valider avant de commencer

| # | Décision | Qui |
|---|---|---|
| D1 | Serveur cible (Docker ≥ 24, 4 vCPU / 8 Go suffisent hors modèle) et nom DNS | Hicham / infra |
| D2 | Accès au modèle Qwen3 par le **réseau privé** (pas l'adresse publique en HTTP utilisée pour les tests) | infra |
| D3 | Certificat HTTPS : proxy de l'infrastructure, ou service `proxy` fourni (Caddy) | infra |
| D4 | GitHub App de production sur l'organisation Calipso, et dépôts concernés par le pilote | Hicham |
| D5 | Destinataires des alertes « PR bloquante » et serveur SMTP | Hicham |
| D6 | Comptes de l'interface (administrateurs / lecteurs) | Hicham |
| D7 | Protection de branche : rendre le check `calipso-pr-review` obligatoire, ou non pendant le pilote | Hicham |

Aucun service externe n'est requis en production : pas de relais smee.io, pas
d'OpenRouter, pas de LangSmith. Toute exception demande une validation préalable.

## 2. Ce qui change par rapport au poste de test

| Poste de test | Production |
|---|---|
| Webhooks relayés par smee.io | GitHub appelle directement `https://<domaine>/webhook/github` |
| Modèle en HTTP sur IP publique | Modèle sur réseau privé, hôte listé dans `LLM_ALLOWED_HOSTS` |
| Interface en HTTP sur localhost | HTTPS, `UI_COOKIE_SECURE=true` |
| Mailpit | SMTP Calipso |
| GitHub App de test, organisation `test-agent-revue` | GitHub App de production, organisation Calipso |
| `docker-compose.github.yml` | `docker-compose.prod.yml` |

## 3. GitHub App de production

Créer une **nouvelle** App (ne pas réutiliser celle de test) sur l'organisation Calipso :

- Permissions dépôt : **Checks** lecture/écriture, **Pull requests** lecture/écriture,
  **Contents** lecture seule, **Metadata** lecture seule. Rien d'autre.
- Événement : **Pull request**.
- Webhook : actif, URL `https://<domaine>/webhook/github`, secret aléatoire (64 caractères hex).
- Installation : « Only select repositories », les dépôts du pilote uniquement.
- Clé privée : générée une fois, déposée sur le serveur dans `secrets/github_app.pem`
  (droits `600`), jamais dans un dépôt, un ticket ou une messagerie.

## 4. Configuration du serveur

1. Copier le dépôt de l'agent sur le serveur (sans `.env`, sans `secrets/`).
2. Créer `.env` à partir de `.env.example`. Valeurs propres à la production :

   | Variable | Valeur |
   |---|---|
   | `GITHUB_AUTH_MODE` | `app` |
   | `GITHUB_APP_ID` | identifiant de l'App de production |
   | `GITHUB_WEBHOOK_SECRET` | le secret saisi dans l'App |
   | `LLM_PROVIDER`, `QWEN3_API_URL`, `QWEN3_API_KEY`, `QWEN3_ENDPOINT=chat` | modèle sur réseau privé |
   | `QWEN3_CONTEXT_TOKENS=8192`, `CHUNK_MAX_CHARS=8000` | fenêtre du modèle servi |
   | `LLM_ALLOWED_HOSTS` | l'hôte privé du modèle, rien d'autre |
   | `POSTGRES_PASSWORD` | mot de passe fort, propre à ce serveur |
   | `UI_USERS` | comptes créés avec `python -m ui.auth` (empreintes scrypt) |
   | `UI_PUBLIC_URL` | `https://<domaine>/ui` |
   | `PUBLIC_HOST` | `<domaine>` (si le service `proxy` est utilisé) |
   | `SMTP_*`, `ALERT_EMAILS` | SMTP Calipso, destinataires validés |
   | `LANGSMITH_TRACING`, `LANGCHAIN_TRACING_V2` | `false` |
   | `DRY_RUN` | `true` au premier démarrage |

3. Déposer `secrets/github_app.pem`.
4. Pare-feu : seuls 443 (et 80 pour la redirection) sont ouverts en entrée. Les ports
   8020, 5432, 6379, 8090 et 11434 ne doivent pas être joignables de l'extérieur.

## 5. Démarrage

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Avec le proxy fourni : ajouter `--profile proxy`. Plusieurs analyses en parallèle :
ajouter `--scale worker=3` (mesuré : p95 de 2 min 22 pour 12 PR simultanées).

## 6. Vérifications, dans l'ordre

1. `docker compose ps` : `api`, `worker`, `checker`, `db`, `redis` en marche.
2. `https://<domaine>/health` répond ; `https://<domaine>/ui` affiche la connexion.
3. Depuis l'extérieur, `http://<serveur>:8020`, `:5432`, `:6379` sont **fermés**.
4. Dans l'App GitHub → Advanced → Recent Deliveries : la livraison « ping » est en 2xx.
5. Interface : le modèle affiché est le bon ; bandeau « Lecture seule (DRY_RUN) » visible.
6. Ouvrir une PR de test sur un dépôt du pilote : l'analyse apparaît dans l'interface,
   **rien** n'est écrit sur GitHub (lecture seule).
7. Relire cette analyse (remarques, contrôles, durée). Si elle est correcte :
   passer `DRY_RUN=false`, relancer le worker, garder `PILOT_MODE=true`.
8. Nouvelle PR de test : check `calipso-pr-review` et revue « commentaire » publiés,
   lien « Détails » vers l'interface en HTTPS.
9. PR de test avec un faux secret : verdict « Bloquante », email reçu par les destinataires.
10. Couper puis réactiver l'interrupteur de publication dans l'interface : effet immédiat.

## 7. Exploitation

- **Arrêt d'urgence** : interrupteur de publication dans l'interface (administrateur).
  Les analyses continuent, plus rien n'est écrit sur GitHub ni envoyé.
- **Sauvegardes** : volume `pgdata` (journal des analyses, avis, réglages) —
  `docker compose exec db pg_dump -U prreview prreview` quotidien ; volume `audit`.
- **Surveillance** : sonde `GET /health` ; page Statistiques (DLQ, taux de lots en échec,
  durée p95) ; journaux `docker compose logs worker`.
- **Mise à jour** : `git pull` puis la commande du § 5. Un job en cours est repris par un
  autre worker (file fiable) ; un check resté « en cours » est clos à la réactivation.
- **Rotation** : clé privée de l'App, secret du webhook et `QWEN3_API_KEY` en cas de doute,
  et au moins une fois par an.
- **Retour arrière** : couper l'interrupteur, puis `docker compose ... down` ;
  désinstaller l'App GitHub des dépôts retire tout accès.

## 8. Pilote supervisé

- `PILOT_MODE=true` : les remarques de l'IA sont des avis. Seuls les contrôles
  déterministes bloquent (secret, dépendance vulnérable grave, CI en échec).
- L'équipe note chaque remarque dans l'interface (« Pertinente » / « Fausse alerte »).
- Objectifs à suivre sur la page Statistiques : pertinence ≥ 70 %, durée < 10 min.
- La levée du mode pilote (l'IA peut bloquer seule) est une décision collective,
  prise sur ces chiffres.

## 9. Ce qui n'est pas couvert par ce guide

- Dimensionnement et exploitation du serveur du modèle (GPU).
- Haute disponibilité (un seul serveur, redémarrage automatique des conteneurs).
- Intégration à la supervision et à la sauvegarde centralisées de Calipso.
