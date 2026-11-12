"""Journal d'événements des analyses, interrupteur de publication et données de l'interface.

- Postgres = trace durable : runs, events (rejouables), findings, feedback, settings.
- Redis Stream (`EVENTS_STREAM_KEY`) = diffusion en direct vers l'API (SSE).

Règles :
- Tout est masqué une seconde fois (`redact_obj`) avant écriture : même si un
  nœud émettait par erreur une valeur non masquée, un secret n'atteint jamais
  la base ni le flux.
- Le suivi ne doit jamais faire échouer une revue : les erreurs d'écriture sont
  journalisées et avalées.
- L'interrupteur est relu à chaque écriture vers GitHub ; si la base est
  injoignable, la dernière valeur lue (ou la valeur initiale) s'applique.
"""
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from agent.secrets_scan import redact_obj

log = logging.getLogger("pr-review.store")

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  delivery_id TEXT,
  repo TEXT NOT NULL,
  pr_number INT NOT NULL,
  head_sha TEXT NOT NULL,
  title TEXT, author TEXT, pr_url TEXT,
  status TEXT NOT NULL,
  verdict TEXT, rules_version TEXT, model TEXT,
  pilot_mode BOOLEAN, publishing_enabled BOOLEAN, demo BOOLEAN NOT NULL DEFAULT FALSE,
  queued_at TIMESTAMPTZ, started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ,
  queue_ms INT, run_ms INT, total_ms INT,
  chunks_total INT, chunks_failed INT, findings_count INT, counts JSONB, cost_usd DOUBLE PRECISION,
  incomplete_reasons JSONB, skipped JSONB, published BOOLEAN, publish_skipped TEXT, error TEXT
);
CREATE INDEX IF NOT EXISTS runs_queued_at_idx ON runs (queued_at DESC);
CREATE TABLE IF NOT EXISTS events (
  run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  seq INT NOT NULL,
  ts TIMESTAMPTZ NOT NULL,
  type TEXT NOT NULL,
  data JSONB NOT NULL,
  PRIMARY KEY (run_id, seq)
);
CREATE TABLE IF NOT EXISTS findings (
  run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  id TEXT NOT NULL,
  path TEXT, line INT, severity TEXT, category TEXT, title TEXT, explanation TEXT, suggestion TEXT,
  source TEXT, chunk INT, excerpt JSONB, kept BOOLEAN, drop_reason TEXT,
  PRIMARY KEY (run_id, id)
);
CREATE TABLE IF NOT EXISTS feedback (
  run_id TEXT NOT NULL,
  finding_id TEXT NOT NULL,
  rating TEXT NOT NULL CHECK (rating IN ('pertinente', 'fausse_alerte')),
  user_login TEXT NOT NULL,
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (run_id, finding_id),
  FOREIGN KEY (run_id, finding_id) REFERENCES findings (run_id, id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY, value JSONB NOT NULL, updated_by TEXT, updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS settings_history (
  id BIGSERIAL PRIMARY KEY, key TEXT NOT NULL, value JSONB NOT NULL, updated_by TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

FINAL_STATUSES = ("ok", "stale", "superseded", "error")


def _dt(ts: float | None) -> datetime | None:
    return datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None


class NullStore:
    """Sans base configurée : rien n'est conservé, l'interrupteur suit la configuration."""

    available = False

    def __init__(self, default_publishing: bool = True):
        self.default_publishing = default_publishing

    async def open(self) -> None: ...
    async def close(self) -> None: ...
    async def create_run(self, job: dict, demo: bool = False) -> None: ...
    async def emit(self, run_id: str, type_: str, data: dict, ts: float | None = None) -> int | None:
        return None

    async def publishing_enabled(self) -> bool:
        return self.default_publishing

    async def publishing_state(self) -> dict:
        return {"enabled": await self.publishing_enabled(), "updated_by": None, "updated_at": None}

    async def set_publishing(self, enabled: bool, by: str) -> None:
        self.default_publishing = enabled


class MemoryStore(NullStore):
    """Pour les tests : garde tout en mémoire, avec le même masquage que Postgres."""

    available = True

    def __init__(self, default_publishing: bool = True):
        super().__init__(default_publishing)
        self.runs: dict[str, dict] = {}
        self.events: list[dict] = []
        self.history: list[dict] = []

    async def create_run(self, job: dict, demo: bool = False) -> None:
        self.runs[job["run_id"]] = {"status": "queued", "demo": demo, **redact_obj(job)}
        await self.emit(job["run_id"], "run_queued", {"repo": job["repo"], "pr_number": job["pr_number"],
                                                      "head_sha": job["head_sha"]}, job.get("queued_at"))

    async def emit(self, run_id: str, type_: str, data: dict, ts: float | None = None) -> int:
        seq = sum(1 for e in self.events if e["run_id"] == run_id)
        self.events.append({"run_id": run_id, "seq": seq, "ts": ts or time.time(), "type": type_,
                            "data": redact_obj(data)})
        return seq

    async def set_publishing(self, enabled: bool, by: str) -> None:
        self.default_publishing = enabled
        self.history.append({"enabled": enabled, "by": by})


class PgStore(NullStore):
    available = True

    def __init__(self, dsn: str, redis_client=None, stream_key: str = "prreview:events",
                 stream_maxlen: int = 20000, default_publishing: bool = True):
        super().__init__(default_publishing)
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool
        self.pool = AsyncConnectionPool(dsn, min_size=1, max_size=8, open=False,
                                        kwargs={"autocommit": True, "row_factory": dict_row})
        self.redis = redis_client
        self.stream_key, self.stream_maxlen = stream_key, stream_maxlen
        self._publishing_cache: bool | None = None

    async def open(self) -> None:
        await self.pool.open(wait=True, timeout=30)
        async with self.pool.connection() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(724201)")  # api et worker démarrent ensemble
                await conn.execute(SCHEMA)

    async def close(self) -> None:
        await self.pool.close()

    # ------------------------------------------------------------------ écriture

    async def create_run(self, job: dict, demo: bool = False) -> None:
        try:
            async with self.pool.connection() as conn:
                await conn.execute(
                    "INSERT INTO runs (id, delivery_id, repo, pr_number, head_sha, status, queued_at, demo) "
                    "VALUES (%s, %s, %s, %s, %s, 'queued', %s, %s) ON CONFLICT (id) DO NOTHING",
                    (job["run_id"], job.get("delivery_id"), job["repo"], job["pr_number"], job["head_sha"],
                     _dt(job.get("queued_at")), demo))
        except Exception:  # noqa: BLE001
            log.exception("création du run %s impossible", job.get("run_id"))
            return
        await self.emit(job["run_id"], "run_queued",
                        {"repo": job["repo"], "pr_number": job["pr_number"], "head_sha": job["head_sha"],
                         "demo": demo}, job.get("queued_at"))

    async def emit(self, run_id: str, type_: str, data: dict, ts: float | None = None) -> int | None:
        from psycopg.types.json import Jsonb
        data = redact_obj(data)
        ts = ts or time.time()
        try:
            async with self.pool.connection() as conn:
                async with conn.transaction():
                    if type_ == "run_started":
                        await conn.execute(
                            "INSERT INTO runs (id, delivery_id, repo, pr_number, head_sha, status, queued_at) "
                            "VALUES (%s, %s, %s, %s, %s, 'running', %s) ON CONFLICT (id) DO NOTHING",
                            (run_id, data.get("delivery_id"), data["repo"], data["pr_number"],
                             data["head_sha"], _dt(data.get("queued_at")) or _dt(ts)))
                    # Verrou de ligne : numérotation sans trou ni doublon par run.
                    await conn.execute("SELECT 1 FROM runs WHERE id = %s FOR UPDATE", (run_id,))
                    cur = await conn.execute(
                        "SELECT COALESCE(MAX(seq) + 1, 0) AS seq FROM events WHERE run_id = %s", (run_id,))
                    seq = (await cur.fetchone())["seq"]
                    await conn.execute(
                        "INSERT INTO events (run_id, seq, ts, type, data) VALUES (%s, %s, %s, %s, %s)",
                        (run_id, seq, _dt(ts), type_, Jsonb(data)))
                    await self._project(conn, run_id, type_, data, ts)
        except Exception:  # noqa: BLE001
            log.exception("événement %s du run %s non enregistré", type_, run_id)
            return None
        if self.redis is not None:
            try:
                await self.redis.xadd(self.stream_key, {
                    "run_id": run_id, "seq": seq, "type": type_, "ts": ts,
                    "data": json.dumps(data, ensure_ascii=False, default=str),
                }, maxlen=self.stream_maxlen, approximate=True)
            except Exception:  # noqa: BLE001
                log.exception("diffusion de l'événement %s impossible", type_)
        return seq

    async def _project(self, conn, run_id: str, type_: str, d: dict, ts: float) -> None:
        """Met à jour les tables de lecture (runs, findings) à partir des événements."""
        from psycopg.types.json import Jsonb
        if type_ == "run_started":
            await conn.execute(
                "UPDATE runs SET status = 'running', started_at = %s, queue_ms = %s, model = %s, "
                "rules_version = %s, pilot_mode = %s, publishing_enabled = %s WHERE id = %s",
                (_dt(ts), d.get("queue_ms"), d.get("model"), d.get("rules_version"), d.get("pilot_mode"),
                 d.get("publishing_enabled"), run_id))
        elif type_ == "pr_info":
            await conn.execute("UPDATE runs SET title = %s, author = %s, pr_url = %s WHERE id = %s",
                               (d.get("title"), d.get("author"), d.get("url"), run_id))
        elif type_ == "finding":
            await conn.execute(
                "INSERT INTO findings (run_id, id, path, line, severity, category, title, explanation, "
                "suggestion, source, chunk, excerpt) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (run_id, id) DO NOTHING",
                (run_id, d["id"], d.get("path"), d.get("line"), d.get("severity"), d.get("category"),
                 d.get("title"), d.get("explanation"), d.get("suggestion"), d.get("source"), d.get("chunk"),
                 Jsonb(d.get("excerpt") or [])))
        elif type_ == "findings_validated":
            await conn.execute("UPDATE findings SET kept = (id = ANY(%s)) WHERE run_id = %s",
                               (d.get("kept") or [], run_id))
            for item in d.get("dropped") or []:
                await conn.execute("UPDATE findings SET drop_reason = %s WHERE run_id = %s AND id = %s",
                                   (item["reason"], run_id, item["id"]))
        elif type_ == "verdict":
            await conn.execute("UPDATE runs SET verdict = %s, counts = %s WHERE id = %s",
                               (d.get("verdict"), Jsonb(d.get("counts") or {}), run_id))
        elif type_ == "run_finished":
            await conn.execute(
                "UPDATE runs SET status = %s, verdict = COALESCE(%s, verdict), finished_at = %s, run_ms = %s, "
                "total_ms = %s, chunks_total = %s, chunks_failed = %s, findings_count = %s, cost_usd = %s, "
                "incomplete_reasons = %s, skipped = %s, published = %s, publish_skipped = %s, error = %s "
                "WHERE id = %s",
                (d.get("status"), d.get("verdict"), _dt(ts), d.get("run_ms"), d.get("total_ms"),
                 d.get("chunks_total"), d.get("chunks_failed"), d.get("findings_count"), d.get("cost_usd"),
                 Jsonb(d.get("incomplete_reasons") or []), Jsonb(d.get("skipped") or []), d.get("published"),
                 d.get("publish_skipped"), d.get("error"), run_id))

    # ------------------------------------------------------------ interrupteur

    async def publishing_enabled(self) -> bool:
        try:
            async with self.pool.connection() as conn:
                cur = await conn.execute("SELECT value FROM settings WHERE key = 'publishing_enabled'")
                row = await cur.fetchone()
            self._publishing_cache = bool(row["value"]) if row else self.default_publishing
        except Exception:  # noqa: BLE001
            log.exception("interrupteur illisible : dernière valeur connue appliquée")
            if self._publishing_cache is None:
                return self.default_publishing
        return self._publishing_cache

    async def publishing_state(self) -> dict:
        async with self.pool.connection() as conn:
            cur = await conn.execute("SELECT value, updated_by, updated_at FROM settings "
                                     "WHERE key = 'publishing_enabled'")
            row = await cur.fetchone()
        if not row:
            return {"enabled": self.default_publishing, "updated_by": None, "updated_at": None}
        return {"enabled": bool(row["value"]), "updated_by": row["updated_by"],
                "updated_at": row["updated_at"].isoformat()}

    async def set_publishing(self, enabled: bool, by: str) -> None:
        from psycopg.types.json import Jsonb
        async with self.pool.connection() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO settings (key, value, updated_by, updated_at) VALUES ('publishing_enabled', %s, %s, now()) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_by = EXCLUDED.updated_by, "
                    "updated_at = now()", (Jsonb(enabled), by))
                await conn.execute("INSERT INTO settings_history (key, value, updated_by) "
                                   "VALUES ('publishing_enabled', %s, %s)", (Jsonb(enabled), by))
        self._publishing_cache = enabled

    async def publishing_history(self, limit: int = 20) -> list[dict]:
        async with self.pool.connection() as conn:
            cur = await conn.execute("SELECT value, updated_by, updated_at FROM settings_history "
                                     "WHERE key = 'publishing_enabled' ORDER BY id DESC LIMIT %s", (limit,))
            return [{"enabled": bool(r["value"]), "by": r["updated_by"], "at": r["updated_at"].isoformat()}
                    for r in await cur.fetchall()]

    # ----------------------------------------------------------------- lecture

    @staticmethod
    def _filters(repo: str | None, verdict: str | None, status: str | None, date_from: str | None,
                 date_to: str | None, demo: bool | None, p: str = "") -> tuple[str, list]:
        where, args = [], []
        if repo:
            where.append(f"{p}repo = %s"); args.append(repo)
        if verdict:
            where.append(f"{p}verdict = %s"); args.append(verdict)
        if status:
            where.append(f"{p}status = %s"); args.append(status)
        if date_from:
            where.append(f"{p}queued_at >= %s::date"); args.append(date_from)
        if date_to:
            where.append(f"{p}queued_at < %s::date + 1"); args.append(date_to)
        if demo is not None:
            where.append(f"{p}demo = %s"); args.append(demo)
        return ("WHERE " + " AND ".join(where)) if where else "", args

    async def list_runs(self, repo=None, verdict=None, status=None, date_from=None, date_to=None,
                        demo=None, limit: int = 50, offset: int = 0) -> dict:
        where, args = self._filters(repo, verdict, status, date_from, date_to, demo)
        async with self.pool.connection() as conn:
            cur = await conn.execute(f"SELECT count(*) AS n FROM runs {where}", args)
            total = (await cur.fetchone())["n"]
            cur = await conn.execute(
                "SELECT id, repo, pr_number, head_sha, title, author, status, verdict, model, demo, queued_at, "
                "started_at, finished_at, queue_ms, run_ms, total_ms, findings_count, counts, chunks_total, "
                f"chunks_failed, cost_usd, publish_skipped FROM runs {where} "
                "ORDER BY queued_at DESC NULLS LAST LIMIT %s OFFSET %s", [*args, limit, offset])
            rows = await cur.fetchall()
        return {"total": total, "runs": [_jsonable(r) for r in rows]}

    async def repos(self) -> list[str]:
        async with self.pool.connection() as conn:
            cur = await conn.execute("SELECT DISTINCT repo FROM runs ORDER BY repo")
            return [r["repo"] for r in await cur.fetchall()]

    async def get_run(self, run_id: str) -> dict | None:
        async with self.pool.connection() as conn:
            cur = await conn.execute("SELECT * FROM runs WHERE id = %s", (run_id,))
            run = await cur.fetchone()
            if not run:
                return None
            cur = await conn.execute(
                "SELECT f.*, fb.rating, fb.user_login AS rated_by FROM findings f "
                "LEFT JOIN feedback fb ON fb.run_id = f.run_id AND fb.finding_id = f.id "
                "WHERE f.run_id = %s ORDER BY f.id", (run_id,))
            findings = await cur.fetchall()
        return {"run": _jsonable(run), "findings": [_jsonable(f) for f in findings]}

    async def events(self, run_id: str, after: int = -1) -> list[dict]:
        async with self.pool.connection() as conn:
            cur = await conn.execute("SELECT seq, ts, type, data FROM events WHERE run_id = %s AND seq > %s "
                                     "ORDER BY seq", (run_id, after))
            return [{"run_id": run_id, "seq": r["seq"], "ts": r["ts"].timestamp(), "type": r["type"],
                     "data": r["data"]} for r in await cur.fetchall()]

    async def set_feedback(self, run_id: str, finding_id: str, rating: str, by: str) -> bool:
        async with self.pool.connection() as conn:
            cur = await conn.execute("SELECT 1 FROM findings WHERE run_id = %s AND id = %s AND kept",
                                     (run_id, finding_id))
            if not await cur.fetchone():
                return False
            await conn.execute(
                "INSERT INTO feedback (run_id, finding_id, rating, user_login, ts) VALUES (%s, %s, %s, %s, now()) "
                "ON CONFLICT (run_id, finding_id) DO UPDATE SET rating = EXCLUDED.rating, "
                "user_login = EXCLUDED.user_login, ts = now()", (run_id, finding_id, rating, by))
        return True

    async def clear_feedback(self, run_id: str, finding_id: str) -> None:
        async with self.pool.connection() as conn:
            await conn.execute("DELETE FROM feedback WHERE run_id = %s AND finding_id = %s", (run_id, finding_id))

    async def stats(self, repo=None, date_from=None, date_to=None, demo=None) -> dict:
        where, args = self._filters(repo, None, None, date_from, date_to, demo)
        done = (where + " AND " if where else "WHERE ") + "status IN ('ok', 'stale', 'superseded', 'error')"
        async with self.pool.connection() as conn:
            cur = await conn.execute(
                "SELECT count(*) AS runs, "
                "count(*) FILTER (WHERE status = 'error') AS errors, "
                "count(*) FILTER (WHERE status IN ('stale', 'superseded')) AS superseded, "
                "percentile_cont(0.5) WITHIN GROUP (ORDER BY total_ms) AS p50_total_ms, "
                "percentile_cont(0.95) WITHIN GROUP (ORDER BY total_ms) AS p95_total_ms, "
                "percentile_cont(0.5) WITHIN GROUP (ORDER BY queue_ms) AS p50_queue_ms, "
                "percentile_cont(0.95) WITHIN GROUP (ORDER BY queue_ms) AS p95_queue_ms, "
                "percentile_cont(0.95) WITHIN GROUP (ORDER BY run_ms) AS p95_run_ms, "
                "COALESCE(sum(chunks_total), 0) AS chunks_total, COALESCE(sum(chunks_failed), 0) AS chunks_failed, "
                "COALESCE(sum(cost_usd), 0) AS cost_usd "
                f"FROM runs {done}", args)
            summary = _jsonable(await cur.fetchone())
            cur = await conn.execute(
                f"SELECT verdict, count(*) AS n FROM runs {done} AND verdict IS NOT NULL AND status = 'ok' "
                "GROUP BY verdict", args)
            verdicts = {r["verdict"]: r["n"] for r in await cur.fetchall()}
            cur = await conn.execute(
                f"SELECT total_ms FROM runs {done} AND total_ms IS NOT NULL ORDER BY queued_at DESC LIMIT 1000", args)
            durations = [r["total_ms"] for r in await cur.fetchall()]
            rwhere, rargs = self._filters(repo, None, None, date_from, date_to, demo, p="r.")
            cur = await conn.execute(
                f"SELECT fb.rating, count(*) AS n FROM feedback fb JOIN runs r ON r.id = fb.run_id {rwhere} "
                "GROUP BY fb.rating", rargs)
            ratings = {r["rating"]: r["n"] for r in await cur.fetchall()}
            cur = await conn.execute(
                "SELECT count(*) AS n FROM findings f JOIN runs r ON r.id = f.run_id "
                f"{rwhere + ' AND' if rwhere else 'WHERE'} f.kept", rargs)
            kept = (await cur.fetchone())["n"]
        rated = ratings.get("pertinente", 0) + ratings.get("fausse_alerte", 0)
        return {
            **summary,
            "verdicts": verdicts,
            "durations_ms": durations,
            "chunk_failure_rate": (summary["chunks_failed"] / summary["chunks_total"])
            if summary["chunks_total"] else None,
            "feedback": {"pertinente": ratings.get("pertinente", 0),
                         "fausse_alerte": ratings.get("fausse_alerte", 0),
                         "rated": rated, "findings_kept": kept,
                         "relevance_rate": ratings.get("pertinente", 0) / rated if rated else None},
        }


def _jsonable(row: dict | None) -> dict:
    out: dict[str, Any] = {}
    for k, v in (row or {}).items():
        out[k] = v.isoformat() if isinstance(v, datetime) else v
    return out


def build_store(settings, redis_client=None) -> NullStore:
    if not settings.DATABASE_URL:
        return NullStore(settings.PUBLISH_ENABLED)
    return PgStore(settings.DATABASE_URL, redis_client, settings.EVENTS_STREAM_KEY,
                   settings.EVENTS_STREAM_MAXLEN, settings.PUBLISH_ENABLED)
