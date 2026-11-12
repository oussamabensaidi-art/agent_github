import { NODE_LABEL, duration } from "../format";
import { PIPELINE, type RunView } from "../runState";

// Chronologie : file d'attente puis chaque nœud, avec les lots de la revue IA
// sur leurs propres lignes — le parallélisme se lit d'un coup d'œil.

interface Row { key: string; label: string; start?: number; end?: number; tone: string; indent?: boolean; note?: string }

export function Timeline({ view, now }: { view: RunView; now: number }) {
  const origin = view.queuedAt ?? view.startedAt;
  if (!origin) return null;
  const end = view.finishedAt ?? now;
  const span = Math.max(end - origin, 0.001);

  const rows: Row[] = [];
  if (view.queuedAt !== undefined) {
    rows.push({ key: "queue", label: "File d’attente", start: view.queuedAt, end: view.startedAt ?? now,
                tone: "queue", note: duration(((view.startedAt ?? now) - view.queuedAt) * 1000) });
  }
  for (const name of PIPELINE) {
    const n = view.nodes[name];
    if (!n || n.status === "skipped") continue;
    rows.push({ key: name, label: NODE_LABEL[name], start: n.started, end: n.finished ?? now,
                tone: n.status, note: n.duration !== undefined ? duration(n.duration) : "…" });
    if (name === "ai_review") {
      for (const c of view.chunks) {
        rows.push({ key: `chunk-${c.index}`, label: `Lot ${String(c.index).padStart(2, "0")}`, start: c.started,
                    end: c.finished ?? (c.started ? now : undefined), tone: `chunk-${c.status}`, indent: true,
                    note: c.duration !== undefined ? duration(c.duration) : c.status === "queued" ? "en attente" : "…" });
      }
    }
  }
  if (view.failNode && view.nodes.fail) {
    const f = view.nodes.fail;
    rows.push({ key: "fail", label: "Échec", start: f.started, end: f.finished ?? now, tone: "error", note: duration(f.duration) });
  }

  const ticks = [0, 0.25, 0.5, 0.75, 1];
  return (
    <div className="timeline" role="table" aria-label="Chronologie de l'analyse">
      <div className="tl-axis" aria-hidden="true">
        <span className="tl-axis-label" />
        <div className="tl-axis-track">
          {ticks.map((t) => (
            <span key={t} className="tl-tick" style={{ left: `${t * 100}%` }}>{duration(t * span * 1000)}</span>
          ))}
        </div>
        <span className="tl-note" />
      </div>
      {rows.map((r) => {
        const left = r.start !== undefined ? ((r.start - origin) / span) * 100 : 0;
        const width = r.start !== undefined && r.end !== undefined ? Math.max(((r.end - r.start) / span) * 100, 0.6) : 0;
        return (
          <div key={r.key} className={`tl-row ${r.indent ? "tl-indent" : ""}`} role="row">
            <span className="tl-label" role="cell">{r.label}</span>
            <div className="tl-track" role="cell">
              {ticks.slice(1, 4).map((t) => <span key={t} className="tl-grid" style={{ left: `${t * 100}%` }} />)}
              {r.start !== undefined && (
                <span className={`tl-bar tl-${r.tone}`} style={{ left: `${left}%`, width: `${width}%` }}
                  title={`${r.label} : ${r.note}`} />
              )}
            </div>
            <span className="tl-note" role="cell">{r.note}</span>
          </div>
        );
      })}
    </div>
  );
}
