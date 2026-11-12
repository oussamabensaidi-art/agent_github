import { useEffect, useState } from "react";
import { api, query } from "../api";
import { Empty, Icon, Panel, VerdictBadge } from "../components/ui";
import { STATUS_LABEL, VERDICT_LABEL, VERDICT_ORDER, dateTime, duration, shortSha } from "../format";
import { Link, navigate } from "../router";
import type { RunRow } from "../types";

const PAGE = 25;

export function Filters({ repos, value, onChange, verdict = true }: {
  repos: string[];
  value: Record<string, string>;
  onChange: (v: Record<string, string>) => void;
  verdict?: boolean;
}) {
  const set = (k: string) => (e: { target: { value: string } }) => onChange({ ...value, [k]: e.target.value });
  return (
    <div className="filters">
      <label>Dépôt
        <select value={value.repo || ""} onChange={set("repo")}>
          <option value="">Tous</option>
          {repos.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
      </label>
      {verdict && (
        <label>Verdict
          <select value={value.verdict || ""} onChange={set("verdict")}>
            <option value="">Tous</option>
            {VERDICT_ORDER.map((v) => <option key={v} value={v}>{VERDICT_LABEL[v]}</option>)}
          </select>
        </label>
      )}
      <label>Du
        <input type="date" value={value.date_from || ""} onChange={set("date_from")} />
      </label>
      <label>Au
        <input type="date" value={value.date_to || ""} onChange={set("date_to")} />
      </label>
      <label>Origine
        <select value={value.demo || ""} onChange={set("demo")}>
          <option value="">Toutes</option>
          <option value="false">Hors démo</option>
          <option value="true">Démo uniquement</option>
        </select>
      </label>
      {Object.values(value).some(Boolean) && (
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => onChange({})}>Réinitialiser</button>
      )}
    </div>
  );
}

export function HistoryPage() {
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<{ total: number; runs: RunRow[] } | null>(null);
  const [repos, setRepos] = useState<string[]>([]);

  useEffect(() => { api<string[]>("/repos").then(setRepos).catch(() => {}); }, []);
  useEffect(() => {
    api<{ total: number; runs: RunRow[] }>(`/runs${query({ ...filters, limit: PAGE, offset })}`).then(setData);
  }, [filters, offset]);

  return (
    <div className="page">
      <div className="page-head">
        <h1>Historique</h1>
        <p className="muted">Chaque analyse est conservée événement par événement et peut être rejouée.</p>
      </div>
      <Filters repos={repos} value={filters} onChange={(v) => { setOffset(0); setFilters(v); }} />
      <Panel>
        {data && data.runs.length === 0 ? <Empty title="Aucune analyse ne correspond à ces filtres" /> : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Date</th><th>PR</th><th>Titre</th><th>Verdict</th><th className="num">Remarques</th>
                  <th className="num">Attente</th><th className="num">Total</th><th>Modèle</th><th />
                </tr>
              </thead>
              <tbody>
                {data?.runs.map((r) => (
                  <tr key={r.id} onClick={() => navigate(`/runs/${r.id}`)} className="row-link">
                    <td className="nowrap">{dateTime(r.queued_at)}</td>
                    <td className="nowrap"><span className="muted">{r.repo}</span> <b>#{r.pr_number}</b> <code className="muted">{shortSha(r.head_sha)}</code></td>
                    <td className="cell-title">{r.title || "—"}{r.demo && <span className="tag tag-demo">démo</span>}</td>
                    <td>{r.verdict && r.status === "ok" ? <VerdictBadge verdict={r.verdict} size="sm" /> : <span className="pill">{STATUS_LABEL[r.status]}</span>}</td>
                    <td className="num">{r.findings_count ?? "—"}</td>
                    <td className="num">{duration(r.queue_ms)}</td>
                    <td className="num"><b>{duration(r.total_ms)}</b></td>
                    <td><code className="muted">{r.model || "—"}</code></td>
                    <td className="nowrap" onClick={(e) => e.stopPropagation()}>
                      <Link className="btn btn-sm btn-ghost" to={`/runs/${r.id}?rejouer=1`}><Icon name="play" size={13} /> Rejouer</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && data.total > PAGE && (
          <div className="pager">
            <button type="button" className="btn btn-sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Précédent</button>
            <span className="muted">{offset + 1}–{Math.min(offset + PAGE, data.total)} sur {data.total}</span>
            <button type="button" className="btn btn-sm" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>Suivant</button>
          </div>
        )}
      </Panel>
    </div>
  );
}
