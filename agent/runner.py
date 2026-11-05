"""Construction des services et exécution d'une analyse (worker et CLI)."""
import time

from agent.audit import AuditLog
from agent.github import GitHubAppAuth, GitHubClient
from agent.graph import review_graph
from agent.llm import OllamaClient
from agent.notify import Mailer
from agent.prompts import load_rules
from agent.state import Services

_app_auth: GitHubAppAuth | None = None


async def github_client_for(settings, installation_id: int | None) -> GitHubClient:
    global _app_auth
    if settings.GITHUB_AUTH_MODE == "token":
        return GitHubClient(settings.GITHUB_TOKEN, settings.GITHUB_API_URL, use_checks=False)
    if not installation_id:
        raise ValueError("mode app : installation_id absent du webhook")
    if _app_auth is None:
        _app_auth = GitHubAppAuth(settings.GITHUB_APP_ID, settings.GITHUB_APP_PRIVATE_KEY_PATH,
                                  settings.GITHUB_API_URL)
    token = await _app_auth.token(installation_id)
    return GitHubClient(token, settings.GITHUB_API_URL, use_checks=True)


def build_services(settings, github) -> Services:
    return Services(
        github=github,
        llm=OllamaClient(settings.LLM_BASE_URL, settings.LLM_MODEL, settings.llm_allowed_hosts,
                         settings.LLM_TIMEOUT_SECONDS, settings.LLM_NUM_CTX),
        mailer=Mailer(settings.SMTP_HOST, settings.SMTP_PORT, settings.SMTP_USER,
                      settings.SMTP_PASSWORD, settings.SMTP_STARTTLS),
        audit=AuditLog(settings.AUDIT_LOG_PATH),
        settings=settings,
        rules=load_rules(settings.RULES_PATH),
    )


async def run_review(job: dict, services: Services) -> dict:
    state = {**job, "started_at": time.time()}
    return await review_graph.ainvoke(state, config={"configurable": {"services": services}})
