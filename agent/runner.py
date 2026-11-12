"""Construction des services et exécution d'une analyse (worker et CLI).

L'analyse est exécutée en flux (`graph.astream`) : les événements émis par les
nœuds sont transmis au journal d'événements au fil de l'eau ; l'état final
est le dernier état complet du flux "values".
"""
import logging
import time
import uuid

from agent.audit import AuditLog
from agent.checks import CheckerClient
from agent.github import GitHubAppAuth, GitHubClient
from agent.graph import review_graph
from agent.llm import OllamaClient, OpenRouterClient, Qwen3ApiClient
from agent.notify import Mailer
from agent.nodes import run_status
from agent.prompts import load_rules
from agent.review import rules_version
from agent.state import Services
from store import NullStore

log = logging.getLogger("pr-review.runner")

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
    auth = _app_auth
    return GitHubClient(token, settings.GITHUB_API_URL, use_checks=True,
                        refresh_token=lambda: auth.token(installation_id, force=True))


def build_llm(settings):
    if settings.LLM_PROVIDER == "openrouter":
        return OpenRouterClient(settings.OPENROUTER_MODEL, settings.OPENROUTER_API_KEY,
                                settings.llm_allowed_hosts, settings.LLM_TIMEOUT_SECONDS)
    if settings.LLM_PROVIDER == "qwen3api":
        return Qwen3ApiClient(settings.QWEN3_API_URL, settings.QWEN3_ENDPOINT, settings.QWEN3_API_KEY,
                              settings.llm_allowed_hosts, settings.LLM_TIMEOUT_SECONDS,
                              settings.QWEN3_MAX_TOKENS, settings.QWEN3_MAX_THINKING_TOKENS,
                              context_tokens=settings.QWEN3_CONTEXT_TOKENS)
    return OllamaClient(settings.LLM_BASE_URL, settings.LLM_MODEL, settings.llm_allowed_hosts,
                        settings.LLM_TIMEOUT_SECONDS, settings.LLM_NUM_CTX)


def build_services(settings, github, store=None) -> Services:
    rules = load_rules(settings.RULES_PATH)
    store = store or NullStore(settings.PUBLISH_ENABLED)
    return Services(
        github=github,
        llm=build_llm(settings),
        mailer=Mailer(settings.SMTP_HOST, settings.SMTP_PORT, settings.SMTP_USER,
                      settings.SMTP_PASSWORD, settings.SMTP_STARTTLS),
        audit=AuditLog(settings.AUDIT_LOG_PATH),
        settings=settings,
        rules=rules,
        rules_version=rules_version(rules),
        controls=store,
        events=store,
        checker=(CheckerClient(settings.CHECKER_URL, settings.CHECKER_TIMEOUT_SECONDS)
                 if settings.CHECKS_ENABLED and settings.CHECKER_URL else None),
    )


async def run_review(job: dict, services: Services) -> dict:
    events = services.events or NullStore()
    run_id = job.get("run_id") or uuid.uuid4().hex
    started = time.time()
    queued_at = job.get("queued_at")
    queue_ms = round((started - queued_at) * 1000) if queued_at else None
    state = {**job, "run_id": run_id, "started_at": started}
    if not services.rules_version:
        services.rules_version = rules_version(services.rules)
    controls = services.controls
    publishing = await controls.publishing_enabled() if controls else services.settings.PUBLISH_ENABLED

    await events.emit(run_id, "run_started", {
        "repo": job["repo"], "pr_number": job["pr_number"], "head_sha": job["head_sha"],
        "delivery_id": job.get("delivery_id"), "queued_at": queued_at, "queue_ms": queue_ms,
        "model": getattr(services.llm, "model", None), "rules_version": services.rules_version,
        "pilot_mode": services.settings.PILOT_MODE, "publishing_enabled": publishing,
        "dry_run": services.settings.DRY_RUN, "concurrency": services.settings.LLM_CONCURRENCY,
    }, started)

    final: dict = state
    async for mode, payload in review_graph.astream(
            state, config={"configurable": {"services": services}}, stream_mode=["custom", "values"]):
        if mode == "custom":
            await events.emit(run_id, payload["type"], payload["data"], payload["ts"])
        else:
            final = payload

    finished = time.time()
    run_ms = round((finished - started) * 1000)
    findings = final.get("findings", [])
    await events.emit(run_id, "run_finished", {
        "status": run_status(final), "verdict": final.get("verdict"),
        "run_ms": run_ms, "queue_ms": queue_ms, "total_ms": run_ms + (queue_ms or 0),
        "chunks_total": final.get("chunks_total"), "chunks_failed": final.get("chunks_failed"),
        "findings_count": len(findings),
        "cost_usd": round(getattr(services.llm, "cost_usd", 0.0), 6) or None,
        "incomplete_reasons": final.get("incomplete_reasons", []),
        "skipped": [{"path": p, "reason": r} for p, r in final.get("skipped", [])],
        "published": final.get("published", False), "publish_skipped": final.get("publish_skipped"),
        "superseded": final.get("superseded", False), "error": final.get("error"),
    }, finished)
    return final
