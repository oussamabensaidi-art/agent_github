"""Worker : dépile les jobs Redis et exécute le graphe de revue.

Une analyse à la fois par worker ; scaler horizontalement avec
`docker compose up --scale worker=N`. Un job en échec part en DLQ.
"""
import asyncio
import json
import logging
import signal
import socket
import time

from redis.exceptions import RedisError

from agent.runner import build_llm, build_services, github_client_for, run_review
from agent.secrets_scan import redact_text
from config import settings
from jobqueue import JobQueue
from store import build_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("pr-review.worker")


async def handle(job: dict, queue: JobQueue, store) -> None:
    label = f"{job['repo']}#{job['pr_number']}@{job['head_sha'][:7]}"
    log.info("analyse %s", label)
    github = None
    try:
        github = await github_client_for(settings, job.get("installation_id"))
        result = await run_review(job, build_services(settings, github, store))
        if result.get("error"):
            await queue.dead_letter(job, result["error"])
            log.error("analyse %s en échec : %s", label, result["error"])
        else:
            log.info("analyse %s terminée : %s", label, result.get("verdict") or "obsolète")
    except Exception as e:  # noqa: BLE001
        log.exception("analyse %s : erreur hors graphe", label)
        error = redact_text(f"{type(e).__name__}: {e}")[0]
        await queue.dead_letter(job, error)
        if job.get("run_id"):
            # Sans cela, le run resterait « en file » dans l'interface.
            await store.emit(job["run_id"], "run_finished", {"status": "error", "error": error})
    finally:
        if github is not None:
            await github.aclose()


async def main() -> None:
    queue = JobQueue()
    store = build_store(settings, queue.redis)
    await store.open()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows
            pass
    llm = build_llm(settings)
    log.info("worker prêt (fournisseur %s, modèle %s @ %s, %s lot(s) en parallèle, journal %s)",
             settings.LLM_PROVIDER, llm.model, llm.host, settings.LLM_CONCURRENCY,
             "postgres" if store.available else "désactivé")
    # Battement de cœur : l'interface affiche la configuration RÉELLE des workers
    # (modèle, lecture seule, mode pilote), pas celle de l'api.
    info = json.dumps({"host": socket.gethostname(), "provider": settings.LLM_PROVIDER, "model": llm.model,
                       "dry_run": settings.DRY_RUN, "pilot_mode": settings.PILOT_MODE,
                       "concurrency": settings.LLM_CONCURRENCY, "auth_mode": settings.GITHUB_AUTH_MODE})
    beat = 0.0
    backoff = 1
    while not stop.is_set():
        try:
            if time.monotonic() - beat > 20:
                await queue.redis.set(f"prreview:worker:{socket.gethostname()}", info, ex=60)
                beat = time.monotonic()
            job = await queue.dequeue()
            backoff = 1
        except (RedisError, OSError) as e:
            # Redis indisponible un instant : on attend et on réessaie, sans tuer le worker.
            log.warning("redis indisponible (%s) ; nouvel essai dans %ss", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)
            continue
        if job:
            await handle(job, queue, store)
    await store.close()


if __name__ == "__main__":
    asyncio.run(main())
