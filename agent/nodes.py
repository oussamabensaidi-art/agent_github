"""Nœuds du graphe de revue.

Chaque nœud reçoit les services via `config["configurable"]["services"]`.
Une exception dans un nœud est capturée par `guarded` : elle renseigne
`error` et le graphe bascule sur le nœud `fail` (statut neutre + audit).
"""
import functools
import logging
import time

from agent import prompts
from agent.diff import build_chunks, file_from_github, filter_files, is_incomplete_reason
from agent.notify import build_alert
from agent.review import (
    VERDICT_BLOCKING, VERDICT_CHECK, VERDICT_READY, VERDICT_TEXT,
    compute_verdict, finding_from_llm, render_comment, render_summary, validate_findings,
)
from agent.secrets_scan import scan_and_redact
from agent.state import ReviewState, Services

log = logging.getLogger("pr-review.graph")

CONCLUSION = {VERDICT_BLOCKING: "failure", VERDICT_CHECK: "neutral", VERDICT_READY: "success"}


def svc(config) -> Services:
    return config["configurable"]["services"]


def guarded(fn):
    @functools.wraps(fn)
    async def wrapper(state: ReviewState, config):
        try:
            return await fn(state, config)
        except Exception as e:  # noqa: BLE001 — toute erreur part dans `fail`
            log.exception("échec du nœud %s", fn.__name__)
            return {"error": f"{fn.__name__}: {type(e).__name__}: {e}"}
    return wrapper


@guarded
async def fetch_pr(state: ReviewState, config) -> dict:
    s = svc(config)
    pr = await s.github.get_pr(state["repo"], state["pr_number"])
    # Un push plus récent a déjà déclenché un autre job : celui-ci est obsolète.
    if pr["head"]["sha"] != state["head_sha"] or pr.get("state") != "open":
        return {"stale": True}
    check_id = None
    if not s.settings.DRY_RUN:
        check_id = await s.github.start_status(state["repo"], state["head_sha"], s.settings.CHECK_NAME)
    return {
        "stale": False,
        "pr_title": pr.get("title", ""),
        "pr_body": pr.get("body") or "",
        "pr_author": (pr.get("user") or {}).get("login", ""),
        "pr_url": pr.get("html_url", ""),
        "check_id": check_id,
    }


@guarded
async def load_diff(state: ReviewState, config) -> dict:
    s = svc(config)
    raw = await s.github.list_files(state["repo"], state["pr_number"])
    files, skipped = filter_files(
        [file_from_github(item) for item in raw],
        s.settings.ignore_patterns,
        s.settings.MAX_FILES,
        s.settings.MAX_FILE_CHANGED_LINES,
        s.settings.MAX_TOTAL_CHANGED_LINES,
    )
    incomplete = [f"`{p}` non analysé : {r}" for p, r in skipped if is_incomplete_reason(r)]
    return {"files": files, "skipped": skipped, "total_files": len(raw), "incomplete_reasons": incomplete}


@guarded
async def scan_secrets(state: ReviewState, config) -> dict:
    # Masque les secrets dans les patchs AVANT l'envoi au modèle.
    return {"secret_findings": scan_and_redact(state["files"])}


@guarded
async def ai_review(state: ReviewState, config) -> dict:
    s = svc(config)
    chunks = build_chunks(state["files"], s.settings.CHUNK_MAX_CHARS)
    system = prompts.system_prompt(s.rules)
    findings, failed = [], 0
    for i, chunk in enumerate(chunks, start=1):
        user = prompts.user_prompt(state.get("pr_title", ""), state.get("pr_body", ""), chunk, i, len(chunks))
        try:
            raw = await s.llm.review(system, user)
        except Exception as e:  # noqa: BLE001 — un lot raté n'arrête pas la revue
            log.warning("lot %s/%s en échec : %s", i, len(chunks), e)
            failed += 1
            continue
        findings += [f for f in (finding_from_llm(r) for r in raw) if f]
    incomplete = list(state.get("incomplete_reasons", []))
    if failed:
        incomplete.append(f"{failed} lot(s) sur {len(chunks)} n'ont pas pu être analysés par le modèle")
    return {"llm_findings": findings, "chunks_total": len(chunks), "chunks_failed": failed,
            "incomplete_reasons": incomplete}


