"""Diffusion en direct : lit le Redis Stream des événements et répartit vers les clients SSE."""
import asyncio
import json
import logging

log = logging.getLogger("pr-review.live")


class LiveHub:
    def __init__(self, redis, stream_key: str):
        self.redis, self.key = redis, stream_key
        self.subs: list[tuple[str | None, asyncio.Queue]] = []
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    def subscribe(self, run_id: str | None = None) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=2000)
        self.subs.append((run_id, q))
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subs = [(r, s) for r, s in self.subs if s is not q]

    async def _loop(self) -> None:
        last = "$"
        while True:
            try:
                res = await self.redis.xread({self.key: last}, block=5000, count=500)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                log.warning("lecture du flux d'événements impossible : %s", e)
                await asyncio.sleep(1)
                continue
            for _stream, entries in res or []:
                for entry_id, f in entries:
                    last = entry_id
                    try:
                        ev = {"run_id": f["run_id"], "seq": int(f["seq"]), "type": f["type"],
                              "ts": float(f["ts"]), "data": json.loads(f["data"])}
                    except (KeyError, ValueError):
                        continue
                    for run_id, q in list(self.subs):
                        if run_id is None or run_id == ev["run_id"]:
                            try:
                                q.put_nowait(ev)
                            except asyncio.QueueFull:
                                pass  # le client rattrape depuis la base (trou de numérotation)
