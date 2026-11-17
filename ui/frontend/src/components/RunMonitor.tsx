import { useEffect, useMemo, useState, type ReactNode } from "react";
import { SEVERITY_LABEL, SEVERITY_ORDER, SKIP_REASON, STATUS_LABEL, cost, duration, shortSha } from "../format";
import type { FindingView, RunView } from "../runState";
import type { Finding, Rating } from "../types";
import { BeforeAfter } from "./BeforeAfter";
import { Checklist } from "./Checklist";
import { FindingCard } from "./FindingCard";
import { PipelineGraph } from "./PipelineGraph";
import { Timeline } from "./Timeline";
import { Icon, Panel, VerdictBadge } from "./ui";

// Page d'une analyse, dans l'ordre où on la lit :
//   1. le verdict et sa raison, en une phrase ;
//   2. ce qu'il faut regarder (les remarques, les plus graves d'abord) ;
//   3. ce qui a été vérifié (une liste de contrôles) ;
//   4. les détails techniques, repliés (graphe, chronologie, durées, modèle).

function useNow(active: boolean) {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    if (!active) return;
    const t = window.setInterval(() => setNow(Date.now() / 1000), 250);
    return () => window.clearInterval(t);
  }, [active]);
  return now;
}

/** La raison du verdict, en clair. */
function why(view: RunView, kept: FindingView[]): string {
  const det = kept.filter((f) => f.severity === "critical" && f.source !== "llm");
  switch (view.verdict) {
    case "BLOQUANTE":
      return det.length
        ? `${det[0].title}${det.length > 1 ? ` (+${det.length - 1} autre(s))` : ""}. À corriger avant la fusion.`
        : "Une remarque critique bloque la fusion.";
    case "ANALYSE_INCOMPLETE":
      return `Une partie n’a pas été vérifiée : ${(view.incompleteReasons[0] || "voir la liste des contrôles").replace(/`/g, "")}.`
        + " Une personne doit relire cette PR.";
    case "A_VERIFIER": {
      const n = kept.filter((f) => f.severity === "critical" || f.severity === "major").length;
      return `${n} remarque(s) à relire. Ce sont des avis : la décision reste humaine.`;
    }
    case "CONTROLES_SATISFAITS":
      return kept.length
        ? `Rien de bloquant ; ${kept.length} remarque(s) mineure(s) pour information.`
        : "Tout a été relu et vérifié : rien à signaler.";
    default:
      return "";
  }
}

interface Props {
  view: RunView;
  live: boolean;
  connected?: boolean;
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
  const [showTech, setShowTech] = useState(false);

  const findings: FindingView[] = useMemo(() => {
    const byId = new Map((stored || []).map((f) => [f.id, f]));
    return view.findings.map((f) => {
      const s = byId.get(f.id);
      return { ...f, rating: f.id in ratings ? ratings[f.id] : s?.rating ?? null };
    });
  }, [view.findings, stored, ratings]);

  const kept = findings.filter((f) => f.state !== "dropped");
  const dropped = findings.filter((f) => f.state === "dropped");
  const groups = SEVERITY_ORDER.map((sev) => ({ sev, items: kept.filter((f) => f.severity === sev) })).filter((g) => g.items.length);
  const rateable = canRate && !running && Boolean(stored);
  const runningMs = view.startedAt ? ((view.finishedAt ?? now) - view.startedAt) * 1000 : null;
  const totalMs = view.totalMs ?? (view.queuedAt ? ((view.finishedAt ?? now) - view.queuedAt) * 1000 : null);

  const title = view.title || (view.status === "queued" ? "Analyse en file d’attente"
    : view.status === "stale" ? "Commit obsolète : rien n’a été analysé"
      : view.status === "error" ? "Analyse interrompue" : "Lecture de la PR…");

  return (
    <div className="monitor">
      {/* 1. Verdict et raison */}
      <section className={`summary ${view.verdict ? `summary-${view.verdict}` : running ? "summary-running" : "summary-other"}`}>
        <div className="summary-main">
          <div className="run-kicker">
            <Icon name="pr" size={14} />
            <span>{view.repo ?? "…"}</span>
            <span className="run-pr">#{view.pr ?? "…"}</span>
            {view.author && <span className="muted">par {view.author}</span>}
            {view.demo && <span className="tag tag-demo">démo</span>}
            {live && running && <span className={`live-dot ${connected ? "on" : ""}`}>{connected ? "en direct" : "connexion…"}</span>}
          </div>
          <h1 className="run-title">{title}</h1>
          <div className="summary-verdict">
            {view.verdict ? <VerdictBadge verdict={view.verdict} size="lg" />
              : view.status === "error" ? <span className="verdict verdict-lg tone-critical"><Icon name="alert" size={18} /> Analyse en échec</span>
                : view.status === "stale" ? <span className="verdict verdict-lg verdict-none">Commit obsolète</span>
                  : <span className="verdict verdict-lg verdict-none verdict-pending"><span className="spinner" /> {view.status === "queued" ? "En file d’attente" : "Analyse en cours"}</span>}
            <p className="summary-why">
              {view.verdict ? why(view, kept)
                : view.status === "error" ? (view.error || "Erreur non détaillée.") + " Une personne doit relire cette PR."
                  : view.status === "stale" ? "Un commit plus récent sera analysé à la place."
                    : `Commencée il y a ${duration(runningMs ?? 0)} · les remarques apparaissent au fil de l’eau.`}
            </p>
          </div>
          {(view.superseded || view.publishSkips.length > 0) && (
            <p className="summary-note"><Icon name="power" size={14} />
              {view.superseded ? "Un commit plus récent est arrivé pendant l’analyse : rien n’a été publié pour celle-ci."
                : `Rien n’a été écrit sur GitHub ni envoyé (${SKIP_REASON[view.publishSkips[0].reason] || view.publishSkips[0].reason}).`}
            </p>
          )}
          {header}
        </div>
        <dl className="summary-facts">
          <div><dt>Durée</dt><dd>{duration(totalMs)}</dd></div>
          <div><dt>Remarques</dt><dd>{view.verdict ? kept.length : findings.length}</dd></div>
          <div><dt>Commit</dt><dd><code>{shortSha(view.sha)}</code></dd></div>
        </dl>
      </section>

      <div className="run-grid">
        {/* 2. Ce qu'il faut regarder */}
        <Panel title={`À regarder${kept.length ? ` · ${kept.length}` : ""}`}
          aside={view.verdict && kept.length > 0 && (
            <span className="sev-counts">
              {groups.map((g) => <span key={g.sev} className={`sev-count sev-${g.sev}`}>{g.items.length} {SEVERITY_LABEL[g.sev].toLowerCase()}</span>)}
            </span>
          )}>
          {findings.length === 0 && (
            <p className="muted pad">{running ? "Les remarques apparaissent ici dès qu’un passage de relecture se termine." : "Aucune remarque : rien à regarder."}</p>
          )}
          {!view.verdict && findings.length > 0 && (
            <div className="feed">
              {[...findings].reverse().map((f) => (
                <FindingCard key={f.id} finding={f} runId={view.runId} canRate={false} pilot={view.pilot} animate />
              ))}
            </div>
          )}
          {view.verdict && groups.map((g) => (
            <div key={g.sev} className="sev-group">
              {g.items.map((f) => (
                <FindingCard key={f.id} finding={f} runId={view.runId} canRate={rateable} pilot={view.pilot}
                  onRated={(id, r) => setRatings((m) => ({ ...m, [id]: r }))} />
              ))}
            </div>
          ))}
          {view.verdict && rateable && kept.length > 0 && (
            <p className="muted pad small-note">Notez chaque remarque (« Pertinente » ou « Fausse alerte ») : c’est ce qui mesure la qualité de l’agent.</p>
          )}
          {view.verdict && dropped.length > 0 && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setShowDropped((v) => !v)}>
              <Icon name="eye" size={14} /> {showDropped ? "Masquer" : "Voir"} {dropped.length} remarque(s) écartée(s) automatiquement
            </button>
          )}
          {showDropped && (
            <div className="dropped-list">
              <h3 className="sub-title">Écartées par la validation (inventées, trop faibles ou en double)</h3>
              {dropped.map((f) => <FindingCard key={f.id} finding={f} runId={view.runId} canRate={false} pilot={view.pilot} />)}
            </div>
          )}
        </Panel>

        {/* 3. Ce qui a été vérifié */}
        <div className="side-col">
          <Panel title="Ce qui a été vérifié">
            <Checklist view={view} kept={view.verdict ? kept : findings} />
            {view.incompleteReasons.length > 0 && (
              <div className="notice notice-serious">
                <Icon name="half" size={16} />
                <div><strong>Non vérifié :</strong>
                  <ul>{view.incompleteReasons.map((r) => <li key={r}>{r.replace(/`/g, "")}</li>)}</ul></div>
              </div>
            )}
          </Panel>
          <Panel title="Fichiers de la PR">
            <ul className="files">
              {view.files.map((f) => (
                <li key={f.path}><span className="file-dot file-ok" /><code>{f.path}</code>
                  <span className="file-diff"><b>+{f.additions}</b> <i>−{f.deletions}</i></span></li>
              ))}
              {view.skipped.map((f) => (
                <li key={f.path} className={f.incomplete ? "file-warn" : "file-off"}>
                  <span className={`file-dot ${f.incomplete ? "file-incomplete" : ""}`} /><code>{f.path}</code>
                  <span className="file-reason">{f.reason}</span></li>
              ))}
              {!view.files.length && !view.skipped.length && <li className="muted">En attente du diff…</li>}
            </ul>
          </Panel>
        </div>
      </div>

      {/* 3 bis. Aperçu avant / après (seulement si la PR touche l'interface) */}
      <BeforeAfter view={view} />

      {/* 4. Détails techniques */}
      <section className="tech">
        <button type="button" className="tech-toggle" aria-expanded={showTech} onClick={() => setShowTech((v) => !v)}>
          <Icon name={showTech ? "minus" : "plus"} size={14} />
          Détails techniques
          <span className="muted">graphe d’exécution, chronologie, durées, modèle</span>
        </button>
        {showTech && (
          <div className="tech-body">
            <div className="kpis">
              <div className="kpi"><span>File d’attente</span><strong>{duration(view.queueMs ?? (view.queuedAt && !view.startedAt ? (now - view.queuedAt) * 1000 : null))}</strong></div>
              <div className="kpi"><span>Exécution</span><strong>{duration(view.runMs ?? runningMs)}</strong></div>
              <div className="kpi"><span>Passages IA</span><strong>{view.chunks.length ? `${view.chunks.filter((c) => c.status === "done").length}/${view.chunks.length}` : "—"}</strong></div>
              <div className="kpi"><span>Coût</span><strong>{cost(view.costUsd)}</strong></div>
            </div>
            <dl className="facts tech-facts">
              <dt>Statut</dt><dd>{STATUS_LABEL[view.status]}</dd>
              {view.model && <><dt>Modèle</dt><dd><code>{view.model}</code></dd></>}
              {view.rulesVersion && <><dt>Règles</dt><dd><code>{view.rulesVersion}</code></dd></>}
              {view.pilot !== undefined && <><dt>Mode</dt><dd>{view.pilot ? "pilote : l’IA donne des avis, seuls les contrôles automatiques bloquent" : "l’IA peut bloquer"}</dd></>}
              <dt>Fusion</dt><dd>jamais par l’agent : décision humaine</dd>
            </dl>
            <PipelineGraph view={view} now={now} />
            <Timeline view={view} now={now} />
          </div>
        )}
      </section>
    </div>
  );
}
