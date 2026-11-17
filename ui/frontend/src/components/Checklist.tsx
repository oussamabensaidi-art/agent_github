import { CHECK_LABEL, CHECK_STATUS, SKIP_REASON, duration } from "../format";
import type { FindingView, RunView } from "../runState";
import { Icon } from "./ui";

// « Ce qui a été vérifié » : une ligne par contrôle, avec un état simple.
// ok = rien trouvé · warn = remarques à relire · bad = bloquant · off = non applicable / non fait · run = en cours

type State = "ok" | "warn" | "bad" | "off" | "run" | "partial";

interface Row { key: string; label: string; state: State; detail: string }

const ICON: Record<State, string> = { ok: "check", warn: "alert", bad: "x", off: "minus", run: "clock", partial: "half" };

function countBy(findings: FindingView[], pred: (f: FindingView) => boolean) {
  return findings.filter(pred).length;
}

function reviewerRows(view: RunView, kept: FindingView[], running: boolean): Row[] {
  const names = Array.from(new Set(view.chunks.map((c) => c.reviewer || "")));
  const labels: Record<string, string> = { securite: "IA · sécurité", code: "IA · code & Symfony", "": "IA · relecture" };
  if (!names.length) {
    const st: State = view.nodes.ai_review?.status === "running" || running ? "run" : "off";
    return [{ key: "ai", label: "IA · relecture", state: st, detail: st === "run" ? "en cours" : "non lancée" }];
  }
  return names.map((name) => {
    const chunks = view.chunks.filter((c) => (c.reviewer || "") === name);
    const failed = chunks.filter((c) => c.status === "failed").length;
    const done = chunks.filter((c) => c.status === "done").length;
    const n = countBy(kept, (f) => f.source === "llm" && (f.reviewer || "") === name);
    const crit = countBy(kept, (f) => f.source === "llm" && (f.reviewer || "") === name && f.severity === "critical");
    let state: State = "ok";
    let detail = "rien à signaler";
    if (done + failed < chunks.length) { state = "run"; detail = `${done}/${chunks.length} passage(s)`; }
    else if (failed) { state = "partial"; detail = `${failed} passage(s) en échec : partie non relue`; }
    else if (n) { state = "warn"; detail = `${n} remarque(s)${crit ? `, dont ${crit} critique(s)` : ""} (avis)`; }
    return { key: `ai-${name}`, label: labels[name] || `IA · ${name}`, state, detail };
  });
}

export function Checklist({ view, kept }: { view: RunView; kept: FindingView[] }) {
  const running = view.status === "queued" || view.status === "running";
  const rows: Row[] = [];

  // Fichiers relus
  const incomplete = view.skipped.filter((s) => s.incomplete);
  const read = view.files.length;
  rows.push(!read && !view.skipped.length
    ? { key: "files", label: "Fichiers relus", state: running ? "run" : "off", detail: running ? "lecture du diff…" : "—" }
    : {
      key: "files", label: "Fichiers relus", state: incomplete.length ? "partial" : "ok",
      detail: `${read} fichier(s)${incomplete.length ? `, ${incomplete.length} non relu(s)` : ""}`
        + `${view.skipped.length - incomplete.length ? `, ${view.skipped.length - incomplete.length} exclu(s) (lock, généré)` : ""}`,
    });

  // Secrets (détection intégrée)
  const secrets = countBy(kept.length ? kept : view.findings, (f) => f.source === "secret-scan");
  const scanned = view.nodes.scan_secrets?.status === "ok";
  rows.push({
    key: "secrets", label: "Secrets", state: secrets ? "bad" : scanned ? "ok" : running ? "run" : "off",
    detail: secrets ? `${secrets} secret(s) trouvé(s) — bloquant` : scanned ? "aucun secret" : "—",
  });

  rows.push(...reviewerRows(view, kept, running));

  // Contrôles déterministes (conteneur + CI)
  for (const c of view.checks.filter((x) => x.name !== "checker" || x.status === "error")) {
    const st = c.status;
    const state: State = st === "ok" ? "ok" : st === "skipped" ? "off" : st === "findings"
      ? (countBy(kept, (f) => f.source === c.name && f.severity === "critical") ? "bad" : "warn")
      : st === "failed" ? "bad" : st === "running" || st === "pending" ? "run" : "partial";
    const label = (CHECK_LABEL[c.name] || c.name).replace(" · ", " · ");
    const detail = st === "findings" ? `${c.count} remarque(s)` : (c.message || CHECK_STATUS[st]?.label || st);
    rows.push({ key: c.name, label, state, detail: detail + (c.durationMs && state !== "run" ? ` · ${duration(c.durationMs)}` : "") });
  }

  // Aperçu avant / après (information, sans effet sur le verdict)
  const pv = view.preview;
  if (pv && pv.status !== "off") {
    const broken = pv.pages.filter((p) => !p.after.image || (p.after.status ?? 0) >= 500).length;
    const changed = pv.pages.filter((p) => (p.diff_pct ?? 0) > 0 || !p.before.image).length;
    rows.push(pv.status === "running"
      ? { key: "preview", label: "Avant / après", state: "run", detail: "captures en cours" }
      : pv.status === "ok"
        ? { key: "preview", label: "Avant / après", state: broken ? "warn" : "ok",
            detail: `${pv.pages.length} page(s), ${changed} modifiée(s)${broken ? `, ${broken} en erreur` : ""}` }
        : { key: "preview", label: "Avant / après", state: pv.status === "error" ? "partial" : "off",
            detail: pv.message || (pv.status === "error" ? "indisponible" : "non concerné") });
  }

  // Publication et alerte
  const skip = view.publishSkips.find((s) => s.step !== "alerte email");
  rows.push(view.published
    ? { key: "gh", label: "Publié sur GitHub", state: "ok",
        detail: `check « ${view.published.github_state} »${view.published.inline ? `, ${view.published.inline} commentaire(s) en ligne` : ""}` }
    : view.superseded ? { key: "gh", label: "Publié sur GitHub", state: "off", detail: "non : un commit plus récent est arrivé" }
      : skip ? { key: "gh", label: "Publié sur GitHub", state: "off", detail: `non : ${SKIP_REASON[skip.reason] || skip.reason}` }
        : { key: "gh", label: "Publié sur GitHub", state: running ? "run" : "off", detail: running ? "en attente du verdict" : "—" });
  if (view.verdict === "BLOQUANTE" || view.alert) {
    rows.push({ key: "mail", label: "Alerte email", state: view.alert === "sent" ? "ok" : "off",
      detail: view.alert === "sent" ? "envoyée à l’équipe" : "non envoyée" });
  }

  return (
    <ul className="checklist">
      {rows.map((r) => (
        <li key={r.key} className={`cl-${r.state}`}>
          <span className="cl-icon" aria-hidden="true">
            {r.state === "run" ? <span className="spinner spinner-sm" /> : <Icon name={ICON[r.state]} size={13} />}
          </span>
          <span className="cl-label">{r.label}</span>
          <span className="cl-detail">{r.detail}</span>
        </li>
      ))}
    </ul>
  );
}
