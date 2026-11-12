import { NODE_HINT, NODE_LABEL, SKIP_REASON, VERDICT_LABEL, VERDICT_TONE, duration } from "../format";
import type { ChunkView, NodeView, RunView } from "../runState";

// Graphe LangGraph de l'agent : les nœuds s'allument à l'exécution, la revue IA
// se déploie en lots parallèles qui convergent vers le verdict.

const W = 112;
const H = 60;
const FAN_X = 594;
const FAN_W = 176;
const X: Record<string, number> = {
  fetch_pr: 18, load_diff: 158, scan_secrets: 298, ai_review: 438,
  decide: 806, publish: 946, alert: 1086, audit: 1226,
};
const ORDER = ["fetch_pr", "load_diff", "scan_secrets", "ai_review", "decide", "publish", "alert", "audit"];
const VIEW_W = X.audit + W + 18;

function nodeClass(n: NodeView | undefined) {
  return `g-node g-${n?.status || "idle"}`;
}

function sub(name: string, n: NodeView | undefined, now: number): string {
  if (!n || n.status === "idle") return NODE_HINT[name];
  if (n.status === "running") return `en cours · ${duration((now - (n.started || now)) * 1000)}`;
  if (n.status === "skipped") return "non exécuté";
  if (n.status === "error") return `erreur · ${duration(n.duration)}`;
  if (name === "fetch_pr" && n.status === "stale") return "commit obsolète";
  return duration(n.duration);
}

function Chunk({ c, x, y, compact, now }: { c: ChunkView; x: number; y: number; compact: boolean; now: number }) {
  if (compact) {
    return (
      <g className={`g-chunk g-chunk-${c.status}`} transform={`translate(${x},${y})`}>
        <title>{`Lot ${c.index} — ${c.files.join(", ")}`}</title>
        <rect width={18} height={18} rx={5} />
      </g>
    );
  }
  const right =
    c.status === "running" ? duration((now - (c.started || now)) * 1000)
      : c.status === "failed" ? "échec"
        : c.status === "done" ? `${c.findings ?? 0} rem. · ${duration(c.duration)}`
          : "en attente";
  const label = c.files.length === 1 ? c.files[0].split("/").pop() : `${c.files.length} fichiers`;
  return (
    <g className={`g-chunk g-chunk-${c.status}`} transform={`translate(${x},${y})`}>
      <title>{`Lot ${c.index} — ${c.files.join(", ")} (${c.chars} caractères)`}</title>
      <rect width={FAN_W} height={24} rx={12} />
      {c.status === "running" && <rect className="g-chunk-sweep" width={FAN_W} height={24} rx={12} />}
      <text x={12} y={16} className="g-chunk-index">{String(c.index).padStart(2, "0")}</text>
      <text x={34} y={16} className="g-chunk-label">{label}</text>
      <text x={FAN_W - 12} y={16} textAnchor="end" className="g-chunk-meta">{right}</text>
    </g>
  );
}

