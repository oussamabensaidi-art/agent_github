"""File fiable : un job n'est jamais perdu quand un worker meurt pendant l'analyse."""
import json

import fakeredis
import pytest

from config import settings
from jobqueue import HEARTBEAT_PREFIX, JobQueue, processing_key


def job(n: int, sha: str = "abc1234") -> dict:
    return {"delivery_id": f"d{n}", "repo": "o/r", "pr_number": n, "head_sha": sha, "run_id": f"run{n}"}


@pytest.fixture
def queue() -> JobQueue:
    return JobQueue(fakeredis.FakeAsyncRedis(decode_responses=True))


async def test_dequeue_moves_job_to_worker_list_until_ack(queue):
    await queue.enqueue(job(1))

    leased = await queue.dequeue("w1", timeout=1)
    assert leased is not None
    j, raw = leased
    assert j["pr_number"] == 1
    # Pris, mais pas perdu : le job est dans la liste « en cours » du worker.
    assert await queue.redis.llen(settings.QUEUE_KEY) == 0
    assert await queue.in_progress() == {"w1": 1}

    await queue.ack("w1", raw)
    assert await queue.in_progress() == {}   # liste vide : Redis la supprime


async def test_jobs_are_taken_in_arrival_order(queue):
    for n in (1, 2, 3):
        await queue.enqueue(job(n))
    order = [(await queue.dequeue("w1", timeout=1))[0]["pr_number"] for _ in range(3)]
    assert order == [1, 2, 3]


async def test_dead_worker_job_is_requeued_first(queue):
    await queue.enqueue(job(1))
    await queue.enqueue(job(2))
    await queue.dequeue("mort", timeout=1)          # le worker « mort » prend #1 puis disparaît (pas de battement)

    out = await queue.recover_orphans("w2")
    assert out == {"requeued": 1, "dead_lettered": 0}
    assert await queue.in_progress() == {}
    j, _ = await queue.dequeue("w2", timeout=1)
    assert j["pr_number"] == 1 and j["attempts"] == 1   # repris en priorité, tentative comptée


async def test_live_worker_job_is_not_stolen(queue):
    await queue.enqueue(job(1))
    await queue.heartbeat("vivant")
    await queue.dequeue("vivant", timeout=1)

    assert await queue.recover_orphans("w2") == {"requeued": 0, "dead_lettered": 0}
    assert await queue.in_progress() == {"vivant": 1}


async def test_own_list_is_recovered_only_at_startup(queue):
    await queue.enqueue(job(1))
    await queue.dequeue("w1", timeout=1)
    await queue.heartbeat("w1")

    # Pendant le fonctionnement : jamais sa propre analyse en cours.
    assert (await queue.recover_orphans("w1"))["requeued"] == 0
    # Au démarrage (le worker redémarre après un plantage) : on la reprend.
    assert (await queue.recover_orphans("w1", include_self=True))["requeued"] == 1


async def test_job_goes_to_dlq_after_max_interruptions(queue):
    await queue.enqueue(job(1))
    for attempt in range(1, settings.QUEUE_MAX_ATTEMPTS + 1):
        await queue.dequeue(f"mort{attempt}", timeout=1)
        out = await queue.recover_orphans("w")
    assert out == {"requeued": 0, "dead_lettered": 1}
    assert await queue.redis.llen(settings.QUEUE_KEY) == 0
    [dead] = await queue.dead_letters()
    assert dead["pr_number"] == 1 and "interrompue" in dead["error"]


async def test_two_workers_recovering_together_requeue_once(queue):
    await queue.enqueue(job(1))
    await queue.dequeue("mort", timeout=1)
    # Un autre worker est déjà en train de reprendre cette liste.
    await queue.redis.set("prreview:recover-lock:mort", "w2", ex=30)

    assert (await queue.recover_orphans("w3"))["requeued"] == 0
    await queue.redis.delete("prreview:recover-lock:mort")
    assert (await queue.recover_orphans("w3"))["requeued"] == 1
    assert await queue.redis.llen(settings.QUEUE_KEY) == 1


async def test_replay_dead_letters_clears_error_and_attempts(queue):
    await queue.dead_letter({**job(1), "attempts": 2}, "403 Forbidden")
    await queue.dead_letter(job(2), "422")

    assert await queue.replay_dead_letters(limit=1) == 1
    j, _ = await queue.dequeue("w", timeout=1)
    assert j["pr_number"] == 1 and "error" not in j and "attempts" not in j and "failed_at" not in j
    assert await queue.dlq_size() == 1
    assert await queue.purge_dead_letters() == 1 and await queue.dlq_size() == 0


async def test_duplicate_delivery_and_same_commit_are_ignored(queue):
    assert await queue.enqueue(job(1)) is True
    assert await queue.enqueue(job(1)) is False                         # même livraison
    assert await queue.enqueue({**job(1), "delivery_id": "autre"}) is False   # même commit
    assert await queue.redis.llen(settings.QUEUE_KEY) == 1


async def test_heartbeat_expires(queue):
    await queue.heartbeat("w1", json.dumps({"host": "w1"}))
    ttl = await queue.redis.ttl(f"{HEARTBEAT_PREFIX}w1")
    assert 0 < ttl <= 60
    assert processing_key("w1").endswith(":processing:w1")
