"""Nœuds du graphe de revue.

Chaque nœud reçoit les services via `config["configurable"]["services"]`.
Le décorateur `node` émet node_started / node_finished (avec durée) et, pour
les nœuds du pipeline, capture toute exception : elle renseigne `error` et le
graphe bascule sur le nœud `fail`.

Toute écriture vers l'extérieur (check, revue, statut, email) passe par
`blocked_reason`, qui relit l'interrupteur de publication juste avant.
"""
import asyncio
import functools
import logging
import re
import time

from agent import prompts
from agent.checks import changed_map, evaluate_ci, tool_findings, tool_incomplete
from agent.diff import FileDiff, build_chunks, excerpt, file_from_github, filter_files, is_incomplete_reason
from agent.events import emit
from agent.notify import build_alert
from agent.review import (
    CHECK_CONCLUSION, OUTCOME_FAILED, OUTCOME_SUPERSEDED, STATUS_STATE, VERDICT_BLOCKING, VERDICT_TEXT,
    Finding, compute_verdict, finding_from_llm, render_comment, render_summary, validate_findings_detailed,
)
from agent.secrets_scan import redact_text, scan_and_redact, scan_pr_text
from agent.state import ReviewState, Services

log = logging.getLogger("pr-review.graph")

CHUNK_FILE_RE = re.compile(r"^### (.+) \(\w+\)$", re.M)


def svc(config) -> Services:
    return config["configurable"]["services"]


def details_url(s: Services, state: ReviewState) -> str:
    base = (s.settings.UI_PUBLIC_URL or "").rstrip("/")
    return f"{base}/runs/{state['run_id']}" if base and state.get("run_id") else ""


async def blocked_reason(s: Services) -> str | None:
    """None si l'agent peut écrire vers GitHub / SMTP, sinon la raison."""
    if s.settings.DRY_RUN:
        return "dry_run"
    enabled = await s.controls.publishing_enabled() if s.controls else s.settings.PUBLISH_ENABLED
    return None if enabled else "kill_switch"


def finding_event(f: Finding, files: dict[str, FileDiff]) -> dict:
    fd = files.get(f.path)
    return {**f.to_dict(), "excerpt": excerpt(fd, f.line) if fd else []}


def node(guard: bool = True):
    def deco(fn):
        @functools.wraps(fn)
        async def wrapper(state: ReviewState, config):
            name = fn.__name__
            t0 = time.perf_counter()
            emit("node_started", node=name)
            try:
                out = await fn(state, config)
            except Exception as e:  # noqa: BLE001 — toute erreur part dans `fail`
                if not guard:
                    raise
                log.exception("échec du nœud %s", name)
                out = {"error": redact_text(f"{name}: {type(e).__name__}: {e}")[0]}
                emit("error", node=name, message=out["error"][:500])
            status = "error" if out.get("error") else "stale" if out.get("stale") else "ok"
            emit("node_finished", node=name, status=status,
                 duration_ms=round((time.perf_counter() - t0) * 1000))
            return out
        return wrapper
    return deco


@node()
async def fetch_pr(state: ReviewState, config) -> dict:
    s = svc(config)
    pr = await s.github.get_pr(state["repo"], state["pr_number"])
    # Un push plus récent a déjà déclenché un autre job : celui-ci est obsolète.
    if pr["head"]["sha"] != state["head_sha"] or pr.get("state") != "open":
        emit("stale", current_sha=pr["head"]["sha"], pr_state=pr.get("state"))
        return {"stale": True}
    check_id = None
    reason = await blocked_reason(s)
    if reason:
        emit("publication_skipped", reason=reason, step="check en cours")
    else:
        check_id = await s.github.start_status(state["repo"], state["head_sha"], s.settings.CHECK_NAME,
                                               details_url(s, state))
    # Titre et description NON masqués à ce stade : ils ne sont émis qu'après scan_secrets.
    emit("pr_fetched", author=(pr.get("user") or {}).get("login", ""), url=pr.get("html_url", ""))
    return {
        "stale": False,
        "pr_title": pr.get("title", ""),
        "pr_body": pr.get("body") or "",
        "pr_author": (pr.get("user") or {}).get("login", ""),
        "pr_url": pr.get("html_url", ""),
        "check_id": check_id,
    }


