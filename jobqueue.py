"""File d'attente Redis fiable : déduplication, mise en file, liste « en cours », reprise, DLQ.

Un job = une analyse d'une PR à un commit donné (repo, numéro, head_sha).

Déduplication à l'entrée, sur deux niveaux :
  - X-GitHub-Delivery : GitHub peut relivrer le même webhook ;
  - repo#pr@sha       : deux événements (ex. reopened + synchronize) pour le
                        même commit ne déclenchent qu'une analyse.

Fiabilité (un worker qui meurt ne perd plus son job) :
  - le worker prend un job avec BLMOVE : le job passe ATOMIQUEMENT de la file
    à la liste « en cours » de ce worker (prreview:queue:processing:<worker>) ;
  - il n'en sort qu'à la fin de l'analyse (`ack`), succès ou échec ;
  - chaque worker entretient un battement de cœur (prreview:worker:<worker>,
    expire en 60 s). Les jobs « en cours » d'un worker sans battement de cœur
    sont remis en tête de file (`recover_orphans`), avec un compteur de
    tentatives ; au-delà de QUEUE_MAX_ATTEMPTS interruptions, le job part en DLQ ;
  - au démarrage, un worker reprend aussi sa propre liste (redémarrage après plantage).

Rejouer la DLQ (après correction de la cause) :
    python -m jobqueue dlq             # liste
    python -m jobqueue replay [N]      # remet en file les N plus anciens (tous par défaut)
    python -m jobqueue purge           # vide la DLQ
"""
import argparse
import asyncio
import json
import time
from typing import Any, Awaitable, Callable

import redis.asyncio as redis

from config import settings


BRPOP_TIMEOUT = 5
# Doit rester > BRPOP_TIMEOUT : redis-py 8 applique un timeout socket par
# défaut qui coupait l'attente bloquante (TimeoutError constaté).
SOCKET_TIMEOUT = BRPOP_TIMEOUT + 10

HEARTBEAT_PREFIX = "prreview:worker:"
HEARTBEAT_TTL = 60


def processing_key(worker_id: str) -> str:
    return f"{settings.QUEUE_KEY}:processing:{worker_id}"


