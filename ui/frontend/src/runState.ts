import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { api } from "./api";
import type { ExcerptLine, Finding, RunEvent, Severity, Verdict } from "./types";

// Vue d'une analyse reconstruite événement par événement : la même pour le direct et la relecture.

export type NodeStatus = "idle" | "running" | "ok" | "error" | "stale" | "skipped";
export const PIPELINE = ["fetch_pr", "load_diff", "scan_secrets", "ai_review", "decide", "publish", "alert", "audit"];

export interface NodeView { status: NodeStatus; started?: number; finished?: number; duration?: number }
export interface ChunkView {
  index: number;
  files: string[];
  chars: number;
  status: "queued" | "running" | "done" | "failed";
  started?: number;
  finished?: number;
  duration?: number;
  findings?: number;
  error?: string;
}
export interface FindingView extends Finding {
  state: "raw" | "kept" | "dropped";
  arrivedAt: number;
}

export interface RunView {
  runId: string;
  repo?: string;
  pr?: number;
  sha?: string;
  title?: string;
  author?: string;
  url?: string;
  demo?: boolean;
  queuedAt?: number;
  startedAt?: number;
  finishedAt?: number;
  queueMs?: number | null;
  runMs?: number;
  totalMs?: number;
  model?: string;
  rulesVersion?: string;
  pilot?: boolean;
  publishingEnabled?: boolean;
  concurrency?: number;
  nodes: Record<string, NodeView>;
  failNode?: string;
  chunks: ChunkView[];
  findings: FindingView[];
  files: { path: string; status: string; additions: number; deletions: number }[];
  skipped: { path: string; reason: string; incomplete: boolean }[];
  verdict?: Verdict;
  counts?: Record<Severity, number>;
  incompleteReasons: string[];
  publishSkips: { reason: string; step: string }[];
  published?: { inline: number; github_state: string; mode: string };
  superseded?: boolean;
  stale?: boolean;
  alert?: "sent" | "skipped";
  status: "queued" | "running" | "ok" | "stale" | "superseded" | "error";
  error?: string;
  costUsd?: number | null;
  lastSeq: number;
  lastTs?: number;
}

export const emptyRun = (runId: string): RunView => ({
  runId, nodes: {}, chunks: [], findings: [], files: [], skipped: [], incompleteReasons: [],
  publishSkips: [], status: "queued", lastSeq: -1,
});

export function applyEvent(v: RunView, ev: RunEvent): RunView {
  if (ev.seq <= v.lastSeq) return v;
  const d = ev.data;
  const n: RunView = { ...v, lastSeq: ev.seq, lastTs: ev.ts };
  switch (ev.type) {
    case "run_queued":
      return { ...n, repo: d.repo, pr: d.pr_number, sha: d.head_sha, demo: d.demo, queuedAt: ev.ts, status: "queued" };
    case "run_started":
      return {
        ...n, repo: d.repo, pr: d.pr_number, sha: d.head_sha, startedAt: ev.ts, queueMs: d.queue_ms,
        queuedAt: n.queuedAt ?? (d.queued_at || ev.ts), model: d.model, rulesVersion: d.rules_version,
        pilot: d.pilot_mode, publishingEnabled: d.publishing_enabled, concurrency: d.concurrency, status: "running",
      };
    case "node_started":
      return { ...n, nodes: { ...n.nodes, [d.node]: { status: "running", started: ev.ts } } };
    case "node_finished": {
      const prev = n.nodes[d.node] || {};
      const status: NodeStatus = d.status === "error" ? "error" : d.status === "stale" ? "stale" : "ok";
      return {
        ...n,
        failNode: status === "error" ? d.node : n.failNode,
        nodes: { ...n.nodes, [d.node]: { ...prev, status, finished: ev.ts, duration: d.duration_ms } },
      };
    }
    case "pr_info":
      return { ...n, title: d.title, author: d.author, url: d.url };
    case "stale":
      return { ...n, stale: true };
    case "diff_loaded":
      return { ...n, files: d.files || [], skipped: d.skipped || [] };
    case "chunks_planned":
      return {
        ...n, concurrency: d.concurrency,
        chunks: (d.chunks || []).map((c: any) => ({ index: c.index, files: c.files, chars: c.chars, status: "queued" })),
      };
    case "chunk_started":
      return { ...n, chunks: n.chunks.map((c) => (c.index === d.index ? { ...c, status: "running", started: ev.ts } : c)) };
    case "chunk_finished":
    case "chunk_failed":
      return {
        ...n,
        chunks: n.chunks.map((c) =>
          c.index === d.index
            ? { ...c, status: ev.type === "chunk_failed" ? "failed" : "done", finished: ev.ts, duration: d.duration_ms,
                findings: d.findings, error: d.error }
            : c),
      };
    case "finding":
      if (n.findings.some((f) => f.id === d.id)) return n;
      return {
        ...n,
        findings: [...n.findings, { ...(d as Finding), excerpt: (d.excerpt || []) as ExcerptLine[], state: "raw", arrivedAt: ev.ts }],
      };
    case "findings_validated": {
      const kept = new Set<string>(d.kept || []);
      const reasons = new Map<string, string>((d.dropped || []).map((x: any) => [x.id, x.reason]));
      return {
        ...n,
        findings: n.findings.map((f) =>
          kept.has(f.id) ? { ...f, state: "kept", kept: true }
            : { ...f, state: "dropped", kept: false, drop_reason: reasons.get(f.id) ?? f.drop_reason }),
      };
    }
    case "verdict":
      return { ...n, verdict: d.verdict, counts: d.counts, incompleteReasons: d.incomplete_reasons || [],
               rulesVersion: d.rules_version ?? n.rulesVersion, pilot: d.pilot_mode ?? n.pilot };
    case "publication_skipped":
      return { ...n, publishSkips: [...n.publishSkips, { reason: d.reason, step: d.step }] };
    case "superseded":
      return { ...n, superseded: true };
    case "published":
      return { ...n, published: { inline: d.inline, github_state: d.github_state, mode: d.mode } };
    case "alert_sent":
      return { ...n, alert: "sent" };
    case "alert_skipped":
      return { ...n, alert: "skipped" };
    case "error":
      return { ...n, error: d.message };
    case "run_finished": {
      // Nœuds jamais atteints : grisés.
      const nodes = { ...n.nodes };
      for (const name of PIPELINE) if (!nodes[name]) nodes[name] = { status: "skipped" };
      return {
        ...n, nodes, status: d.status, finishedAt: ev.ts, runMs: d.run_ms, totalMs: d.total_ms,
        queueMs: d.queue_ms ?? n.queueMs, costUsd: d.cost_usd, error: d.error ?? n.error,
        verdict: d.verdict ?? n.verdict,
      };
    }
    default:
      return n;
  }
}