@guarded
async def decide(state: ReviewState, config) -> dict:
    s = svc(config)
    commentable = {f.path: f.commentable for f in state["files"]}
    findings = validate_findings(
        state.get("secret_findings", []) + state.get("llm_findings", []),
        commentable,
        s.settings.MIN_COMMENT_SEVERITY,
    )
    incomplete = state.get("incomplete_reasons", [])
    verdict = compute_verdict(findings, incomplete)
    inline_count = min(sum(1 for f in findings if f.inline), s.settings.MAX_INLINE_COMMENTS)
    summary = render_summary(verdict, findings, inline_count, state.get("skipped", []),
                             incomplete, s.llm.model, state["head_sha"])
    return {"findings": findings, "verdict": verdict, "summary": summary, "inline_count": inline_count}


@guarded
async def publish(state: ReviewState, config) -> dict:
    s = svc(config)
    if s.settings.DRY_RUN:
        return {"published": False}
    findings = state["findings"]
    comments = [
        {"path": f.path, "line": f.line, "side": "RIGHT", "body": render_comment(f)}
        for f in [f for f in findings if f.inline][: state["inline_count"]]
    ]
    fallback = render_summary(state["verdict"], findings, 0, state.get("skipped", []),
                              state.get("incomplete_reasons", []), s.llm.model, state["head_sha"])
    await s.github.create_review(state["repo"], state["pr_number"], state["head_sha"],
                                 state["summary"], comments, fallback)
    counts = f"{len(findings)} remarque(s)"
    await s.github.finish_status(
        state["repo"], state["head_sha"], s.settings.CHECK_NAME, state.get("check_id"),
        CONCLUSION[state["verdict"]], f"{VERDICT_TEXT[state['verdict']]} — {counts}", state["summary"],
    )
    return {"published": True}


@guarded
async def alert(state: ReviewState, config) -> dict:
    s = svc(config)
    if state["verdict"] != VERDICT_BLOCKING or s.settings.DRY_RUN:
        return {"alert_sent": False}
    if not s.mailer.configured or not s.settings.alert_emails:
        log.warning("PR bloquante mais SMTP/ALERT_EMAILS non configurés : pas d'alerte")
        return {"alert_sent": False}
    msg = build_alert(s.settings.ALERT_FROM, s.settings.alert_emails, state["repo"], state["pr_number"],
                      state.get("pr_title", ""), state.get("pr_author", ""), state.get("pr_url", ""),
                      state["findings"])
    try:
        await s.mailer.send(msg)
    except Exception:  # noqa: BLE001 — la revue est publiée ; un mail raté ne doit pas la défaire
        log.exception("échec d'envoi de l'alerte email")
        return {"alert_sent": False}
    return {"alert_sent": True}


def _audit_record(state: ReviewState, s: Services, status: str) -> dict:
    findings = state.get("findings", [])
    return {
        "status": status,
        "delivery_id": state.get("delivery_id"),
        "repo": state.get("repo"),
        "pr_number": state.get("pr_number"),
        "head_sha": state.get("head_sha"),
        "files_total": state.get("total_files"),
        "files_reviewed": len(state.get("files", [])),
        "files_skipped": len(state.get("skipped", [])),
        "secrets_found": len(state.get("secret_findings", [])),
        "findings": {sev: sum(1 for f in findings if f.severity == sev)
                     for sev in ("critical", "major", "minor", "info")},
        "chunks_total": state.get("chunks_total"),
        "chunks_failed": state.get("chunks_failed"),
        "verdict": state.get("verdict"),
        "published": state.get("published", False),
        "alert_sent": state.get("alert_sent", False),
        "llm_model": getattr(s.llm, "model", None),
        "llm_host": getattr(s.llm, "host", None),
        "dry_run": s.settings.DRY_RUN,
        "duration_s": round(time.time() - state.get("started_at", time.time()), 1),
        "error": state.get("error"),
    }


async def audit(state: ReviewState, config) -> dict:
    s = svc(config)
    status = "stale" if state.get("stale") else "ok"
    s.audit.write(_audit_record(state, s, status))
    return {}


async def fail(state: ReviewState, config) -> dict:
    """Échec : statut neutre sur la PR (sans bloquer), audit, puis DLQ côté worker."""
    s = svc(config)
    if not s.settings.DRY_RUN and state.get("head_sha"):
        try:
            await s.github.finish_status(
                state["repo"], state["head_sha"], s.settings.CHECK_NAME, state.get("check_id"),
                "neutral", "Revue automatique en échec — relecture humaine requise",
                "L'analyse automatique n'a pas pu aboutir. L'incident est journalisé.",
            )
        except Exception:  # noqa: BLE001
            log.exception("impossible de mettre à jour le statut après échec")
    s.audit.write(_audit_record(state, s, "error"))
    return {}
