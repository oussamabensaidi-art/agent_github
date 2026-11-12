"""API de l'interface de suivi (/ui/api) et service des fichiers de l'interface (/ui).

Tout est derrière une session (ui.auth). Lecture : tout compte connecté.
Écriture : avis sur les remarques (tout compte), interrupteur et démo (admin).
"""
import asyncio
import hashlib
import hmac
import json
import logging
import time
from pathlib import Path
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent.prompts import load_rules
from agent.review import VERDICTS, rules_version
from config import settings
from ui.auth import COOKIE, admin_user, current_user, dummy_verify, parse_users, verify_password

log = logging.getLogger("pr-review.ui")

api = APIRouter(prefix="/ui/api")
DIST = Path(__file__).resolve().parent / "dist"

# Types relayés sur le flux global (liste des runs en direct) : pas le détail.
GLOBAL_TYPES = {"run_queued", "run_started", "pr_info", "node_started", "verdict", "run_finished"}


def store_of(request: Request):
    store = request.app.state.store
    if not store.available:
        raise HTTPException(503, "journal d'événements non configuré (DATABASE_URL)")
    return store


def _sse(ev: dict, event_id) -> str:
    return f"id: {event_id}\ndata: {json.dumps(ev, ensure_ascii=False, default=str)}\n\n"


# --------------------------------------------------------------------- session

class Login(BaseModel):
    login: str
    password: str


@api.post("/login")
async def login(body: Login, request: Request, response: Response):
    sessions = request.app.state.sessions
    if await sessions.too_many_failures(body.login):
        raise HTTPException(429, "trop de tentatives, réessayez dans quelques minutes")
    user = parse_users(settings.UI_USERS).get(body.login)
    if user is None:
        dummy_verify(body.password)
    if user is None or not verify_password(body.password, user[1]):
        await sessions.record_failure(body.login)
        raise HTTPException(401, "identifiant ou mot de passe incorrect")
    token = await sessions.create(body.login, user[0])
    response.set_cookie(COOKIE, token, httponly=True, samesite="strict", secure=settings.UI_COOKIE_SECURE,
                        max_age=settings.UI_SESSION_TTL_SECONDS, path="/ui")
    return {"login": body.login, "role": user[0]}


