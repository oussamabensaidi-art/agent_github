"""Worker : dépile les jobs Redis et exécute le graphe de revue.

Une analyse à la fois par worker ; scaler horizontalement avec
`docker compose up --scale worker=N`. Un job en échec part en DLQ.

Fiabilité (jobqueue) : le job reste dans la liste « en cours » du worker
jusqu'à la fin de l'analyse. Le battement de cœur est entretenu en tâche de
fond, y compris pendant une longue analyse (attente de la CI) ; un worker
sans battement de cœur est considéré comme mort et ses jobs sont repris.
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

RECOVER_EVERY = 60  # secondes entre deux recherches de jobs orphelins (workers morts)


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
    worker_id = socket.gethostname()
    info = json.dumps({"host": worker_id, "provider": settings.LLM_PROVIDER, "model": llm.model,
                       "dry_run": settings.DRY_RUN, "pilot_mode": settings.PILOT_MODE,
                       "concurrency": settings.LLM_CONCURRENCY, "auth_mode": settings.GITHUB_AUTH_MODE})
    beating = asyncio.create_task(heartbeat_loop(queue, worker_id, info, stop))
    recovered = 0.0
    first = True
    backoff = 1
    while not stop.is_set():
        try:
            if first or time.monotonic() - recovered > RECOVER_EVERY:
                # Au démarrage : aussi notre propre liste (redémarrage après plantage).
                out = await queue.recover_orphans(worker_id, include_self=first)
                if out["requeued"] or out["dead_lettered"]:
                    log.warning("jobs interrompus repris : %s remis en file, %s en DLQ",
                                out["requeued"], out["dead_lettered"])
                recovered, first = time.monotonic(), False
            leased = await queue.dequeue(worker_id)
            backoff = 1
        except (RedisError, OSError) as e:
            # Redis indisponible un instant : on attend et on réessaie, sans tuer le worker.
            log.warning("redis indisponible (%s) ; nouvel essai dans %ss", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)
            continue
        if leased:
            job, raw = leased
            await handle(job, queue, store)
            await ack_with_retry(queue, worker_id, raw)
    beating.cancel()
    await store.close()


async def heartbeat_loop(queue: JobQueue, worker_id: str, info: str, stop: asyncio.Event) -> None:
    """Battement de cœur toutes les 20 s, indépendant de l'analyse en cours.

    L'interface y lit la configuration RÉELLE des workers (modèle, lecture seule,
    mode pilote) ; jobqueue s'en sert pour savoir si un worker est vivant.
    """
    while not stop.is_set():
        try:
            await queue.heartbeat(worker_id, info)
        except (RedisError, OSError) as e:
            log.warning("battement de cœur impossible (%s)", e)
        try:
            await asyncio.wait_for(stop.wait(), timeout=20)
        except asyncio.TimeoutError:
            pass


async def ack_with_retry(queue: JobQueue, worker_id: str, raw: str) -> None:
    """Retire le job de la liste « en cours ». Redis indisponible : on réessaie (sinon il serait rejoué)."""
    for delay in (1, 2, 5, 10, 30):
        try:
            await queue.ack(worker_id, raw)
            return
        except (RedisError, OSError) as e:
            log.warning("ack impossible (%s) ; nouvel essai dans %ss", e, delay)
            await asyncio.sleep(delay)
    log.error("ack abandonné : ce job sera rejoué au prochain démarrage du worker")


if __name__ == "__main__":
    asyncio.run(main())
