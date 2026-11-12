"""API webhook : reçoit les événements GitHub et les met en file.

Le traitement (long) est fait par le worker ; l'API répond en < 1 s pour
rester sous le délai de 10 s de GitHub.
"""
import hashlib
import hmac
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request

from config import settings
from jobqueue import JobQueue
from store import NullStore, build_store
from ui.auth import Sessions
from ui.live import LiveHub
from ui.routes import mount_ui

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("pr-review.api")

queue = JobQueue()
# Remplacé au démarrage par le journal Postgres si DATABASE_URL est défini.
store = NullStore(settings.PUBLISH_ENABLED)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global store
    store = build_store(settings, queue.redis)
    await store.open()
    hub = LiveHub(queue.redis, settings.EVENTS_STREAM_KEY)
    if store.available:
        hub.start()
    app.state.store, app.state.queue, app.state.hub = store, queue, hub
    app.state.sessions = Sessions(queue.redis, settings.UI_SESSION_TTL_SECONDS)
    yield
    await hub.stop()
    await store.close()


app = FastAPI(title="Calipso PR Review Agent", lifespan=lifespan)
mount_ui(app)


def verify_signature(secret: str, body: bytes, signature_header: str | None) -> bool:
    """Vérifie X-Hub-Signature-256 (HMAC-SHA256 du corps brut)."""
    if not secret or not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.removeprefix("sha256="))


def job_from_event(event: str, delivery_id: str, payload: dict) -> dict | None:
    """Transforme un webhook pull_request en job, ou None s'il est ignoré."""
    if event != "pull_request":
        return None
    if payload.get("action") not in settings.trigger_actions:
        return None
    pr = payload["pull_request"]
    if pr.get("state") != "open":
        return None
    if settings.SKIP_DRAFTS and pr.get("draft"):
        return None
    return {
        "delivery_id": delivery_id,
        "repo": payload["repository"]["full_name"],
        "pr_number": pr["number"],
        "head_sha": pr["head"]["sha"],
        "installation_id": (payload.get("installation") or {}).get("id"),
        "action": payload["action"],
    }


@app.get("/health")
async def health():
    try:
        redis_ok = await queue.ping()
    except Exception:
        redis_ok = False
    if not redis_ok:
        raise HTTPException(status_code=503, detail="redis unavailable")
    return {"status": "ok"}


@app.post("/webhook/github", status_code=202)
async def github_webhook(
    request: Request,
    x_github_event: str = Header(default=""),
    x_github_delivery: str = Header(default=""),
    x_hub_signature_256: str | None = Header(default=None),
):
    body = await request.body()
    if not verify_signature(settings.GITHUB_WEBHOOK_SECRET, body, x_hub_signature_256):
        log.warning("signature invalide delivery=%s", x_github_delivery)
        raise HTTPException(status_code=401, detail="invalid signature")

    if x_github_event == "ping":
        return {"status": "pong"}

    try:
        payload = json.loads(body)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid json")

    job = job_from_event(x_github_event, x_github_delivery, payload)
    if job is None:
        return {"status": "ignored"}

    job["run_id"] = uuid.uuid4().hex
    job["queued_at"] = time.time()
    demo = x_github_delivery.startswith("demo-")

    async def register() -> None:
        await store.create_run(job, demo=demo)

    queued = await queue.enqueue(job, before_push=register)
    log.info("job %s %s#%s@%s", "queued" if queued else "duplicate",
             job["repo"], job["pr_number"], job["head_sha"][:7])
    return {"status": "queued", "run_id": job["run_id"]} if queued else {"status": "duplicate"}
