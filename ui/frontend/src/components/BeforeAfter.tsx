import { useEffect, useState } from "react";
import { duration } from "../format";
import type { PreviewPage, PreviewSide, RunView } from "../runState";
import { Icon, Panel } from "./ui";

// Aperçu avant / après : l'application lancée sur la branche de base puis sur la PR,
// les mêmes pages photographiées des deux côtés. Information pour le relecteur :
// n'a aucun effet sur le verdict.

const img = (runId: string, idx: number, kind: string) => `/ui/api/runs/${runId}/previews/${idx}/${kind}.png`;

type Kind = "before" | "after" | "diff";
const KIND_LABEL: Record<Kind, string> = { before: "Avant (base)", after: "Après (PR)", diff: "Différences" };
interface Zoom { page: PreviewPage; kind: Kind }

function change(p: PreviewPage): { tone: string; text: string } {
  if (!p.after.image) return { tone: "bad", text: "non affichée avec la PR" };
  if ((p.after.status ?? 0) >= 500) return { tone: "bad", text: `erreur ${p.after.status} avec la PR` };
  if (!p.before.image || p.before.status === 404) return { tone: "new", text: "nouvelle page" };
  if (p.before.status !== p.after.status) return { tone: "changed", text: `HTTP ${p.before.status} → ${p.after.status}` };
  if (p.diff_pct === null || p.diff_pct === undefined) return { tone: "none", text: "—" };
  if (p.diff_pct === 0) return { tone: "same", text: "aucun changement visible" };
  return { tone: "changed", text: `${p.diff_pct.toLocaleString("fr-FR")} % de la page a changé` };
}

/** Deux pages comparables pixel par pixel : rendues des deux côtés, avec le même statut HTTP. */
const comparable = (p: PreviewPage) =>
  p.images.includes("diff") && p.before.image && p.after.image && p.before.status === p.after.status;

function kindsOf(p: PreviewPage): Kind[] {
  return (["before", "after", "diff"] as Kind[]).filter((k) => (k === "diff" ? comparable(p) : p[k].image));
}

/** Visionneuse dans la page : ✕, Échap ou clic à côté pour fermer ; ← → pour passer d'une vue à l'autre. */
function Lightbox({ runId, zoom, onChange, onClose }: { runId: string; zoom: Zoom; onChange: (z: Zoom) => void; onClose: () => void }) {
  const kinds = kindsOf(zoom.page);
  const at = kinds.indexOf(zoom.kind);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowRight" && at < kinds.length - 1) onChange({ ...zoom, kind: kinds[at + 1] });
      else if (e.key === "ArrowLeft" && at > 0) onChange({ ...zoom, kind: kinds[at - 1] });
    };
    window.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { window.removeEventListener("keydown", onKey); document.body.style.overflow = overflow; };
  }, [zoom, at, kinds, onChange, onClose]);

  return (
    <div className="lb" role="dialog" aria-modal="true" aria-label={`${KIND_LABEL[zoom.kind]} : ${zoom.page.path}`} onClick={onClose}>
      <div className="lb-bar" onClick={(e) => e.stopPropagation()}>
        <code className="ba-path">{zoom.page.path}</code>
        <div className="seg" role="tablist" aria-label="Vue">
          {kinds.map((k) => (
            <button key={k} type="button" role="tab" aria-selected={k === zoom.kind} className={k === zoom.kind ? "on" : ""}
              onClick={() => onChange({ ...zoom, kind: k })}>{KIND_LABEL[k]}</button>
          ))}
        </div>
        <span className="lb-spacer" />
        <a className="btn btn-ghost btn-sm" href={img(runId, zoom.page.idx, zoom.kind)} target="_blank" rel="noreferrer">
          <Icon name="external" size={14} /> Image seule
        </a>
        <button type="button" className="btn btn-ghost btn-sm lb-close" onClick={onClose} aria-label="Fermer" autoFocus>
          <Icon name="x" size={16} /> Fermer
        </button>
      </div>
      <div className="lb-body">
        <img src={img(runId, zoom.page.idx, zoom.kind)} alt={`${KIND_LABEL[zoom.kind]} : ${zoom.page.path}`}
          onClick={(e) => e.stopPropagation()} />
      </div>
      <p className="lb-hint">Échap ou clic à côté pour fermer · ← → pour changer de vue</p>
    </div>
  );
}

function Shot({ runId, page, kind, onZoom, note }: { runId: string; page: PreviewPage; kind: Kind; onZoom: (z: Zoom) => void; note?: string }) {
  const s: PreviewSide | null = kind === "diff" ? null : page[kind];
  const has = kind === "diff" ? comparable(page) : Boolean(s?.image);
  return (
    <figure className={`ba-shot ${kind === "diff" ? "ba-diff" : ""}`}>
      <figcaption>
        <span className={`ba-side ba-${kind === "before" ? "before" : "after"}`}>{KIND_LABEL[kind]}</span>
        {s?.status && <span className="muted">HTTP {s.status}</span>}
        {s?.final_path && s.final_path !== page.path && <span className="muted">→ {s.final_path}</span>}
        {note && <span className="muted">{note}</span>}
      </figcaption>
      {has ? (
        <button type="button" className="ba-zoom" onClick={() => onZoom({ page, kind })} title="Agrandir">
          <img src={img(runId, page.idx, kind)} alt={`${KIND_LABEL[kind]} : ${page.path}`} loading="lazy" />
        </button>
      ) : (
        <div className="ba-missing">
          <Icon name="minus" size={16} />
          <span>{kind === "before" ? "Page absente avant la PR" : "Page non affichée"}</span>
          {s?.error && <code>{s.error}</code>}
        </div>
      )}
    </figure>
  );
}