@node()
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
    emit("diff_loaded",
         files=[{"path": f.path, "status": f.status, "additions": f.additions, "deletions": f.deletions}
                for f in files],
         skipped=[{"path": p, "reason": r, "incomplete": is_incomplete_reason(r)} for p, r in skipped],
         total=len(raw))
    return {"files": files, "skipped": skipped, "total_files": len(raw), "incomplete_reasons": incomplete}


@node()
async def scan_secrets(state: ReviewState, config) -> dict:
    # Masque les secrets des patchs ET du texte de la PR AVANT l'envoi au modèle.
    found = scan_and_redact(state["files"])
    title, body, in_text = scan_pr_text(state.get("pr_title", ""), state.get("pr_body", ""))
    findings = found + in_text
    files = {f.path: f for f in state["files"]}
    for k, f in enumerate(findings, start=1):
        f.id = f"s{k}"
        emit("finding", **finding_event(f, files))
    emit("pr_info", title=title, author=state.get("pr_author", ""), url=state.get("pr_url", ""))
    emit("secrets_scanned", count=len(findings))
    return {"secret_findings": findings, "pr_title": title, "pr_body": body}


@node()
async def ai_review(state: ReviewState, config) -> dict:
    s = svc(config)
    chunks = build_chunks(state["files"], s.settings.CHUNK_MAX_CHARS)
    system = prompts.system_prompt(s.rules)
    files = {f.path: f for f in state["files"]}
    concurrency = max(1, s.settings.LLM_CONCURRENCY)
    emit("chunks_planned", total=len(chunks), concurrency=concurrency,
         chunks=[{"index": i, "files": CHUNK_FILE_RE.findall(c), "chars": len(c)}
                 for i, c in enumerate(chunks, start=1)])
    sem = asyncio.Semaphore(concurrency)

    async def review_chunk(i: int, chunk: str) -> list[Finding] | None:
        async with sem:
            t0 = time.perf_counter()
            emit("chunk_started", index=i)
            user = prompts.user_prompt(state.get("pr_title", ""), state.get("pr_body", ""), chunk, i, len(chunks))
            try:
                raw = await s.llm.review(system, user)
            except Exception as e:  # noqa: BLE001 — un lot raté n'arrête pas la revue
                log.warning("lot %s/%s en échec : %s", i, len(chunks), e)
                emit("chunk_failed", index=i, duration_ms=round((time.perf_counter() - t0) * 1000),
                     error=f"{type(e).__name__}: {e}"[:300])
                return None
            found = []
            for k, r in enumerate(raw, start=1):
                f = finding_from_llm(r)
                if f:
                    f.id, f.chunk = f"c{i}-{k}", i
                    found.append(f)
                    emit("finding", **finding_event(f, files))
            emit("chunk_finished", index=i, duration_ms=round((time.perf_counter() - t0) * 1000),
                 findings=len(found))
            return found

    results = await asyncio.gather(*(review_chunk(i, c) for i, c in enumerate(chunks, start=1)))
    findings = [f for r in results if r for f in r]
    failed = sum(1 for r in results if r is None)
    incomplete = list(state.get("incomplete_reasons", []))
    if failed:
        incomplete.append(f"{failed} lot(s) sur {len(chunks)} n'ont pas pu être analysés par le modèle")
    return {"llm_findings": findings, "chunks_total": len(chunks), "chunks_failed": failed,
            "incomplete_reasons": incomplete}