export function PipelineGraph({ view, now }: { view: RunView; now: number }) {
  const chunks = view.chunks;
  const compact = chunks.length > 8;
  const cols = compact ? Math.ceil(chunks.length / 6) : 1;
  const rows = compact ? Math.min(6, chunks.length) : chunks.length;
  const fanH = compact ? rows * 24 : chunks.length * 32;
  const failing = Boolean(view.failNode);
  const height = Math.max(220, fanH + 90) + (failing ? 70 : 0);
  const cy = failing ? (height - 70) / 2 : height / 2;
  const top = cy - fanH / 2;

  const chunkPos = (i: number) => compact
    ? { x: FAN_X + 14 + Math.floor(i / 6) * ((FAN_W - 28) / Math.max(cols, 1)), y: top + (i % 6) * 24 }
    : { x: FAN_X, y: top + i * 32 };

  const edge = (a: string, b: string) => {
    const from = view.nodes[a];
    const to = view.nodes[b];
    const active = to?.status === "running";
    const done = to && to.status !== "idle" && to.status !== "skipped";
    return `g-edge ${active ? "g-edge-active" : done ? "g-edge-done" : ""} ${from?.status === "skipped" ? "g-edge-off" : ""}`;
  };

  const secrets = view.findings.filter((f) => f.source === "secret-scan").length;
  const llmFindings = view.findings.filter((f) => f.source === "llm").length;
  const skippedPublish = view.publishSkips.find((s) => s.step !== "alerte email");

  return (
    <div className="graph-wrap">
      <svg className="graph" viewBox={`0 0 ${VIEW_W} ${height}`} role="img"
        aria-label="Graphe d'exécution de l'analyse">
        <defs>
          <linearGradient id="sweep" x1="0" x2="1">
            <stop offset="0" stopColor="var(--accent)" stopOpacity="0" />
            <stop offset="0.5" stopColor="var(--accent)" stopOpacity="0.35" />
            <stop offset="1" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* arêtes linéaires */}
        {ORDER.slice(0, 3).map((name, i) => (
          <path key={name} className={edge(name, ORDER[i + 1])}
            d={`M${X[name] + W} ${cy} L${X[ORDER[i + 1]]} ${cy}`} />
        ))}
        {ORDER.slice(4, 7).map((name, i) => (
          <path key={name} className={edge(name, ORDER[i + 5])}
            d={`M${X[name] + W} ${cy} L${X[ORDER[i + 5]]} ${cy}`} />
        ))}

        {/* éventail des lots */}
        {chunks.length === 0 ? (
          <path className={edge("ai_review", "decide")} d={`M${X.ai_review + W} ${cy} L${X.decide} ${cy}`} />
        ) : chunks.map((c, i) => {
          const p = chunkPos(i);
          const ey = p.y + (compact ? 9 : 12);
          const sx = X.ai_review + W;
          const live = c.status === "running" ? "g-edge-active" : c.status !== "queued" ? "g-edge-done" : "";
          const out = c.status === "done" || c.status === "failed" ? (c.status === "failed" ? "g-edge-failed" : "g-edge-done") : "";
          return (
            <g key={c.index}>
              <path className={`g-edge ${live}`}
                d={`M${sx} ${cy} C${sx + 30} ${cy}, ${p.x - 30} ${ey}, ${p.x} ${ey}`} />
              {!compact && (
                <path className={`g-edge ${out}`}
                  d={`M${p.x + FAN_W} ${ey} C${p.x + FAN_W + 22} ${ey}, ${X.decide - 22} ${cy}, ${X.decide} ${cy}`} />
              )}
            </g>
          );
        })}
        {compact && chunks.length > 0 && (
          <path className={`g-edge ${view.nodes.decide ? "g-edge-done" : ""}`}
            d={`M${FAN_X + FAN_W} ${cy} L${X.decide} ${cy}`} />
        )}
        {chunks.map((c, i) => {
          const p = chunkPos(i);
          return <Chunk key={c.index} c={c} x={p.x} y={p.y} compact={compact} now={now} />;
        })}
        {chunks.length > 0 && (
          <text x={FAN_X + FAN_W / 2} y={top - 12} textAnchor="middle" className="g-fan-label">
            {`${chunks.length} lot${chunks.length > 1 ? "s" : ""} · ${view.concurrency ?? "?"} en parallèle`}
          </text>
        )}

        {/* commit obsolète : saut direct vers le journal */}
        {view.stale && (
          <g>
            <path className="g-edge g-edge-stale" d={`M${X.fetch_pr + W / 2} ${cy - H / 2} C${X.fetch_pr + 200} ${cy - H / 2 - 70}, ${X.audit - 200} ${cy - H / 2 - 70}, ${X.audit + W / 2} ${cy - H / 2}`} />
            <text x={(X.fetch_pr + X.audit + W) / 2} y={cy - H / 2 - 50} textAnchor="middle" className="g-fan-label">
              commit obsolète : rien n’est analysé ni publié
            </text>
          </g>
        )}

        {/* échec */}
        {failing && view.failNode && (
          <g>
            <path className="g-edge g-edge-failed"
              d={`M${X[view.failNode] + W / 2} ${cy + H / 2} C${X[view.failNode] + W / 2} ${height - 30}, ${X.decide - 40} ${height - 34}, ${X.decide} ${height - 34}`} />
            <g className="g-node g-error" transform={`translate(${X.decide},${height - 62})`}>
              <rect width={W} height={56} rx={14} />
              <text x={14} y={24} className="g-label">Échec</text>
              <text x={14} y={42} className="g-sub">action requise</text>
            </g>
          </g>
        )}

        {/* nœuds */}
        {ORDER.map((name, i) => {
          const n = view.nodes[name];
          const isDecide = name === "decide" && view.verdict;
          return (
            <g key={name} className={`${nodeClass(n)} ${isDecide ? `g-verdict tone-${VERDICT_TONE[view.verdict!]}` : ""}`}
              transform={`translate(${X[name]},${cy - H / 2})`}>
              <title>{`${NODE_LABEL[name]} — ${NODE_HINT[name]}`}</title>
              {n?.status === "running" && <rect className="g-halo" x={-5} y={-5} width={W + 10} height={H + 10} rx={18} />}
              <rect className="g-box" width={W} height={H} rx={14} />
              <text x={14} y={20} className="g-index">{String(i + 1).padStart(2, "0")}</text>
              <text x={14} y={38} className="g-label">{isDecide ? VERDICT_LABEL[view.verdict!] : NODE_LABEL[name]}</text>
              <text x={14} y={52} className="g-sub">{sub(name, n, now)}</text>
              {name === "scan_secrets" && secrets > 0 && (
                <g className="g-badge g-badge-critical" transform={`translate(${W - 10},-8)`}>
                  <circle r={11} /><text textAnchor="middle" y={4}>{secrets}</text>
                </g>
              )}
              {name === "ai_review" && llmFindings > 0 && (
                <g className="g-badge" transform={`translate(${W - 10},-8)`}>
                  <circle r={11} /><text textAnchor="middle" y={4}>{llmFindings}</text>
                </g>
              )}
              {name === "publish" && skippedPublish && (
                <g className="g-tag" transform={`translate(0,${H + 8})`}>
                  <rect width={W} height={20} rx={10} />
                  <text x={W / 2} y={14} textAnchor="middle">{SKIP_REASON[skippedPublish.reason] || skippedPublish.reason}</text>
                </g>
              )}
              {name === "publish" && view.superseded && (
                <g className="g-tag" transform={`translate(0,${H + 8})`}>
                  <rect width={W} height={20} rx={10} />
                  <text x={W / 2} y={14} textAnchor="middle">commit plus récent</text>
                </g>
              )}
              {name === "publish" && view.published && (
                <g className="g-tag g-tag-ok" transform={`translate(0,${H + 8})`}>
                  <rect width={W} height={20} rx={10} />
                  <text x={W / 2} y={14} textAnchor="middle">{view.published.github_state}</text>
                </g>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