type Action = { kind: "reset"; runId: string } | { kind: "events"; events: RunEvent[] };

function reducer(state: RunView, action: Action): RunView {
  if (action.kind === "reset") return emptyRun(action.runId);
  return action.events.reduce(applyEvent, state);
}

/** Suit une analyse en direct (SSE) : historique depuis la base, puis flux. */
export function useLiveRun(runId: string | null, enabled = true) {
  const [view, dispatch] = useReducer(reducer, emptyRun(runId || ""));
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    if (!runId || !enabled) return;
    dispatch({ kind: "reset", runId });
    const es = new EventSource(`/ui/api/runs/${runId}/stream`, { withCredentials: true });
    // Regroupement par minuterie (pas requestAnimationFrame, suspendu quand l'onglet n'est pas affiché).
    let buffer: RunEvent[] = [];
    let timer = 0;
    const flush = () => {
      timer = 0;
      const batch = buffer;
      buffer = [];
      if (batch.length) dispatch({ kind: "events", events: batch });
    };
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);
    es.onmessage = (m) => {
      buffer.push(JSON.parse(m.data));
      if (!timer) timer = window.setTimeout(flush, 40);
    };
    return () => {
      es.close();
      if (timer) window.clearTimeout(timer);
      setConnected(false);
    };
  }, [runId, enabled]);
  return { view, connected };
}

export interface Replay {
  view: RunView;
  playing: boolean;
  progress: number;
  speed: number;
  total: number;
  play: () => void;
  pause: () => void;
  restart: () => void;
  setSpeed: (s: number) => void;
  seekEnd: () => void;
}

/** Relecture d'une analyse passée à partir de ses événements enregistrés, au rythme réel (accéléré). */
export function useReplay(runId: string | null, active: boolean): Replay {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [view, dispatch] = useReducer(reducer, emptyRun(runId || ""));
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [cursor, setCursor] = useState(0);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    if (!runId || !active) return;
    let cancelled = false;
    api<RunEvent[]>(`/runs/${runId}/events`).then((evs) => {
      if (cancelled) return;
      setEvents(evs);
      dispatch({ kind: "reset", runId });
      setCursor(0);
      setPlaying(true);
    });
    return () => {
      cancelled = true;
    };
  }, [runId, active]);

  useEffect(() => {
    if (!playing || cursor >= events.length) {
      if (cursor >= events.length && events.length) setPlaying(false);
      return;
    }
    const prev = cursor === 0 ? events[0].ts : events[cursor - 1].ts;
    // La file d'attente peut durer : on plafonne les silences pour garder une relecture vivante.
    const gap = Math.min(Math.max((events[cursor].ts - prev) * 1000, 0), 4000) / speed;
    timer.current = window.setTimeout(() => {
      dispatch({ kind: "events", events: [events[cursor]] });
      setCursor((c) => c + 1);
    }, gap);
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [playing, cursor, events, speed]);

  const restart = useCallback(() => {
    dispatch({ kind: "reset", runId: runId || "" });
    setCursor(0);
    setPlaying(true);
  }, [runId]);
  const seekEnd = useCallback(() => {
    dispatch({ kind: "events", events: events.slice(cursor) });
    setCursor(events.length);
    setPlaying(false);
  }, [events, cursor]);

  return {
    view, playing, speed, total: events.length,
    progress: events.length ? cursor / events.length : 0,
    play: () => {
      if (cursor >= events.length) restart();
      else setPlaying(true);
    },
    pause: () => setPlaying(false),
    restart, setSpeed, seekEnd,
  };
}