function PageCompare({ runId, page, onZoom }: { runId: string; page: PreviewPage; onZoom: (z: Zoom) => void }) {
  const [mode, setMode] = useState<"side" | "diff">("side");
  const c = change(page);
  const canDiff = comparable(page);
  return (
    <article className="ba-page">
      <header className="ba-head">
        <div>
          <code className="ba-path">{page.path}</code>
          <span className="muted ba-reason">{page.reason}</span>
        </div>
        <div className="ba-tools">
          <span className={`ba-change ba-${c.tone}`}>{c.text}</span>
          {canDiff && (
            <div className="seg" role="tablist" aria-label="Affichage">
              <button type="button" role="tab" aria-selected={mode === "side"} className={mode === "side" ? "on" : ""}
                onClick={() => setMode("side")}>Avant / après</button>
              <button type="button" role="tab" aria-selected={mode === "diff"} className={mode === "diff" ? "on" : ""}
                onClick={() => setMode("diff")}>Différences</button>
            </div>
          )}
        </div>
      </header>
      {page.change?.summary && (
        <div className="ba-what">
          <p><strong>Ce qui change :</strong> {page.change.summary}</p>
          {(page.change.text_added.length > 0 || page.change.text_removed.length > 0) && (
            <ul className="ba-text">
              {page.change.text_added.map((t, i) => <li key={`a${i}`} className="ba-add"><span>+</span>{t}</li>)}
              {page.change.text_removed.map((t, i) => <li key={`r${i}`} className="ba-del"><span>−</span>{t}</li>)}
            </ul>
          )}
        </div>
      )}
      {mode === "diff" && canDiff ? (
        <Shot runId={runId} page={page} kind="diff" onZoom={onZoom} note="zones encadrées en rouge : ce qui a changé" />
      ) : (
        <div className="ba-pair">
          <Shot runId={runId} page={page} kind="before" onZoom={onZoom} />
          <Shot runId={runId} page={page} kind="after" onZoom={onZoom} />
        </div>
      )}
      {!canDiff && page.before.image && page.after.image && (
        <p className="muted small-note ba-note">Pas de vue « Différences » : les deux pages ne sont pas comparables (statut HTTP différent).</p>
      )}
    </article>
  );
}

export function BeforeAfter({ view }: { view: RunView }) {
  const [zoom, setZoom] = useState<Zoom | null>(null);
  const p = view.preview;
  if (!p || p.status === "off") return null;
  const running = p.status === "running";
  return (
    <Panel title={`Avant / après${p.pages.length ? ` · ${p.pages.length} page(s) modifiée(s)` : ""}`}
      aside={<span className="muted small-note">Information : sans effet sur le verdict{p.durationMs ? ` · ${duration(p.durationMs)}` : ""}</span>}
      className="ba-panel">
      {running && !p.pages.length && (
        <p className="muted pad"><span className="spinner spinner-sm" /> Lancement de l’application avant et après la PR…
          {p.files?.length ? ` (${p.files.length} fichier(s) d’interface modifié(s))` : ""}</p>
      )}
      {(p.pages.length > 0 || (p.unchanged?.length ?? 0) > 0) && (
        <div className="notice ba-caveat">
          <Icon name="info" size={16} />
          <p><strong>Aide indicative, peut se tromper.</strong> L’agent n’ouvre que quelques pages, avec un compte de test
            et des données fictives ; la comparaison et les suggestions de l’IA peuvent être fausses ou incomplètes.
            Cela ne remplace pas un test à la main et ne change jamais le verdict.</p>
        </div>
      )}
      {!running && !p.pages.length && !(p.unchanged?.length) && (
        <p className="muted pad">Pas d’aperçu : {p.message || "non disponible"}.</p>
      )}
      {!running && !p.pages.length && (p.unchanged?.length ?? 0) > 0 && (
        <p className="pad">Aucun changement visible sur les pages ouvertes.</p>
      )}
      {p.status !== "running" && p.message && p.pages.length > 0 && <p className="muted pad small-note">{p.message}</p>}

      {(p.suggesting || (p.suggestions?.length ?? 0) > 0 || p.suggestError) && (
        <section className="ba-suggest">
          <h3>À vérifier à la main <span className="ba-ai">suggestions de l’IA · peuvent être fausses</span></h3>
          {p.suggesting && <p className="muted"><span className="spinner spinner-sm" /> L’IA lit les changements…</p>}
          {p.suggestError && !p.suggestions?.length && <p className="muted">{p.suggestError}.</p>}
          <ul>
            {(p.suggestions || []).map((s, i) => (
              <li key={i}>
                <span className="ba-box" aria-hidden="true" />
                <div><p>{s.check}{s.page && <code> {s.page}</code>}</p>{s.why && <p className="muted small-note">{s.why}</p>}</div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {p.pages.map((page) => <PageCompare key={page.idx} runId={view.runId} page={page} onZoom={setZoom} />)}
      {(p.unchanged?.length ?? 0) > 0 && (
        <p className="muted pad small-note ba-unchanged">
          Ouverte(s), rien de visible n’a changé (captures non montrées) : {p.unchanged!.map((u) => <code key={u.path}>{u.path}</code>)}
        </p>
      )}
      {zoom && <Lightbox runId={view.runId} zoom={zoom} onChange={setZoom} onClose={() => setZoom(null)} />}
    </Panel>
  );
}
