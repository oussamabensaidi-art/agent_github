"""Worker : dépile les jobs Redis et exécute le graphe de revue.

Une analyse à la fois par worker ; scaler horizontalement avec
`docker compose up --scale worker=N`. Un job en échec part en DLQ.
File fiable : le job reste dans la liste « en cours » du worker jusqu'à la fin
de l'analyse ; si le worker meurt, un autre le reprend (voir jobqueue.py).
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
    worker_id = socket.gethostname()
    # Le battement tourne en tâche de fond : il doit continuer PENDANT une analyse
    # (sinon un autre worker croirait celui-ci mort et reprendrait son job).
    beat_task = asyncio.create_task(keep_alive(queue, store, worker_id, info, stop))
    first = True
    backoff = 1
    while not stop.is_set():
        try:
            if first:
                await queue.heartbeat(worker_id, info)
                await recover(queue, store, worker_id, include_self=True)
                first = False
            reserved = await queue.reserve(worker_id)
            backoff = 1
        except (RedisError, OSError) as e:
            # Redis indisponible un instant : on attend et on réessaie, sans tuer le worker.
            log.warning("redis indisponible (%s) ; nouvel essai dans %ss", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)
            continue
        if reserved:
            job, raw = reserved
            try:
                await handle(job, queue, store)
            finally:
                await ack_safely(queue, worker_id, raw)
    beat_task.cancel()
    await store.close()


async def ack_safely(queue: JobQueue, worker_id: str, raw: str) -> None:
    for delay in (0, 1, 3):
        try:
            await asyncio.sleep(delay)
            await queue.ack(worker_id, raw)
            return
        except (RedisError, OSError) as e:
            log.warning("acquittement impossible (%s)", e)


async def recover(queue: JobQueue, store, worker_id: str, include_self: bool = False) -> None:
    requeued, dead = await queue.recover_orphans(worker_id, include_self)
    for job in requeued:
        log.warning("job repris après arrêt d'un worker : %s#%s", job.get("repo"), job.get("pr_number"))
    for job in dead:
        log.error("job abandonné (reprises épuisées) : %s#%s", job.get("repo"), job.get("pr_number"))
        if job.get("run_id"):
            await store.emit(job["run_id"], "run_finished",
                             {"status": "error", "error": "worker interrompu pendant l'analyse (reprises épuisées)"})


async def flush_deferred(store, client_for, dry_run: bool = False) -> int:
    """Publication réactivée : clôt les checks restés « en cours » pendant la coupure."""
    if dry_run or not await store.publishing_enabled():
        return 0
    done = 0
    for item in await store.take_deferred_checks():
        github = None
        try:
            github = await client_for(item.get("installation_id"))
            await github.finish_status(item["repo"], item["sha"], item["name"], item["check_id"],
                                       item["outcome"], item["title"], item["summary"], item.get("details_url", ""))
            done += 1
            log.info("check %s clos après réactivation (%s)", item["check_id"], item["repo"])
        except Exception as e:  # noqa: BLE001
            log.warning("clôture différée du check %s impossible : %s", item.get("check_id"), e)
        finally:
            if github is not None and hasattr(github, "aclose"):
                await github.aclose()
    return done


async def keep_alive(queue: JobQueue, store, worker_id: str, info: str, stop: asyncio.Event) -> None:
    """Battement de cœur toutes les 20 s + reprise des jobs des workers morts."""
    while not stop.is_set():
        try:
            await queue.heartbeat(worker_id, info)
            await recover(queue, store, worker_id)
            await flush_deferred(store, lambda inst: github_client_for(settings, inst), settings.DRY_RUN)
        except Exception as e:  # noqa: BLE001 — ne jamais tuer la tâche de fond
            log.warning("battement de cœur impossible (%s)", e)
        await asyncio.sleep(20)


if __name__ == "__main__":
    asyncio.run(main())