@api.post("/logout")
async def logout(request: Request, response: Response, user=Depends(current_user)):
    await request.app.state.sessions.delete(request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/ui")
    return {"ok": True}


@api.get("/me")
async def me(user=Depends(current_user)):
    return user


# --------------------------------------------------------------- configuration

@api.get("/config")
async def config(request: Request, user=Depends(current_user)):
    store = request.app.state.store
    rules = load_rules(settings.RULES_PATH)
    try:
        from agent.runner import build_llm
        model = build_llm(settings).model
    except Exception as e:  # noqa: BLE001
        model = f"(configuration invalide : {type(e).__name__})"
    # Configuration réelle : celle des workers actifs (battement de cœur Redis), pas celle de l'api.
    workers = []
    try:
        redis = request.app.state.queue.redis
        async for key in redis.scan_iter(match="prreview:worker:*"):
            raw = await redis.get(key)
            if raw:
                workers.append(json.loads(raw))
    except Exception:  # noqa: BLE001
        pass
    w = workers[0] if workers else {}
    return {
        "workers": workers,
        "publishing": await store.publishing_state() if store.available else
        {"enabled": settings.PUBLISH_ENABLED, "updated_by": None, "updated_at": None},
        "store": store.available,
        "pilot_mode": w.get("pilot_mode", settings.PILOT_MODE),
        "dry_run": w.get("dry_run", settings.DRY_RUN),
        "demo_mode": settings.DEMO_MODE,
        "rules_version": rules_version(rules),
        "provider": w.get("provider", settings.LLM_PROVIDER),
        "model": w.get("model", model),
        "concurrency": w.get("concurrency", settings.LLM_CONCURRENCY),
        "check_name": settings.CHECK_NAME,
        "auth_mode": w.get("auth_mode", settings.GITHUB_AUTH_MODE),
        "verdicts": VERDICTS,
    }


class Publishing(BaseModel):
    enabled: bool


@api.put("/publishing")
async def set_publishing(body: Publishing, request: Request, user=Depends(admin_user)):
    store = store_of(request)
    await store.set_publishing(body.enabled, user["login"])
    log.warning("interrupteur de publication : %s par %s", "ACTIVÉ" if body.enabled else "COUPÉ", user["login"])
    return await store.publishing_state()


@api.get("/publishing/history")
async def publishing_history(request: Request, user=Depends(current_user)):
    return await store_of(request).publishing_history()


# ------------------------------------------------------------------------ runs

@api.get("/runs")
async def runs(request: Request, repo: str | None = None, verdict: str | None = None, status: str | None = None,
               date_from: str | None = None, date_to: str | None = None, demo: bool | None = None,
               limit: int = 50, offset: int = 0, user=Depends(current_user)):
    return await store_of(request).list_runs(repo, verdict, status, date_from, date_to, demo,
                                             min(max(limit, 1), 200), max(offset, 0))


@api.get("/repos")
async def repos(request: Request, user=Depends(current_user)):
    return await store_of(request).repos()


@api.get("/runs/{run_id}")
async def run_detail(run_id: str, request: Request, user=Depends(current_user)):
    run = await store_of(request).get_run(run_id)
    if not run:
        raise HTTPException(404, "analyse inconnue")
    return run


@api.get("/runs/{run_id}/events")
async def run_events(run_id: str, request: Request, user=Depends(current_user)):
    return await store_of(request).events(run_id)


@api.get("/runs/{run_id}/stream")
async def run_stream(run_id: str, request: Request, last_event_id: str | None = Header(default=None),
                     user=Depends(current_user)):
    store, hub = store_of(request), request.app.state.hub
    queue = hub.subscribe(run_id)  # abonnement AVANT la lecture en base : aucun événement perdu

    async def gen():
        sent = int(last_event_id) if last_event_id and last_event_id.isdigit() else -1
        try:
            for ev in await store.events(run_id, after=sent):
                yield _sse(ev, ev["seq"])
                sent = ev["seq"]
            while not await request.is_disconnected():
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                if ev["seq"] <= sent:
                    continue
                if ev["seq"] > sent + 1:  # trou (file pleine, reconnexion) : rattrapage depuis la base
                    for e in await store.events(run_id, after=sent):
                        yield _sse(e, e["seq"])
                        sent = e["seq"]
                    continue
                yield _sse(ev, ev["seq"])
                sent = ev["seq"]
        finally:
            hub.unsubscribe(queue)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@api.get("/stream")
async def global_stream(request: Request, user=Depends(current_user)):
    hub = request.app.state.hub
    queue = hub.subscribe(None)

    async def gen():
        try:
            yield ": connecté\n\n"
            while not await request.is_disconnected():
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                if ev["type"] in GLOBAL_TYPES:
                    yield _sse(ev, f"{ev['run_id']}:{ev['seq']}")
        finally:
            hub.unsubscribe(queue)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class Feedback(BaseModel):
    rating: Literal["pertinente", "fausse_alerte"]


@api.put("/runs/{run_id}/findings/{finding_id}/feedback")
async def set_feedback(run_id: str, finding_id: str, body: Feedback, request: Request,
                       user=Depends(current_user)):
    if not await store_of(request).set_feedback(run_id, finding_id, body.rating, user["login"]):
        raise HTTPException(404, "remarque inconnue ou écartée")
    return {"rating": body.rating, "rated_by": user["login"]}


@api.delete("/runs/{run_id}/findings/{finding_id}/feedback")
async def clear_feedback(run_id: str, finding_id: str, request: Request, user=Depends(current_user)):
    await store_of(request).clear_feedback(run_id, finding_id)
    return {"rating": None}


@api.get("/stats")
async def stats(request: Request, repo: str | None = None, date_from: str | None = None,
                date_to: str | None = None, demo: bool | None = None, user=Depends(current_user)):
    out = await store_of(request).stats(repo, date_from, date_to, demo)
    try:
        out["dlq_size"] = await request.app.state.queue.dlq_size()
    except Exception:  # noqa: BLE001
        out["dlq_size"] = None
    out["relevance_target"] = 0.70
    return out


# ------------------------------------------------------------------------ démo

def demo_guard() -> None:
    if not settings.DEMO_MODE:
        raise HTTPException(404, "mode démo désactivé")
    if "api.github.com" in settings.GITHUB_API_URL:
        raise HTTPException(409, "mode démo refusé : l'agent pointe vers le vrai GitHub")


@api.get("/demo")
async def demo_catalog(user=Depends(current_user)):
    demo_guard()
    from e2e.fixtures import PRS, REPO, WEBHOOK_SHA
    return {"repo": REPO, "prs": [{
        "number": n, "title": pr["title"], "files": [f["filename"] for f in pr["files"]],
        "stale": n in WEBHOOK_SHA} for n, pr in sorted(PRS.items())]}


class DemoLaunch(BaseModel):
    prs: list[int]


@api.post("/demo/launch")
async def demo_launch(body: DemoLaunch, request: Request, user=Depends(admin_user)):
    """Envoie de vrais webhooks signés à l'API : tout le pipeline est exercé, contre le faux GitHub."""
    demo_guard()
    from e2e.fixtures import PRS, REPO, WEBHOOK_SHA
    numbers = [n for n in body.prs if n in PRS] or sorted(PRS)
    # Les PR fictives ont des commits fixes : sans cela, la déduplication (24 h) bloquerait une 2e démo.
    await request.app.state.queue.forget_commits(REPO)
    stamp = str(int(time.time() * 1000))
    launched = []
    async with httpx.AsyncClient(base_url=settings.DEMO_SELF_URL, timeout=10) as client:
        for n in numbers:
            raw = json.dumps({
                "action": "opened", "repository": {"full_name": REPO}, "installation": {"id": 42},
                "pull_request": {"number": n, "draft": False, "state": "open",
                                 "head": {"sha": WEBHOOK_SHA.get(n, PRS[n]["sha"])}},
            }).encode()
            sig = "sha256=" + hmac.new(settings.GITHUB_WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
            r = await client.post("/webhook/github", content=raw, headers={
                "X-GitHub-Event": "pull_request", "X-GitHub-Delivery": f"demo-{stamp}-{n}",
                "X-Hub-Signature-256": sig, "Content-Type": "application/json"})
            launched.append({"number": n, "http": r.status_code, **(r.json() if r.status_code < 500 else {})})
    log.info("démo lancée par %s : %s", user["login"], numbers)
    return {"launched": launched}


# --------------------------------------------------------------------- statique

def mount_ui(app: FastAPI) -> None:
    app.include_router(api)
    if (DIST / "assets").is_dir():
        app.mount("/ui/assets", StaticFiles(directory=DIST / "assets"), name="ui-assets")

    @app.get("/ui", include_in_schema=False)
    @app.get("/ui/{path:path}", include_in_schema=False)
    async def ui_index(path: str = ""):
        if path.startswith("api/"):
            raise HTTPException(404)
        target = (DIST / path).resolve()
        if path and target.is_file() and DIST.resolve() in target.parents:
            return FileResponse(target)
        index = DIST / "index.html"
        if not index.exists():
            return HTMLResponse("<p>Interface non construite (ui/frontend → npm run build).</p>", status_code=503)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
