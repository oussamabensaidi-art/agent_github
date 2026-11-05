"""Worker : dépile les jobs Redis et exécute le graphe de revue.

Une analyse à la fois par worker ; scaler horizontalement avec
`docker compose up --scale worker=N`. Un job en échec part en DLQ.
"""
import asyncio
import logging
import signal

from redis.exceptions import RedisError

from agent.runner import build_services, github_client_for, run_review
from config import settings
from jobqueue import JobQueue

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("pr-review.worker")


async def handle(job: dict, queue: JobQueue) -> None:
    label = f"{job['repo']}#{job['pr_number']}@{job['head_sha'][:7]}"
    log.info("analyse %s", label)
    github = None
    try:
        github = await github_client_for(settings, job.get("installation_id"))
        result = await run_review(job, build_services(settings, github))
        if result.get("error"):
            await queue.dead_letter(job, result["error"])
            log.error("analyse %s en échec : %s", label, result["error"])
        else:
            log.info("analyse %s terminée : %s", label, result.get("verdict") or "obsolète")
    except Exception as e:  # noqa: BLE001
        log.exception("analyse %s : erreur hors graphe", label)
        await queue.dead_letter(job, f"{type(e).__name__}: {e}")
    finally:
        if github is not None:
            await github.aclose()


async def main() -> None:
    queue = JobQueue()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows
            pass
    log.info("worker prêt (modèle %s @ %s)", settings.LLM_MODEL, settings.LLM_BASE_URL)
    backoff = 1
    while not stop.is_set():
        try:
            job = await queue.dequeue()
            backoff = 1
        except (RedisError, OSError) as e:
            # Redis indisponible un instant : on attend et on réessaie, sans tuer le worker.
            log.warning("redis indisponible (%s) ; nouvel essai dans %ss", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)
            continue
        if job:
            await handle(job, queue)


if __name__ == "__main__":
    asyncio.run(main())
