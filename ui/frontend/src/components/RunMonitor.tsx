import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  SEVERITY_ORDER, SKIP_REASON, STATUS_LABEL, VERDICT_HINT, cost, duration, shortSha,
} from "../format";
import type { FindingView, RunView } from "../runState";
import type { Finding, Rating } from "../types";
import { FindingCard } from "./FindingCard";
import { PipelineGraph } from "./PipelineGraph";
import { Timeline } from "./Timeline";
import { Icon, Panel, VerdictBadge } from "./ui";

function useNow(active: boolean) {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    if (!active) return;
    const t = window.setInterval(() => setNow(Date.now() / 1000), 200);
    return () => window.clearInterval(t);
  }, [active]);
  return now;
}

interface Props {
  view: RunView;
  live: boolean;
  connected?: boolean;
  /** Remarques enregistrées (avec les avis) : présentes une fois l'analyse terminée. */
  stored?: Finding[];
  canRate?: boolean;
  replayClock?: number;
  header?: ReactNode;
}

export function RunMonitor({ view, live, connected, stored, canRate = false, replayClock, header }: Props) {
  const running = view.status === "queued" || view.status === "running";
  const ticking = useNow(live && running);
  const now = replayClock ?? (running ? ticking : view.finishedAt ?? ticking);
  const [ratings, setRatings] = useState<Record<string, Rating | null>>({});
  const [showDropped, setShowDropped] = useState(false);

  // Fusion : ordre et état du flux, avis de la base.
  const findings: FindingView[] = useMemo(() => {
    const byId = new Map((stored || []).map((f) => [f.id, f]));
    return view.findings.map((f) => {
      const s = byId.get(f.id);
      return { ...f, rating: f.id in ratings ? ratings[f.id] : s?.rating ?? null };
    });
  }, [view.findings, stored, ratings]);

  const kept = findings.filter((f) => f.state !== "dropped");
  const dropped = findings.filter((f) => f.state === "dropped");
  const grouped = SEVERITY_ORDER.map((sev) => ({ sev, items: kept.filter((f) => f.severity === sev) }))
    .filter((g) => g.items.length);
  const incomplete = view.skipped.filter((s) => s.incomplete);
  const excluded = view.skipped.filter((s) => !s.incomplete);
  const rateable = canRate && !running && Boolean(stored);
  const runningMs = view.startedAt ? ((view.finishedAt ?? now) - view.startedAt) * 1000 : null;

  return (
    <div className="monitor">
      <div className="run-hero">
        <div className="run-hero-main">
          <div className="run-kicker">
            <Icon name="pr" size={15} />
            <span>{view.repo ?? "…"}</span>
            <span className="run-pr">#{view.pr ?? "…"}</span>
            <code>{shortSha(view.sha)}</code>
            {view.demo && <span className="tag tag-demo">démo · GitHub simulé</span>}
            {live && running && (
              <span className={`live-dot ${connected ? "on" : ""}`}>{connected ? "en direct" : "connexion…"}</span>
            )}
          </div>
          <h1 className="run-title">{view.title || (view.status === "queued" ? "Analyse en file d’attente"
            : view.status === "stale" ? "Commit obsolète : rien n’a été analysé"
              : view.status === "error" ? "Analyse interrompue" : "Lecture de la PR…")}</h1>
          <div className="run-meta">
            {view.author && <span>par <strong>{view.author}</strong></span>}
            <span>{STATUS_LABEL[view.status]}</span>
            {view.model && <span>modèle <code>{view.model}</code></span>}
            {view.rulesVersion && <span>règles <code>{view.rulesVersion}</code></span>}
            {view.pilot !== undefined && <span>{view.pilot ? "mode pilote · IA consultative" : "IA bloquante"}</span>}
          </div>
          {header}
        </div>
        <div className={`run-verdict ${view.verdict ? "" : "run-verdict-wait"}`}>
          {view.verdict ? (
            <>
              <VerdictBadge verdict={view.verdict} size="lg" />
              <p>{VERDICT_HINT[view.verdict]}</p>
            </>
          ) : view.status === "error" ? (
            <><span className="verdict verdict-lg tone-critical"><Icon name="alert" size={18} /> Analyse en échec</span>
              <p>{view.error || "Erreur non détaillée."}</p></>
          ) : view.status === "stale" ? (
            <><span className="verdict verdict-lg verdict-none">Commit obsolète</span><p>Un commit plus récent sera analysé à la place.</p></>
          ) : (
            <><span className="verdict verdict-lg verdict-none verdict-pending"><span className="spinner" /> Verdict en attente</span>
              <p>Le verdict est calculé par des règles fixes, une fois toutes les remarques connues.</p></>
          )}
        </div>
      </div>

      <div className="kpis">
        <div className="kpi"><span>File d’attente</span><strong>{duration(view.queueMs ?? (view.queuedAt && !view.startedAt ? (now - view.queuedAt) * 1000 : null))}</strong></div>
        <div className="kpi"><span>Exécution</span><strong>{duration(view.runMs ?? runningMs)}</strong></div>
        <div className="kpi kpi-strong"><span>Total (attente comprise)</span><strong>{duration(view.totalMs ?? (view.queuedAt ? ((view.finishedAt ?? now) - view.queuedAt) * 1000 : null))}</strong></div>
        <div className="kpi"><span>Lots</span><strong>{view.chunks.length ? `${view.chunks.filter((c) => c.status === "done").length}/${view.chunks.length}` : "—"}</strong>
          {view.chunks.some((c) => c.status === "failed") && <em>{view.chunks.filter((c) => c.status === "failed").length} en échec</em>}</div>
        <div className="kpi"><span>Remarques retenues</span><strong>{view.verdict ? kept.length : findings.length ? `${findings.length} reçues` : "0"}</strong></div>
        <div className="kpi"><span>Coût</span><strong>{cost(view.costUsd)}</strong></div>
      </div>

      {(view.publishSkips.length > 0 || view.superseded) && (
        <div className="notice notice-warn">
          <Icon name="power" size={16} />
          {view.superseded
            ? "Un commit plus récent est arrivé pendant l’analyse : rien n’a été publié sur la PR, le check de ce commit est clos « remplacé »."
            : `Rien n’a été écrit vers GitHub ni envoyé par email (${SKIP_REASON[view.publishSkips[0].reason] || view.publishSkips[0].reason}) : ${view.publishSkips.map((s) => s.step).join(", ")}.`}
        </div>
      )}

      <Panel title="Exécution" aside={<span className="muted">graphe LangGraph · lots en parallèle</span>} className="panel-graph">
        <PipelineGraph view={view} now={now} />
        <Timeline view={view} now={now} />
      </Panel>

      <div className="run-grid">
        <Panel title={`Remarques${kept.length ? ` · ${kept.length}` : ""}`}
          aside={dropped.length > 0 && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setShowDropped((v) => !v)}>
              <Icon name="eye" size={14} /> {showDropped ? "Masquer" : "Voir"} les {dropped.length} écartée{dropped.length > 1 ? "s" : ""}
            </button>
          )}>
          {findings.length === 0 && (
            <p className="muted pad">{running ? "Les remarques apparaissent ici dès qu’un lot est analysé." : "Aucune remarque."}</p>
          )}
          {!view.verdict && findings.length > 0 && (
            <div className="feed">
              {[...findings].reverse().map((f) => (
                <FindingCard key={f.id} finding={f} runId={view.runId} canRate={false} pilot={view.pilot} animate />
              ))}
            </div>
          )}
          {view.verdict && grouped.map((g) => (
            <div key={g.sev} className="sev-group">
              {g.items.map((f) => (
                <FindingCard key={f.id} finding={f} runId={view.runId} canRate={rateable} pilot={view.pilot}
                  onRated={(id, r) => setRatings((m) => ({ ...m, [id]: r }))} />
              ))}
            </div>
          ))}
          {view.verdict && showDropped && (
            <div className="dropped-list">
              <h3 className="sub-title">Écartées par la validation (anti-hallucination, seuil, doublons)</h3>
              {dropped.map((f) => <FindingCard key={f.id} finding={f} runId={view.runId} canRate={false} pilot={view.pilot} />)}
            </div>
          )}
          {view.verdict && !rateable && kept.length > 0 && canRate && (
            <p className="muted pad">Les avis seront possibles à la fin de l’analyse.</p>
          )}
        </Panel>

        <div className="side-col">
          <Panel title="Couverture du diff">
            <ul className="files">
              {view.files.map((f) => (
                <li key={f.path}><span className="file-dot file-ok" /><code>{f.path}</code>
                  <span className="file-diff"><b>+{f.additions}</b> <i>−{f.deletions}</i></span></li>
              ))}
              {incomplete.map((f) => (
                <li key={f.path} className="file-warn"><span className="file-dot file-incomplete" /><code>{f.path}</code>
                  <span className="file-reason">{f.reason}</span></li>
              ))}
              {excluded.map((f) => (
                <li key={f.path} className="file-off"><span className="file-dot" /><code>{f.path}</code>
                  <span className="file-reason">{f.reason}</span></li>
              ))}
              {!view.files.length && !view.skipped.length && <li className="muted">En attente du diff…</li>}
            </ul>
            {view.incompleteReasons.length > 0 && (
              <div className="notice notice-serious">
                <Icon name="half" size={16} />
                <div>
                  <strong>Non relu :</strong>
                  <ul>{view.incompleteReasons.map((r) => <li key={r}>{r.replace(/`/g, "")}</li>)}</ul>
                </div>
              </div>
            )}
          </Panel>
          <Panel title="Publication">
            <dl className="facts">
              <dt>GitHub</dt>
              <dd>{view.published ? `${view.published.mode} « ${view.published.github_state} », ${view.published.inline} commentaire(s) en ligne`
                : view.superseded ? "non publiée (commit remplacé)"
                  : view.publishSkips.length ? "aucune écriture (interrupteur ou lecture seule)"
                    : running ? "en attente" : "—"}</dd>
              <dt>Alerte email</dt>
              <dd>{view.alert === "sent" ? "envoyée" : view.verdict === "BLOQUANTE" ? (view.alert === "skipped" ? "non envoyée" : "—") : "non requise"}</dd>
              <dt>Fusion</dt>
              <dd>jamais par l’agent · décision humaine</dd>
            </dl>
          </Panel>
        </div>
      </div>
    </div>
  );
}
