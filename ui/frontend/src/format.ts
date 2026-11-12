import type { Severity, Verdict } from "./types";

const nf1 = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 1 });
const nf0 = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 });
const pct = new Intl.NumberFormat("fr-FR", { style: "percent", maximumFractionDigits: 0 });

export function duration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || Number.isNaN(ms)) return "—";
  if (ms < 1000) return `${nf0.format(ms)} ms`;
  const s = ms / 1000;
  if (s < 60) return `${nf1.format(s)} s`;
  const m = Math.floor(s / 60);
  const rest = Math.round(s - m * 60);
  return rest ? `${m} min ${String(rest).padStart(2, "0")} s` : `${m} min`;
}

export const percent = (v: number | null | undefined) => (v === null || v === undefined ? "—" : pct.format(v));
export const integer = (v: number | null | undefined) => (v === null || v === undefined ? "—" : nf0.format(v));

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("fr-FR", {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

export function relative(iso: string | null | undefined): string {
  if (!iso) return "";
  const s = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "à l’instant";
  if (s < 3600) return `il y a ${Math.floor(s / 60)} min`;
  if (s < 86400) return `il y a ${Math.floor(s / 3600)} h`;
  return `il y a ${Math.floor(s / 86400)} j`;
}

export const cost = (usd: number | null | undefined) =>
  usd ? `${new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 4 }).format(usd)} $` : "0 $ · modèle interne";

export const VERDICT_LABEL: Record<Verdict, string> = {
  BLOQUANTE: "Bloquante",
  A_VERIFIER: "À vérifier",
  CONTROLES_SATISFAITS: "Contrôles satisfaits",
  ANALYSE_INCOMPLETE: "Analyse incomplète",
};

export const VERDICT_HINT: Record<Verdict, string> = {
  BLOQUANTE: "Une détection déterministe (secret) empêche la fusion.",
  A_VERIFIER: "Des remarques demandent une relecture humaine. Avis consultatif.",
  CONTROLES_SATISFAITS: "Tout le diff a été relu, rien de notable n’a été trouvé.",
  ANALYSE_INCOMPLETE: "Une partie de la PR n’a pas été relue : jamais présentée comme réussie.",
};

export type Tone = "critical" | "warning" | "good" | "serious";

export const VERDICT_TONE: Record<Verdict, Tone> = {
  BLOQUANTE: "critical",
  A_VERIFIER: "warning",
  CONTROLES_SATISFAITS: "good",
  ANALYSE_INCOMPLETE: "serious",
};

export const VERDICT_ORDER: Verdict[] = ["BLOQUANTE", "ANALYSE_INCOMPLETE", "A_VERIFIER", "CONTROLES_SATISFAITS"];

export const SEVERITY_LABEL: Record<Severity, string> = {
  critical: "Critique", major: "Majeur", minor: "Mineur", info: "Info",
};
export const SEVERITY_ORDER: Severity[] = ["critical", "major", "minor", "info"];

export const STATUS_LABEL: Record<string, string> = {
  queued: "En file", running: "En cours", ok: "Terminée", stale: "Obsolète",
  superseded: "Remplacée", error: "En échec",
};

export const NODE_LABEL: Record<string, string> = {
  fetch_pr: "Lecture PR",
  load_diff: "Diff filtré",
  scan_secrets: "Secrets",
  ai_review: "Revue IA",
  static_checks: "Contrôles",
  decide: "Verdict",
  publish: "Publication",
  alert: "Alerte",
  audit: "Journal",
  fail: "Échec",
};

export const NODE_HINT: Record<string, string> = {
  fetch_pr: "PR lue sur GitHub, commit vérifié",
  load_diff: "fichiers filtrés, limites appliquées",
  scan_secrets: "secrets masqués avant le modèle",
  ai_review: "lots analysés en parallèle",
  static_checks: "outils + CI, en parallèle",
  decide: "règles déterministes versionnées",
  publish: "commit revérifié, revue COMMENT",
  alert: "email si bloquante",
  audit: "trace JSONL",
  fail: "statut « action requise »",
};

export const SKIP_REASON: Record<string, string> = {
  kill_switch: "publication suspendue",
  dry_run: "mode lecture seule",
};

export const SOURCE_LABEL: Record<string, string> = {
  llm: "IA · avis",
  "secret-scan": "Détection de secrets",
  gitleaks: "gitleaks",
  "composer-audit": "composer audit",
  phpstan: "PHPStan",
  "php-cs-fixer": "PHP-CS-Fixer",
  ci: "CI du dépôt",
};

/** Sources déterministes (ne dépendent pas d'un modèle) : peuvent bloquer en mode pilote. */
export const DETERMINISTIC = new Set(["secret-scan", "gitleaks", "composer-audit", "phpstan", "php-cs-fixer", "ci"]);

export const CHECK_LABEL: Record<string, string> = {
  checker: "Conteneur de contrôle",
  gitleaks: "gitleaks · secrets",
  "composer-audit": "composer audit · dépendances",
  phpstan: "PHPStan · analyse statique",
  "php-cs-fixer": "PHP-CS-Fixer · style",
  ci: "CI du dépôt · tests",
};

export const CHECK_STATUS: Record<string, { label: string; tone: string }> = {
  running: { label: "en cours", tone: "info" },
  pending: { label: "CI en cours", tone: "info" },
  ok: { label: "rien à signaler", tone: "good" },
  findings: { label: "remarques", tone: "warning" },
  failed: { label: "en échec", tone: "critical" },
  skipped: { label: "non applicable", tone: "muted" },
  error: { label: "en erreur", tone: "serious" },
  timeout: { label: "délai dépassé", tone: "serious" },
};

export const shortSha = (sha: string | null | undefined) => (sha ? sha.slice(0, 7) : "");
