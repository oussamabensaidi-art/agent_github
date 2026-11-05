"""File d'attente Redis : déduplication + mise en file + DLQ.

Un job = une analyse d'une PR à un commit donné (repo, numéro, head_sha).
Deux niveaux de déduplication :
  - X-GitHub-Delivery : GitHub peut relivrer le même webhook ;
  - repo#pr@sha       : deux événements (ex. reopened + synchronize) pour le
                        même commit ne déclenchent qu'une analyse.
"""
import json
from typing import Any

import redis.asyncio as redis

from config import settings


BRPOP_TIMEOUT = 5
# Doit rester > BRPOP_TIMEOUT : redis-py 8 applique un timeout socket par
# défaut qui coupait l'attente bloquante de BRPOP (TimeoutError constaté).
SOCKET_TIMEOUT = BRPOP_TIMEOUT + 10


class JobQueue:
    def __init__(self, client: "redis.Redis | None" = None):
        self.redis = client or redis.from_url(
            settings.REDIS_URL, decode_responses=True,
            socket_timeout=SOCKET_TIMEOUT, socket_connect_timeout=5, health_check_interval=30,
        )

    async def ping(self) -> bool:
        return bool(await self.redis.ping())

    async def enqueue(self, job: dict[str, Any]) -> bool:
        """Met le job en file. Renvoie False si c'est un doublon."""
        ttl = settings.DEDUP_TTL_SECONDS
        if not await self.redis.set(f"prreview:delivery:{job['delivery_id']}", 1, nx=True, ex=ttl):
            return False
        sha_key = f"prreview:sha:{job['repo']}#{job['pr_number']}@{job['head_sha']}"
        if not await self.redis.set(sha_key, 1, nx=True, ex=ttl):
            return False
        await self.redis.lpush(settings.QUEUE_KEY, json.dumps(job))
        return True

    async def dequeue(self, timeout: int = BRPOP_TIMEOUT) -> dict[str, Any] | None:
        item = await self.redis.brpop([settings.QUEUE_KEY], timeout=timeout)
        if not item:
            return None
        return json.loads(item[1])

    async def dead_letter(self, job: dict[str, Any], error: str) -> None:
        await self.redis.lpush(settings.DLQ_KEY, json.dumps({**job, "error": error}))
