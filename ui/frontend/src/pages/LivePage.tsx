import { useEffect, useRef, useState } from "react";
import { api, jsonBody, query } from "../api";
import { RunMonitor } from "../components/RunMonitor";
import { Empty, Icon, Panel, VerdictBadge } from "../components/ui";
import { STATUS_LABEL, duration, relative } from "../format";
import { Link } from "../router";
import { useLiveRun } from "../runState";
import type { AppConfig, RunEvent, RunRow, User } from "../types";
import { useRunDetail } from "./RunPage";

interface DemoCatalog { repo: string; prs: { number: number; title: string; files: string[]; stale: boolean }[] }

const DEMO_HINT: Record<number, string> = {
  101: "secret en dur, injection SQL, route sans contrôle d’accès",
  102: "service propre avec son test",
  103: "fichier de 2 000 lignes + service sans test",
  104: "webhook sur un ancien commit",
};

function DemoLauncher({ onLaunched }: { onLaunched: (runIds: string[]) => void }) {
  const [catalog, setCatalog] = useState<DemoCatalog | null>(null);
  const [picked, setPicked] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    api<DemoCatalog>("/demo").then((c) => {
      setCatalog(c);
      setPicked(c.prs.map((p) => p.number));
    }).catch((e) => setError(e.message));
  }, []);

  async function launch() {
    setBusy(true);
    setError("");
    try {
      const r = await api<{ launched: { number: number; status: string; run_id?: string }[] }>(
        "/demo/launch", { method: "POST", body: jsonBody({ prs: picked }) });
      onLaunched(r.launched.map((l) => l.run_id).filter(Boolean) as string[]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "échec");
    } finally {
      setBusy(false);
    }
  }

  if (!catalog) return error ? <p className="form-error">{error}</p> : null;
  return (
    <div className="demo">
      <div className="demo-head">
        <Icon name="flask" size={16} />
        <div>
          <strong>Démo · PR fictives</strong>
          <span>{catalog.repo} · faux GitHub, vrai pipeline</span>
        </div>
      </div>
      <ul className="demo-list">
        {catalog.prs.map((p) => (
          <li key={p.number}>
            <label>
              <input type="checkbox" checked={picked.includes(p.number)}
                onChange={(e) => setPicked((s) => (e.target.checked ? [...s, p.number] : s.filter((n) => n !== p.number)))} />
              <span className="demo-pr">#{p.number}</span>
              <span className="demo-title">{p.title}<small>{DEMO_HINT[p.number] || `${p.files.length} fichier(s)`}</small></span>
            </label>
          </li>
        ))}
      </ul>
      <button type="button" className="btn btn-primary btn-block" disabled={busy || !picked.length} onClick={launch}>
        <Icon name="bolt" size={15} /> {busy ? "Envoi des webhooks…" : `Lancer ${picked.length} PR`}
      </button>
      {error && <p className="form-error">{error}</p>}
    </div>
  );
}

export function LivePage({ config, user }: { config: AppConfig; user: User }) {
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [follow, setFollow] = useState<string | null>(null);
  const auto = useRef(true);

  useEffect(() => {
    api<{ runs: RunRow[] }>(`/runs${query({ limit: 25 })}`).then((r) => {
      setRuns(r.runs);
      const active = r.runs.find((x) => x.status === "running") || r.runs.find((x) => x.status === "queued") || r.runs[0];
      setFollow((f) => f ?? active?.id ?? null);
    });
    const es = new EventSource("/ui/api/stream", { withCredentials: true });
    es.onmessage = (m) => {
      const ev: RunEvent = JSON.parse(m.data);
      setRuns((list) => {
        const i = list.findIndex((r) => r.id === ev.run_id);
        const base: RunRow = i >= 0 ? list[i] : {
          id: ev.run_id, repo: ev.data.repo ?? "…", pr_number: ev.data.pr_number ?? 0, head_sha: ev.data.head_sha ?? "",
          title: null, author: null, status: "queued", verdict: null, model: null, demo: Boolean(ev.data.demo),
          queued_at: new Date(ev.ts * 1000).toISOString(), started_at: null, finished_at: null, queue_ms: null,
          run_ms: null, total_ms: null, findings_count: null, counts: null, chunks_total: null, chunks_failed: null,
          cost_usd: null, publish_skipped: null,
        };
        const row: RunRow = { ...base };
        if (ev.type === "run_started") row.status = "running";
        if (ev.type === "pr_info") { row.title = ev.data.title; row.author = ev.data.author; }
        if (ev.type === "verdict") row.verdict = ev.data.verdict;
        if (ev.type === "run_finished") { row.status = ev.data.status; row.total_ms = ev.data.total_ms; row.verdict = ev.data.verdict ?? row.verdict; }
        const next = i >= 0 ? list.map((r, k) => (k === i ? row : r)) : [row, ...list];
        return next.slice(0, 40);
      });
      if (ev.type === "run_started" && auto.current) setFollow(ev.run_id);
    };
    return () => es.close();
  }, []);

  const { view, connected } = useLiveRun(follow);
  const finished = !["queued", "running"].includes(view.status);
  const detail = useRunDetail(follow, finished);
  const queued = runs.filter((r) => r.status === "queued").length;
  const active = runs.filter((r) => r.status === "running").length;

  return (
    <div className="page live">
      <aside className="live-side">
        {config.demo_mode && user.role === "admin" && (
          <DemoLauncher onLaunched={(ids) => { auto.current = true; if (ids[0]) setFollow(ids[0]); }} />
        )}
        <Panel title="Analyses récentes" aside={<span className="muted">{active} en cours · {queued} en file</span>}>
          {runs.length === 0 && <p className="muted pad">Aucune analyse pour l’instant.</p>}
          <ul className="run-list">
            {runs.map((r) => (
              <li key={r.id}>
                <button type="button" className={`run-item ${follow === r.id ? "on" : ""} run-${r.status}`}
                  onClick={() => { auto.current = false; setFollow(r.id); }}>
                  <span className="run-item-top">
                    <span className="run-item-repo">{r.repo.split("/").pop()} <b>#{r.pr_number}</b></span>
                    {r.status === "running" || r.status === "queued"
                      ? <span className={`pill pill-${r.status}`}>{STATUS_LABEL[r.status]}</span>
                      : r.verdict ? <VerdictBadge verdict={r.verdict} size="sm" /> : <span className="pill">{STATUS_LABEL[r.status]}</span>}
                  </span>
                  <span className="run-item-title">{r.title || "…"}</span>
                  <span className="run-item-meta">{relative(r.queued_at)}{r.total_ms ? ` · ${duration(r.total_ms)}` : ""}{r.demo ? " · démo" : ""}</span>
                </button>
              </li>
            ))}
          </ul>
          {!auto.current && (
            <button type="button" className="btn btn-ghost btn-sm btn-block" onClick={() => { auto.current = true; }}>
              Suivre automatiquement la prochaine analyse
            </button>
          )}
        </Panel>
      </aside>
      <div className="live-main">
        {follow ? (
          <RunMonitor view={view} live connected={connected} stored={detail?.findings} canRate
            header={<div className="player"><Link className="btn btn-sm btn-ghost" to={`/runs/${follow}`}>Ouvrir la page de l’analyse</Link></div>} />
        ) : (
          <Panel><Empty title="En attente d’une analyse">Ouvrez ou mettez à jour une PR, ou lancez la démo : l’analyse s’affichera ici en direct.</Empty></Panel>
        )}
      </div>
    </div>
  );
}