class JobQueue:
    def __init__(self, client: "redis.Redis | None" = None):
        self.redis = client or redis.from_url(
            settings.REDIS_URL, decode_responses=True,
            socket_timeout=SOCKET_TIMEOUT, socket_connect_timeout=5, health_check_interval=30,
        )

    async def ping(self) -> bool:
        return bool(await self.redis.ping())

    # --- Entrée ----------------------------------------------------------------

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

    # --- Worker ----------------------------------------------------------------

    async def heartbeat(self, worker_id: str, info: str = "{}") -> None:
        """Signale que le worker est vivant (à appeler toutes les ~20 s, y compris pendant une analyse)."""
        await self.redis.set(f"{HEARTBEAT_PREFIX}{worker_id}", info, ex=HEARTBEAT_TTL)

    async def dequeue(self, worker_id: str, timeout: int = BRPOP_TIMEOUT) -> tuple[dict[str, Any], str] | None:
        """Prend le plus ancien job et le place dans la liste « en cours » du worker.

        Renvoie (job, brut) : `brut` sert à `ack` une fois l'analyse terminée.
        """
        raw = await self.redis.blmove(settings.QUEUE_KEY, processing_key(worker_id), timeout, "RIGHT", "LEFT")
        if not raw:
            return None
        return json.loads(raw), raw

    async def ack(self, worker_id: str, raw: str) -> None:
        """Retire le job de la liste « en cours » : l'analyse est terminée (succès, échec ou DLQ)."""
        await self.redis.lrem(processing_key(worker_id), 1, raw)

    async def in_progress(self) -> dict[str, int]:
        """Nombre de jobs « en cours » par worker."""
        prefix = processing_key("")
        return {k.removeprefix(prefix): int(await self.redis.llen(k))
                async for k in self.redis.scan_iter(match=f"{prefix}*")}

    async def recover_orphans(self, worker_id: str, include_self: bool = False) -> dict[str, int]:
        """Remet en file les jobs « en cours » des workers morts (sans battement de cœur).

        `include_self` : reprend aussi la liste de ce worker — uniquement au
        démarrage, quand rien ne tourne encore (redémarrage après plantage).
        Renvoie {"requeued": n, "dead_lettered": m}.
        """
        prefix = processing_key("")
        out = {"requeued": 0, "dead_lettered": 0}
        keys = [k async for k in self.redis.scan_iter(match=f"{prefix}*")]
        for key in keys:
            owner = key.removeprefix(prefix)
            if owner == worker_id:
                if not include_self:
                    continue
            elif await self.redis.exists(f"{HEARTBEAT_PREFIX}{owner}"):
                continue
            # Un seul worker reprend une liste donnée : sinon deux workers remettraient le même job en file.
            lock = f"prreview:recover-lock:{owner}"
            if not await self.redis.set(lock, worker_id, nx=True, ex=30):
                continue
            try:
                await self._requeue_all(key, out)
            finally:
                await self.redis.delete(lock)
        return out

    async def _requeue_all(self, key: str, out: dict[str, int]) -> None:
        while (raw := await self.redis.lindex(key, -1)) is not None:
            job = json.loads(raw)
            job["attempts"] = int(job.get("attempts", 0)) + 1
            # Retrait et remise en file dans une même transaction : jamais perdu, jamais doublé.
            async with self.redis.pipeline(transaction=True) as pipe:
                pipe.lrem(key, -1, raw)
                if job["attempts"] >= settings.QUEUE_MAX_ATTEMPTS:
                    job["error"] = (f"analyse interrompue {job['attempts']} fois "
                                    "(worker arrêté pendant l'analyse) : abandon")
                    job["failed_at"] = time.time()
                    pipe.lpush(settings.DLQ_KEY, json.dumps(job))
                    out["dead_lettered"] += 1
                else:
                    # En tête de file (côté BLMOVE RIGHT) : repris en priorité.
                    pipe.rpush(settings.QUEUE_KEY, json.dumps(job))
                    out["requeued"] += 1
                await pipe.execute()

    # --- File d'échec (DLQ) ------------------------------------------------------

    async def dead_letter(self, job: dict[str, Any], error: str) -> None:
        await self.redis.lpush(settings.DLQ_KEY, json.dumps({**job, "error": error, "failed_at": time.time()}))

    async def dlq_size(self) -> int:
        return int(await self.redis.llen(settings.DLQ_KEY))

    async def dead_letters(self) -> list[dict[str, Any]]:
        """Contenu de la DLQ, du plus ancien au plus récent."""
        return [json.loads(raw) for raw in reversed(await self.redis.lrange(settings.DLQ_KEY, 0, -1))]

    async def replay_dead_letters(self, limit: int | None = None) -> int:
        """Remet en file les jobs de la DLQ (les plus anciens d'abord), sans erreur ni compteur.

        Les clés de déduplication ne s'appliquent pas : c'est une relance voulue.
        Un job dont la PR a reçu un commit plus récent sera simplement marqué obsolète.
        """
        n = 0
        while limit is None or n < limit:
            raw = await self.redis.rpop(settings.DLQ_KEY)
            if raw is None:
                break
            job = json.loads(raw)
            for k in ("error", "failed_at", "attempts"):
                job.pop(k, None)
            await self.redis.lpush(settings.QUEUE_KEY, json.dumps(job))
            n += 1
        return n

    async def purge_dead_letters(self) -> int:
        n = await self.dlq_size()
        await self.redis.delete(settings.DLQ_KEY)
        return n

    async def forget_commits(self, repo: str) -> int:
        """Efface les clés de déduplication par commit d'un dépôt (mode démo uniquement)."""
        keys = [k async for k in self.redis.scan_iter(match=f"prreview:sha:{repo}#*")]
        return await self.redis.delete(*keys) if keys else 0


async def _cli(args: argparse.Namespace) -> None:
    queue = JobQueue()
    try:
        if args.command == "dlq":
            items = await queue.dead_letters()
            for job in items:
                print(f"{job['repo']}#{job['pr_number']}@{job['head_sha'][:7]} — {job.get('error', '')[:150]}")
            print(f"{len(items)} job(s) en DLQ")
        elif args.command == "replay":
            print(f"{await queue.replay_dead_letters(args.limit)} job(s) remis en file")
        elif args.command == "purge":
            print(f"{await queue.purge_dead_letters()} job(s) supprimé(s) de la DLQ")
    finally:
        await queue.redis.aclose()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="File d'échec (DLQ) de l'agent de revue")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("dlq", help="lister les jobs en échec")
    r = sub.add_parser("replay", help="remettre en file les jobs en échec")
    r.add_argument("limit", nargs="?", type=int, help="nombre de jobs (défaut : tous)")
    sub.add_parser("purge", help="vider la DLQ")
    asyncio.run(_cli(p.parse_args()))
