"""Agent de revue des PR — configuration (pydantic-settings).

Même pattern que les agents #64 / #67 : tous les secrets viennent de
l'environnement / .env, jamais en dur.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Webhook GitHub entrant ---
    GITHUB_WEBHOOK_SECRET: str = ""
    # Actions pull_request qui déclenchent une analyse.
    TRIGGER_ACTIONS: str = "opened,synchronize,reopened,ready_for_review"
    SKIP_DRAFTS: bool = True

    # --- Authentification GitHub ---
    # Mode "app" (cible) : GitHub App, droits minimaux, check runs.
    # Mode "token" (dev) : PAT d'un compte bot, statuts de commit.
    GITHUB_AUTH_MODE: str = "app"
    GITHUB_API_URL: str = "https://api.github.com"
    GITHUB_APP_ID: str = ""
    GITHUB_APP_PRIVATE_KEY_PATH: str = "/run/secrets/github_app.pem"
    GITHUB_TOKEN: str = ""
    CHECK_NAME: str = "calipso-pr-review"

    # --- Redis (file d'attente) ---
    REDIS_URL: str = "redis://localhost:6379/0"
    QUEUE_KEY: str = "prreview:queue"
    DLQ_KEY: str = "prreview:dlq"
    DEDUP_TTL_SECONDS: int = 86400

    # --- Modèle IA local (Ollama) ---
    LLM_BASE_URL: str = "http://localhost:11434"
    LLM_MODEL: str = "qwen2.5-coder:7b"
    LLM_TIMEOUT_SECONDS: float = 240.0
    LLM_NUM_CTX: int = 16384
    # Garde-fou "aucun code ne sort de l'infra" : hôtes LLM autorisés.
    # Ajouter un hôte cloud ici = décision de conformité explicite.
    LLM_ALLOWED_HOSTS: str = "localhost,127.0.0.1,ollama,host.docker.internal"

    # --- Filtrage et limites de taille ---
    IGNORE_PATTERNS: str = (
        "composer.lock,symfony.lock,package-lock.json,yarn.lock,pnpm-lock.yaml,"
        "poetry.lock,Pipfile.lock,*.min.js,*.min.css,*.map,"
        "vendor/*,node_modules/*,var/*,public/build/*,dist/*,build/*,*.generated.*"
    )
    MAX_FILES: int = 100
    MAX_FILE_CHANGED_LINES: int = 1500
    MAX_TOTAL_CHANGED_LINES: int = 4000
    CHUNK_MAX_CHARS: int = 12000

    # --- Revue & verdict ---
    RULES_PATH: str = "rules/default.md"
    # Filtre anti-faux-positifs : sous ce niveau, pas de commentaire.
    MIN_COMMENT_SEVERITY: str = "minor"
    MAX_INLINE_COMMENTS: int = 30

    # --- Alerte email (PR bloquante) ---
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_STARTTLS: bool = True
    ALERT_FROM: str = "pr-review-bot@calipso-assurances.fr"
    ALERT_EMAILS: str = ""

    # --- Journalisation ---
    AUDIT_LOG_PATH: str = "data/audit.jsonl"

    # --- Divers ---
    # true : analyse complète, mais rien n'est publié sur GitHub ni envoyé.
    DRY_RUN: bool = False

    @staticmethod
    def _csv(value: str) -> list[str]:
        return [v.strip() for v in value.split(",") if v.strip()]

    @property
    def trigger_actions(self) -> list[str]:
        return self._csv(self.TRIGGER_ACTIONS)

    @property
    def ignore_patterns(self) -> list[str]:
        return self._csv(self.IGNORE_PATTERNS)

    @property
    def llm_allowed_hosts(self) -> list[str]:
        return self._csv(self.LLM_ALLOWED_HOSTS)

    @property
    def alert_emails(self) -> list[str]:
        return self._csv(self.ALERT_EMAILS)


settings = Settings()
