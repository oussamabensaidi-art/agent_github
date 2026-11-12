import { useEffect, useMemo, useRef, useState } from "react";
import { api, query } from "../api";
import { Empty, Icon, Panel, Stat } from "../components/ui";
import { VERDICT_LABEL, VERDICT_ORDER, VERDICT_TONE, duration, integer, percent } from "../format";
import type { Stats } from "../types";
import { Filters } from "./HistoryPage";

const TARGET_MS = 10 * 60 * 1000;
const TONE_ICON: Record<string, string> = { critical: "x", warning: "alert", good: "check", serious: "half" };

function VerdictBar({ verdicts }: { verdicts: Stats["verdicts"] }) {
  const total = VERDICT_ORDER.reduce((s, v) => s + (verdicts[v] || 0), 0);
  const [hover, setHover] = useState<string | null>(null);
  if (!total) return <p className="muted pad">Aucune analyse terminée sur la période.</p>;
  return (
    <div className="vbar-wrap">
      <div className="vbar" role="img" aria-label="Répartition des verdicts">
        {VERDICT_ORDER.filter((v) => verdicts[v]).map((v) => (
          <span key={v} className={`vbar-seg tone-${VERDICT_TONE[v]} ${hover && hover !== v ? "dim" : ""}`}
            style={{ flexGrow: verdicts[v] }} onMouseEnter={() => setHover(v)} onMouseLeave={() => setHover(null)}
            title={`${VERDICT_LABEL[v]} : ${verdicts[v]} (${percent((verdicts[v] || 0) / total)})`} />
        ))}
      </div>
      <ul className="legend">
        {VERDICT_ORDER.map((v) => (
          <li key={v} className={hover && hover !== v ? "dim" : ""} onMouseEnter={() => setHover(v)} onMouseLeave={() => setHover(null)}>
            <span className={`legend-key tone-${VERDICT_TONE[v]}`}><Icon name={TONE_ICON[VERDICT_TONE[v]]} size={11} /></span>
            <span className="legend-label">{VERDICT_LABEL[v]}</span>
            <span className="legend-value">{integer(verdicts[v] || 0)}</span>
            <span className="legend-share">{percent((verdicts[v] || 0) / total)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function niceStep(max: number) {
  const steps = [1000, 2000, 5000, 10000, 15000, 30000, 60000, 120000, 300000, 600000];
  return steps.find((s) => max / s <= 12) || 600000;
}

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(640);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(320, Math.round(e.contentRect.width))));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

// Graphique dimensionné à la largeur réelle du panneau : le texte garde sa taille.
function DurationHistogram({ values, p50, p95 }: { values: number[]; p50: number | null; p95: number | null }) {
  const [hover, setHover] = useState<number | null>(null);
  const [box, W] = useWidth<HTMLDivElement>();
  const bins = useMemo(() => {
    if (!values.length) return { step: 1000, counts: [] as number[] };
    const max = Math.max(...values, p95 || 0);
    const step = niceStep(max);
    const counts = new Array(Math.max(1, Math.ceil((max + 1) / step))).fill(0);
    for (const v of values) counts[Math.min(counts.length - 1, Math.floor(v / step))] += 1;
    return { step, counts };
  }, [values, p95]);
  if (!values.length) return <div ref={box}><p className="muted pad">Pas encore de durée mesurée.</p></div>;

  const H = 240, PL = 34, PB = 28, PT = 30;
  const flip = (x: number) => x > W - 130;
  const plotW = W - PL - 8, plotH = H - PB - PT;
  const top = Math.max(...bins.counts);
  const bw = plotW / bins.counts.length;
  const xOf = (ms: number) => PL + (ms / (bins.step * bins.counts.length)) * plotW;
  const yTicks = Array.from(new Set([0, Math.ceil(top / 2), top]));
  return (
    <div className="hist" ref={box}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Distribution des durées totales (attente comprise)">
        {yTicks.map((t) => {
          const y = PT + plotH - (t / top) * plotH;
          return (
            <g key={t}>
              <line x1={PL} x2={W - 8} y1={y} y2={y} className="grid" />
              <text x={PL - 8} y={y + 4} textAnchor="end" className="axis-text">{t}</text>
            </g>
          );
        })}
        {bins.counts.map((c, i) => {
          const h = (c / top) * plotH;
          const x = PL + i * bw + 1;
          return (
            <g key={i} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <rect x={PL + i * bw} y={PT} width={bw} height={plotH} fill="transparent" />
              {c > 0 && (
                <path className={`hist-bar ${hover !== null && hover !== i ? "dim" : ""}`}
                  d={`M${x} ${PT + plotH} V${PT + plotH - h + 4} q0 -4 4 -4 h${Math.max(bw - 10, 1)} q4 0 4 4 V${PT + plotH} Z`} />
              )}
            </g>
          );
        })}
        <line x1={PL} x2={W - 8} y1={PT + plotH} y2={PT + plotH} className="baseline" />
        {[0, 0.5, 1].map((t) => (
          <text key={t} x={PL + t * plotW} y={H - 8} textAnchor={t === 0 ? "start" : t === 1 ? "end" : "middle"} className="axis-text">
            {duration(t * bins.step * bins.counts.length)}
          </text>
        ))}
        {p50 !== null && (
          <g className="marker"><line x1={xOf(p50)} x2={xOf(p50)} y1={PT - 6} y2={PT + plotH} />
            <text x={xOf(p50) + (flip(xOf(p50)) ? -6 : 4)} y={PT - 12} textAnchor={flip(xOf(p50)) ? "end" : "start"}
              className="marker-text">p50 {duration(p50)}</text></g>
        )}
        {p95 !== null && (
          <g className="marker marker-strong"><line x1={xOf(p95)} x2={xOf(p95)} y1={PT - 6} y2={PT + plotH} />
            <text x={xOf(p95) + (flip(xOf(p95)) ? -6 : 4)} y={PT + 8} textAnchor={flip(xOf(p95)) ? "end" : "start"}
              className="marker-text">p95 {duration(p95)}</text></g>
        )}
        {hover !== null && (
          <g className="tip" transform={`translate(${Math.min(PL + hover * bw + bw / 2, W - 120)}, ${PT + 4})`}>
            <rect x={-4} y={-2} width={124} height={38} rx={6} />
            <text x={6} y={14}>{duration(hover * bins.step)} – {duration((hover + 1) * bins.step)}</text>
            <text x={6} y={29} className="tip-strong">{bins.counts[hover]} analyse(s)</text>
          </g>
        )}
      </svg>
      <p className="muted small">
        Durée totale = file d’attente + exécution. Objectif du cahier des charges : p95 sous {duration(TARGET_MS)}
        {p95 !== null && <> — <strong className={p95 <= TARGET_MS ? "ok-text" : "bad-text"}>{p95 <= TARGET_MS ? "atteint" : "dépassé"}</strong></>}.
      </p>
    </div>
  );
}

function Relevance({ fb, target }: { fb: Stats["feedback"]; target: number }) {
  const rate = fb.relevance_rate;
  return (
    <div className="relevance">
      <div className="relevance-num">
        <strong>{percent(rate)}</strong>
        <span>de remarques jugées pertinentes</span>
      </div>
      <div className="meter" role="img" aria-label={`Pertinence ${percent(rate)}, objectif ${percent(target)}`}>
        <span className="meter-fill" style={{ width: `${(rate ?? 0) * 100}%` }} />
        <span className="meter-target" style={{ left: `${target * 100}%` }}><em>objectif {percent(target)}</em></span>
      </div>
      <dl className="facts facts-row">
        <dt>Pertinentes</dt><dd>{fb.pertinente}</dd>
        <dt>Fausses alertes</dt><dd>{fb.fausse_alerte}</dd>
        <dt>Sans avis</dt><dd>{Math.max(fb.findings_kept - fb.rated, 0)}</dd>
      </dl>
      {fb.rated < 30 && <p className="muted small">Échantillon de {fb.rated} avis : indicatif tant qu’il reste sous 30.</p>}
    </div>
  );
}

export function StatsPage() {
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [stats, setStats] = useState<Stats | null>(null);
  const [repos, setRepos] = useState<string[]>([]);
  useEffect(() => { api<string[]>("/repos").then(setRepos).catch(() => {}); }, []);
  useEffect(() => {
    const { verdict: _ignored, ...rest } = filters;
    api<Stats>(`/stats${query(rest)}`).then(setStats);
  }, [filters]);

  return (
    <div className="page">
      <div className="page-head">
        <h1>Statistiques</h1>
        <p className="muted">Mesures de pilotage du cahier des charges : délai, fiabilité, pertinence.</p>
      </div>
      <Filters repos={repos} value={filters} onChange={setFilters} verdict={false} />
      {!stats ? <p className="muted pad">Chargement…</p> : stats.runs === 0 ? (
        <Panel><Empty title="Aucune analyse sur la période">Lancez la démo ou attendez les premières PR.</Empty></Panel>
      ) : (
        <>
          <div className="stats-grid">
            <Stat label="Analyses" value={integer(stats.runs)} sub={`${stats.errors} en échec · ${stats.superseded} obsolètes ou remplacées`} />
            <Stat label="Durée totale p50" value={duration(stats.p50_total_ms)} sub="attente comprise" />
            <Stat label="Durée totale p95" value={duration(stats.p95_total_ms)}
              tone={stats.p95_total_ms !== null ? (stats.p95_total_ms <= TARGET_MS ? "good" : "critical") : undefined}
              sub={`objectif < ${duration(TARGET_MS)}`} />
            <Stat label="File d’attente p95" value={duration(stats.p95_queue_ms)} sub={`p50 ${duration(stats.p50_queue_ms)}`} />
            <Stat label="Lots en échec" value={percent(stats.chunk_failure_rate)} sub={`${stats.chunks_failed} sur ${stats.chunks_total} lots`} />
            <Stat label="File d’échecs (DLQ)" value={stats.dlq_size === null ? "—" : integer(stats.dlq_size)}
              tone={stats.dlq_size ? "warning" : undefined} sub="jobs à reprendre" />
          </div>
          <div className="stats-cols">
            <Panel title="Verdicts"><VerdictBar verdicts={stats.verdicts} /></Panel>
            <Panel title="Pertinence des remarques"><Relevance fb={stats.feedback} target={stats.relevance_target} /></Panel>
          </div>
          <Panel title="Durée totale des analyses" aside={<span className="muted">{stats.durations_ms.length} analyse(s)</span>}>
            <DurationHistogram values={stats.durations_ms} p50={stats.p50_total_ms} p95={stats.p95_total_ms} />
          </Panel>
        </>
      )}
    </div>
  );
}