async def _run_checker(s: Services, state: ReviewState, changed: dict) -> list[dict]:
    t0 = time.perf_counter()
    emit("check_tool", tool="checker", status="running")
    try:
        archive = await s.github.download_tarball(state["repo"], state["head_sha"],
                                                  s.settings.CHECK_MAX_ARCHIVE_MB * 1024 * 1024)
        return await s.checker.check(archive, changed, s.settings.PHPSTAN_LEVEL)
    except Exception as e:  # noqa: BLE001 — checker indisponible : incomplet, jamais vert
        log.warning("contrôles statiques indisponibles : %s", e)
        return [{"name": "checker", "status": "error", "findings": [],
                 "duration_ms": round((time.perf_counter() - t0) * 1000),
                 "message": redact_text(f"{type(e).__name__}: {e}")[0][:300]}]


def _ci_done(st: str, elapsed: float, settings) -> bool:
    return (st == "done" or (st == "pending" and elapsed >= settings.CI_WAIT_SECONDS)
            or (st == "none" and elapsed >= settings.CI_GRACE_SECONDS))


async def _wait_ci(s: Services, state: ReviewState) -> dict:
    """Attend la fin de la CI du dépôt (sondage), sans jamais lever d'exception."""
    t0 = time.perf_counter()
    st, ci_findings, ci_incomplete, summary = "none", [], [], []
    try:
        while True:
            runs = await s.github.list_check_runs(state["repo"], state["head_sha"])
            st, ci_findings, ci_incomplete, summary = evaluate_ci(runs, s.settings.CHECK_NAME,
                                                                  s.settings.ci_check_names)
            if _ci_done(st, time.perf_counter() - t0, s.settings):
                break
            emit("check_tool", tool="ci", status="pending", runs=summary)
            await asyncio.sleep(s.settings.CI_POLL_SECONDS)
    except Exception as e:  # noqa: BLE001
        log.warning("lecture de la CI impossible : %s", e)
        st, ci_incomplete = "error", [f"CI du dépôt : lecture impossible ({type(e).__name__})"]
    duration = round((time.perf_counter() - t0) * 1000)
    if st == "pending":
        ci_incomplete = [f"CI du dépôt non terminée après {s.settings.CI_WAIT_SECONDS} s : tests non vérifiés"]
    if st == "none" and s.settings.CI_REQUIRED:
        ci_incomplete = ["aucune CI sur ce dépôt : tests non exécutés"]
    status = {"done": "failed" if ci_findings else ("error" if ci_incomplete else "ok"),
              "none": "error" if s.settings.CI_REQUIRED else "skipped",
              "pending": "pending", "error": "error"}[st]
    return {"name": "ci", "status": status, "duration_ms": duration, "runs": summary,
            "message": "aucune CI détectée" if st == "none" else "",
            "_findings": ci_findings, "_incomplete": ci_incomplete}


@node()
async def static_checks(state: ReviewState, config) -> dict:
    """Contrôles déterministes, en parallèle de ai_review : checker isolé + CI du dépôt.

    Ne renvoie jamais `error` (branche parallèle) : une panne rend l'analyse incomplète."""
    s = svc(config)
    if s.checker is None:
        return {"static_findings": [], "static_incomplete": [], "checks": []}
    changed = changed_map(state["files"], state.get("skipped", []))
    jobs = [_run_checker(s, state, changed)]
    if s.settings.CI_ENABLED:
        jobs.append(_wait_ci(s, state))
    results = await asyncio.gather(*jobs)
    tools = results[0]
    ci = results[1] if len(results) > 1 else None

    findings = tool_findings(tools) + (ci["_findings"] if ci else [])
    if tools and tools[0]["name"] == "checker":
        incomplete = ["contrôles statiques indisponibles : " + tools[0].get("message", "")[:160]]
    else:
        incomplete = tool_incomplete(tools)
    if ci:
        incomplete += ci["_incomplete"]
    files = {f.path: f for f in state["files"]}
    for k, f in enumerate(findings, start=1):
        f.id = f"t{k}"
        emit("finding", **finding_event(f, files))
    checks = []
    for t in tools + ([ci] if ci else []):
        entry = {"name": t["name"], "status": t["status"], "duration_ms": t.get("duration_ms", 0),
                 "count": sum(1 for f in findings if f.source == t["name"]),
                 "message": redact_text(t.get("message") or "")[0][:300]}
        if t.get("runs"):
            entry["runs"] = t["runs"]
        checks.append(entry)
        emit("check_tool", tool=entry["name"], **{k: v for k, v in entry.items() if k != "name"})
    emit("checks_finished", count=len(findings), incomplete=incomplete)
    return {"static_findings": findings, "static_incomplete": incomplete, "checks": checks}


