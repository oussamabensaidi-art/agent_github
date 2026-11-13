"""File d'attente Redis fiable : déduplication + mise en file + reprise + DLQ.

Fiabilité : un worker ne retire pas le job de Redis, il le DÉPLACE (BLMOVE,
atomique) dans sa liste « en cours » `prreview:processing:<worker>` et ne l'en
retire (`ack`) qu'une fois l'analyse terminée. Si le worker meurt, son battement
de cœur expire ; un autre worker remet alors ses jobs en file (`recover_orphans`).
Après JOB_MAX_RETRIES reprises, le job part en DLQ.

Un job = une analyse d'une PR à un commit donné (repo, numéro, head_sha).
Deux niveaux de déduplication :
  - X-GitHub-Delivery : GitHub peut relivrer le même webhook ;
  - repo#pr@sha       : deux événements (ex. reopened + synchronize) pour le
                        même commit ne déclenchent qu'une analyse.
"""
import json
from typing import Any, Awaitable, Callable

import redis.asyncio as redis

from config import settings


BRPOP_TIMEOUT = 5
# Doit rester > BRPOP_TIMEOUT : redis-py 8 applique un timeout socket par
# défaut qui coupait l'attente bloquante de BRPOP (TimeoutError constaté).
SOCKET_TIMEOUT = BRPOP_TIMEOUT + 10

PROCESSING_PREFIX = "prreview:processing:"
WORKER_PREFIX = "prreview:worker:"
ATTEMPTS_PREFIX = "prreview:attempts:"


class JobQueue:
    def __init__(self, client: "redis.Redis | None" = None):
        self.redis = client or redis.from_url(
            settings.REDIS_URL, decode_responses=True,
            socket_timeout=SOCKET_TIMEOUT, socket_connect_timeout=5, health_check_interval=30,
        )

    async def ping(self) -> bool:
        return bool(await self.redis.ping())

    async def enqueue(self, job: dict[str, Any],
                      before_push: Callable[[], Awaitable[None]] | None = None) -> bool:
        """Met le job en file. Renvoie False si c'est un doublon.

        `before_push` (création du run dans le journal) s'exécute après la
        déduplication et avant la mise en file : le worker ne peut pas
        dépiler un job dont le run n'existe pas encore.
        """
        ttl = settings.DEDUP_TTL_SECONDS
        if not await self.redis.set(f"prreview:delivery:{job['delivery_id']}", 1, nx=True, ex=ttl):
            return False
        sha_key = f"prreview:sha:{job['repo']}#{job['pr_number']}@{job['head_sha']}"
        if not await self.redis.set(sha_key, 1, nx=True, ex=ttl):
            return False
        if before_push is not None:
            await before_push()
        await self.redis.lpush(settings.QUEUE_KEY, json.dumps(job))
        return True

    async def reserve(self, worker_id: str, timeout: int = BRPOP_TIMEOUT) -> tuple[dict[str, Any], str] | None:
        """Prend un job : il passe de la file à la liste « en cours » du worker (atomique).

        Renvoie (job, brut) ; `brut` sert à l'acquittement."""
        raw = await self.redis.blmove(settings.QUEUE_KEY, PROCESSING_PREFIX + worker_id, timeout,
                                      src="RIGHT", dest="LEFT")
        if not raw:
            return None
        return json.loads(raw), raw

    async def ack(self, worker_id: str, raw: str) -> None:
        """Analyse terminée (réussie ou en DLQ) : le job quitte la liste « en cours »."""
        await self.redis.lrem(PROCESSING_PREFIX + worker_id, 1, raw)

    async def heartbeat(self, worker_id: str, info: str) -> None:
        await self.redis.set(WORKER_PREFIX + worker_id, info, ex=settings.WORKER_HEARTBEAT_TTL)

    async def recover_orphans(self, self_id: str, include_self: bool = False) -> tuple[list[dict], list[dict]]:
        """Remet en file les jobs « en cours » des workers morts (battement de cœur expiré).

        `include_self` : au démarrage, un worker reprend aussi sa propre liste (conteneur
        redémarré sous le même nom). Renvoie (jobs remis en file, jobs partis en DLQ)."""
        requeued: list[dict] = []
        dead: list[dict] = []
        async for key in self.redis.scan_iter(match=PROCESSING_PREFIX + "*"):
            worker_id = key[len(PROCESSING_PREFIX):]
            if worker_id == self_id:
                if not include_self:
                    continue
            elif await self.redis.exists(WORKER_PREFIX + worker_id):
                continue
            for raw in await self.redis.lrange(key, 0, -1):
                job = json.loads(raw)
                ident = job.get("run_id") or job.get("delivery_id") or raw[:64]
                attempts = await self.redis.incr(ATTEMPTS_PREFIX + ident)
                await self.redis.expire(ATTEMPTS_PREFIX + ident, settings.DEDUP_TTL_SECONDS)
                if attempts > settings.JOB_MAX_RETRIES:
                    # LREM d'abord : un seul worker gagne, pas de double mise en DLQ.
                    if await self.redis.lrem(key, 1, raw):
                        await self.dead_letter(job, "worker interrompu pendant l'analyse (reprises épuisées)")
                        dead.append(job)
                elif await self.redis.lmove(key, settings.QUEUE_KEY, src="RIGHT", dest="RIGHT") is not None:
                    requeued.append(job)   # en tête de file : repris en priorité
        return requeued, dead

    async def processing_size(self) -> int:
        total = 0
        async for key in self.redis.scan_iter(match=PROCESSING_PREFIX + "*"):
            total += int(await self.redis.llen(key))
        return total

    async def dead_letter(self, job: dict[str, Any], error: str) -> None:
        await self.redis.lpush(settings.DLQ_KEY, json.dumps({**job, "error": error}))

    async def dlq_size(self) -> int:
        return int(await self.redis.llen(settings.DLQ_KEY))

    async def forget_commits(self, repo: str) -> int:
        """Efface les clés de déduplication par commit d'un dépôt (mode démo uniquement)."""
        keys = [k async for k in self.redis.scan_iter(match=f"prreview:sha:{repo}#*")]
        return await self.redis.delete(*keys) if keys else 0
