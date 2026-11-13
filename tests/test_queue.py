"""File fiable : réservation, acquittement, reprise des jobs d'un worker mort, DLQ."""
import json

from config import settings
from jobqueue import PROCESSING_PREFIX, WORKER_PREFIX, JobQueue


class FakeRedis:
    """Sous-ensemble en mémoire des commandes Redis utilisées par JobQueue."""

    def __init__(self):
        self.kv: dict[str, str] = {}
        self.lists: dict[str, list[str]] = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.kv:
            return None
        self.kv[key] = str(value)
        return True

    async def exists(self, key):
        return int(key in self.kv)

    async def incr(self, key):
        self.kv[key] = str(int(self.kv.get(key, 0)) + 1)
        return int(self.kv[key])

    async def expire(self, key, ttl):
        return True

    async def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)

    async def llen(self, key):
        return len(self.lists.get(key, []))

    async def lrange(self, key, start, stop):
        return list(self.lists.get(key, []))

    async def lrem(self, key, count, value):
        items = self.lists.get(key, [])
        if value in items:
            items.remove(value)
            return 1
        return 0

    def _move(self, src, dst, src_side, dst_side):
        items = self.lists.get(src, [])
        if not items:
            return None
        value = items.pop() if src_side == "RIGHT" else items.pop(0)
        target = self.lists.setdefault(dst, [])
        target.append(value) if dst_side == "RIGHT" else target.insert(0, value)
        return value

    async def lmove(self, first, second, src="LEFT", dest="RIGHT"):
        return self._move(first, second, src, dest)

    async def scan_iter(self, match):
        prefix = match.rstrip("*")
        for key in [k for k, v in self.lists.items() if k.startswith(prefix) and v]:
            yield key


class Redis(FakeRedis):
    async def blmove(self, first, second, timeout, src="LEFT", dest="RIGHT"):
        return self._move(first, second, src, dest)


def job(n: int) -> dict:
    return {"delivery_id": f"d{n}", "repo": "calipso/app", "pr_number": n, "head_sha": f"{n:040d}", "run_id": f"run{n}"}


async def test_job_stays_in_processing_until_acked():
    q = JobQueue(Redis())
    assert await q.enqueue(job(1)) and await q.enqueue(job(2))
    reserved, raw = await q.reserve("w1")
    assert reserved["pr_number"] == 1                      # premier arrivé, premier servi
    assert await q.processing_size() == 1 and await q.redis.llen(settings.QUEUE_KEY) == 1
    await q.ack("w1", raw)
    assert await q.processing_size() == 0
    assert await q.reserve("w1") and await q.reserve("w1") is None


async def test_duplicate_delivery_or_commit_is_not_queued_twice():
    q = JobQueue(Redis())
    assert await q.enqueue(job(1))
    assert not await q.enqueue(job(1))
    assert not await q.enqueue({**job(1), "delivery_id": "autre"})


async def test_dead_worker_job_is_requeued_first_then_dead_lettered():
    q = JobQueue(Redis())
    await q.enqueue(job(1))
    await q.enqueue(job(2))
    await q.reserve("mort")                                 # le worker « mort » prend le job 1 puis disparaît
    await q.heartbeat("vivant", "{}")

    requeued, dead = await q.recover_orphans("vivant")
    assert [j["pr_number"] for j in requeued] == [1] and dead == []
    nxt, raw = await q.reserve("vivant")
    assert nxt["pr_number"] == 1                            # repris avant le job 2

    # Le second worker meurt lui aussi sur ce job : reprises épuisées → DLQ.
    del q.redis.kv[WORKER_PREFIX + "vivant"]
    await q.heartbeat("troisieme", "{}")
    requeued, dead = await q.recover_orphans("troisieme")
    assert requeued == [] and [j["pr_number"] for j in dead] == [1]
    assert await q.dlq_size() == 1 and await q.processing_size() == 0
    assert "reprises épuisées" in json.loads(q.redis.lists[settings.DLQ_KEY][0])["error"]
    assert (await q.reserve("troisieme"))[0]["pr_number"] == 2


async def test_live_worker_jobs_are_left_alone_and_restart_recovers_own_list():
    q = JobQueue(Redis())
    await q.enqueue(job(1))
    await q.reserve("w1")
    await q.heartbeat("w1", "{}")
    await q.heartbeat("w2", "{}")
    assert await q.recover_orphans("w2") == ([], [])        # w1 est vivant : on ne touche pas à son job
    assert await q.recover_orphans("w1") == ([], [])        # ni au sien en cours de route
    requeued, _ = await q.recover_orphans("w1", include_self=True)   # redémarrage sous le même nom
    assert len(requeued) == 1 and not q.redis.lists[PROCESSING_PREFIX + "w1"]