@node()
async def decide(state: ReviewState, config) -> dict:
    s = svc(config)
    if state.get("error"):
        return {}  # la revue IA a échoué : routage vers `fail`
    commentable = {f.path: f.commentable for f in state["files"]}
    findings, dropped = validate_findings_detailed(
        state.get("secret_findings", []) + state.get("static_findings", []) + state.get("llm_findings", []),
        commentable,
        s.settings.MIN_COMMENT_SEVERITY,
    )
    emit("findings_validated", kept=[f.id for f in findings],
         dropped=[{"id": f.id, "reason": r} for f, r in dropped])
    incomplete = list(state.get("incomplete_reasons", [])) + list(state.get("static_incomplete", []))
    pilot = s.settings.PILOT_MODE
    verdict = compute_verdict(findings, incomplete, pilot)
    inline_count = min(sum(1 for f in findings if f.inline), s.settings.MAX_INLINE_COMMENTS)
    summary = render_summary(verdict, findings, inline_count, state.get("skipped", []),
                             incomplete, s.llm.model, state["head_sha"], s.rules_version, pilot,
                             details_url(s, state), state.get("checks"))
    counts = {sev: sum(1 for f in findings if f.severity == sev) for sev in ("critical", "major", "minor", "info")}
    emit("verdict", verdict=verdict, counts=counts, incomplete_reasons=incomplete,
         rules_version=s.rules_version, pilot_mode=pilot)
    return {"findings": findings, "verdict": verdict, "summary": summary, "inline_count": inline_count,
            "incomplete_reasons": incomplete}


@node()
async def publish(state: ReviewState, config) -> dict:
    s = svc(config)
    reason = await blocked_reason(s)
    if reason:
        emit("publication_skipped", reason=reason, step="revue et check")
        return {"published": False, "publish_skipped": reason}

    # Dernière vérification : si un commit plus récent est arrivé pendant
    # l'analyse, on ne publie rien sur la PR (le check de ce commit est clos).
    pr = await s.github.get_pr(state["repo"], state["pr_number"])
    if pr["head"]["sha"] != state["head_sha"] or pr.get("state") != "open":
        await s.github.finish_status(
            state["repo"], state["head_sha"], s.settings.CHECK_NAME, state.get("check_id"),
            OUTCOME_SUPERSEDED, VERDICT_TEXT[OUTCOME_SUPERSEDED],
            "Un commit plus récent a été poussé pendant l'analyse : ce résultat n'est pas publié.",
            details_url(s, state))
        emit("superseded", current_sha=pr["head"]["sha"], pr_state=pr.get("state"))
        return {"published": False, "superseded": True}

    findings = state["findings"]
    pilot = s.settings.PILOT_MODE
    comments = [
        {"path": f.path, "line": f.line, "side": "RIGHT", "body": render_comment(f, pilot)}
        for f in [f for f in findings if f.inline][: state["inline_count"]]
    ]
    fallback = render_summary(state["verdict"], findings, 0, state.get("skipped", []),
                              state.get("incomplete_reasons", []), s.llm.model, state["head_sha"],
                              s.rules_version, pilot, details_url(s, state))
    await s.github.create_review(state["repo"], state["pr_number"], state["head_sha"],
                                 state["summary"], comments, fallback)
    verdict = state["verdict"]
    await s.github.finish_status(
        state["repo"], state["head_sha"], s.settings.CHECK_NAME, state.get("check_id"),
        verdict, f"{VERDICT_TEXT[verdict]} — {len(findings)} remarque(s)", state["summary"],
        details_url(s, state),
    )
    use_checks = getattr(s.github, "use_checks", True)
    emit("published", inline=len(comments),
         github_state=CHECK_CONCLUSION[verdict] if use_checks else STATUS_STATE[verdict],
         mode="check run" if use_checks else "statut de commit")
    return {"published": True}


