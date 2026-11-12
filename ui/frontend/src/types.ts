export type Verdict = "BLOQUANTE" | "A_VERIFIER" | "CONTROLES_SATISFAITS" | "ANALYSE_INCOMPLETE";
export type RunStatus = "queued" | "running" | "ok" | "stale" | "superseded" | "error";
export type Severity = "critical" | "major" | "minor" | "info";
export type Rating = "pertinente" | "fausse_alerte";

export interface RunEvent {
  run_id: string;
  seq: number;
  ts: number;
  type: string;
  data: Record<string, any>;
}

export interface ExcerptLine { n: number | null; kind: "+" | "-" | " "; text: string; target: boolean }

export interface Finding {
  id: string;
  path: string;
  line: number | null;
  severity: Severity;
  category: string;
  title: string;
  explanation: string;
  suggestion: string;
  source: string;
  chunk: number | null;
  excerpt: ExcerptLine[];
  kept?: boolean | null;
  drop_reason?: string | null;
  rating?: Rating | null;
  rated_by?: string | null;
}

export interface RunRow {
  id: string;
  repo: string;
  pr_number: number;
  head_sha: string;
  title: string | null;
  author: string | null;
  status: RunStatus;
  verdict: Verdict | null;
  model: string | null;
  demo: boolean;
  queued_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  queue_ms: number | null;
  run_ms: number | null;
  total_ms: number | null;
  findings_count: number | null;
  counts: Record<Severity, number> | null;
  chunks_total: number | null;
  chunks_failed: number | null;
  cost_usd: number | null;
  publish_skipped: string | null;
}

export interface RunDetail {
  run: RunRow & {
    rules_version: string | null;
    pilot_mode: boolean | null;
    publishing_enabled: boolean | null;
    incomplete_reasons: string[] | null;
    skipped: { path: string; reason: string }[] | null;
    published: boolean | null;
    error: string | null;
    pr_url: string | null;
  };
  findings: Finding[];
}

export interface WorkerInfo { host: string; provider: string; model: string; dry_run: boolean; pilot_mode: boolean; concurrency: number }

export interface AppConfig {
  workers: WorkerInfo[];
  publishing: { enabled: boolean; updated_by: string | null; updated_at: string | null };
  store: boolean;
  pilot_mode: boolean;
  dry_run: boolean;
  demo_mode: boolean;
  rules_version: string;
  provider: string;
  model: string;
  concurrency: number;
  check_name: string;
  auth_mode: string;
}

export interface User { login: string; role: "admin" | "lecteur" }

export interface Stats {
  runs: number;
  errors: number;
  superseded: number;
  p50_total_ms: number | null;
  p95_total_ms: number | null;
  p50_queue_ms: number | null;
  p95_queue_ms: number | null;
  p95_run_ms: number | null;
  chunks_total: number;
  chunks_failed: number;
  cost_usd: number;
  verdicts: Partial<Record<Verdict, number>>;
  durations_ms: number[];
  chunk_failure_rate: number | null;
  dlq_size: number | null;
  relevance_target: number;
  feedback: { pertinente: number; fausse_alerte: number; rated: number; findings_kept: number; relevance_rate: number | null };
}