@node()
async def alert(state: ReviewState, config) -> dict:
    s = svc(config)
    if state["verdict"] != VERDICT_BLOCKING or state.get("superseded"):
        return {"alert_sent": False}
    reason = await blocked_reason(s)
    if reason:
        emit("publication_skipped", reason=reason, step="alerte email")
        return {"alert_sent": False}
    if not s.mailer.configured or not s.settings.alert_emails:
        log.warning("PR bloquante mais SMTP/ALERT_EMAILS non configurés : pas d'alerte")
        emit("alert_skipped", reason="SMTP non configuré")
        return {"alert_sent": False}
    msg = build_alert(s.settings.ALERT_FROM, s.settings.alert_emails, state["repo"], state["pr_number"],
                      state.get("pr_title", ""), state.get("pr_author", ""), state.get("pr_url", ""),
                      state["findings"])
    try:
        await s.mailer.send(msg)
    except Exception:  # noqa: BLE001 — la revue est publiée ; un mail raté ne doit pas la défaire
        log.exception("échec d'envoi de l'alerte email")
        emit("alert_skipped", reason="échec d'envoi SMTP")
        return {"alert_sent": False}
    emit("alert_sent", recipients=len(s.settings.alert_emails))
    return {"alert_sent": True}


def run_status(state: ReviewState) -> str:
    if state.get("error"):
        return "error"
    if state.get("stale"):
        return "stale"
    if state.get("superseded"):
        return "superseded"
    return "ok"


def _audit_record(state: ReviewState, s: Services, status: str) -> dict:
    findings = state.get("findings", [])
    return {
        "status": status,
        "run_id": state.get("run_id"),
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
        "rules_version": s.rules_version,
        "pilot_mode": s.settings.PILOT_MODE,
        "published": state.get("published", False),
        "publish_skipped": state.get("publish_skipped"),
        "alert_sent": state.get("alert_sent", False),
        "llm_model": getattr(s.llm, "model", None),
        "llm_host": getattr(s.llm, "host", None),
        "llm_served_by": sorted(getattr(s.llm, "providers_seen", None) or []) or None,
        "llm_cost_usd": round(getattr(s.llm, "cost_usd", 0.0), 6) or None,
        "dry_run": s.settings.DRY_RUN,
        "queue_s": round(state["started_at"] - state["queued_at"], 1)
        if state.get("queued_at") and state.get("started_at") else None,
        "duration_s": round(time.time() - state.get("started_at", time.time()), 1),
        "error": state.get("error"),
    }


@node(guard=False)
async def audit(state: ReviewState, config) -> dict:
    s = svc(config)
    s.audit.write(_audit_record(state, s, run_status(state)))
    return {}


@node(guard=False)
async def fail(state: ReviewState, config) -> dict:
    """Échec : check « action requise » / statut « error » (jamais vert), audit, puis DLQ côté worker."""
    s = svc(config)
    if state.get("head_sha"):
        reason = await blocked_reason(s)
        if reason:
            emit("publication_skipped", reason=reason, step="statut d'échec")
        else:
            try:
                await s.github.finish_status(
                    state["repo"], state["head_sha"], s.settings.CHECK_NAME, state.get("check_id"),
                    OUTCOME_FAILED, VERDICT_TEXT[OUTCOME_FAILED],
                    "L'analyse automatique n'a pas pu aboutir. L'incident est journalisé.",
                    details_url(s, state),
                )
            except Exception:  # noqa: BLE001
                log.exception("impossible de mettre à jour le statut après échec")
    s.audit.write(_audit_record(state, s, "error"))
    return {}
