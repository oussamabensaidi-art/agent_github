import type { ReactNode } from "react";
import { SEVERITY_LABEL, VERDICT_LABEL, VERDICT_TONE, type Tone } from "../format";
import type { Severity, Verdict } from "../types";

const PATHS: Record<string, string> = {
  check: "M4 10.5l4 4L16 6",
  x: "M5 5l10 10M15 5L5 15",
  alert: "M10 3l8 14H2L10 3zM10 8v4M10 14.5v.5",
  info: "M10 18a8 8 0 100-16 8 8 0 000 16zM10 9v5M10 6v.5",
  half: "M10 18a8 8 0 100-16 8 8 0 000 16zM10 2v16",
  play: "M6 4l10 6-10 6V4z",
  pause: "M6 4h3v12H6zM11 4h3v12h-3z",
  restart: "M4 10a6 6 0 106-6H7M7 1L4 4l3 3",
  end: "M5 4l8 6-8 6V4zM15 4v12",
  power: "M10 2v7M5.6 5.2a6.5 6.5 0 108.8 0",
  bolt: "M11 2L4 11h5l-1 7 7-9h-5l1-7z",
  pr: "M6 4.5a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0zM6 15.5a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0zM17 15.5a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0zM4.5 6v8M15.5 14V8a2 2 0 00-2-2H10M12 4l-2 2 2 2",
  clock: "M10 18a8 8 0 100-16 8 8 0 000 16zM10 5v5l3 2",
  shield: "M10 2l7 3v5c0 4-3 7-7 8-4-1-7-4-7-8V5l7-3z",
  logout: "M8 4H4v12h4M13 6l4 4-4 4M17 10H8",
  flask: "M8 2h4M9 2v5L4 16a1.5 1.5 0 001.3 2h9.4a1.5 1.5 0 001.3-2L11 7V2",
  thumbUp: "M6 9l3-6a2 2 0 012 2v3h4.5a1.5 1.5 0 011.5 1.7l-1 6A1.5 1.5 0 0114.5 17H6V9zM3 9h3v8H3z",
  thumbDown: "M14 11l-3 6a2 2 0 01-2-2v-3H4.5A1.5 1.5 0 013 10.3l1-6A1.5 1.5 0 015.5 3H14v8zM17 11h-3V3h3z",
  external: "M11 3h6v6M17 3l-8 8M14 12v4H4V6h4",
  eye: "M1.5 10S5 4 10 4s8.5 6 8.5 6-3.5 6-8.5 6-8.5-6-8.5-6zM10 12.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5z",
};

export function Icon({ name, size = 16, className = "" }: { name: keyof typeof PATHS | string; size?: number; className?: string }) {
  return (
    <svg className={`icon ${className}`} width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor"
      strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={PATHS[name] || PATHS.info} />
    </svg>
  );
}

const TONE_ICON: Record<Tone, string> = { critical: "x", warning: "alert", good: "check", serious: "half" };

export function VerdictBadge({ verdict, size = "md" }: { verdict: Verdict | null | undefined; size?: "sm" | "md" | "lg" }) {
  if (!verdict) return <span className={`verdict verdict-${size} verdict-none`}>—</span>;
  const tone = VERDICT_TONE[verdict];
  return (
    <span className={`verdict verdict-${size} tone-${tone}`}>
      <span className="verdict-icon"><Icon name={TONE_ICON[tone]} size={size === "lg" ? 18 : 13} /></span>
      {VERDICT_LABEL[verdict]}
    </span>
  );
}

const SEV_TONE: Record<Severity, string> = { critical: "critical", major: "serious", minor: "warning", info: "muted" };

export function SeverityChip({ severity }: { severity: Severity }) {
  return (
    <span className={`sev sev-${SEV_TONE[severity]}`}>
      <span className="sev-dot" />
      {SEVERITY_LABEL[severity] || severity}
    </span>
  );
}

export function Panel({ title, aside, children, className = "" }: { title?: ReactNode; aside?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`panel ${className}`}>
      {(title || aside) && (
        <header className="panel-head">
          {title && <h2>{title}</h2>}
          {aside && <div className="panel-aside">{aside}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: ReactNode; tone?: string }) {
  return (
    <div className={`stat ${tone ? `stat-${tone}` : ""}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <div className="empty-mark" aria-hidden="true">
        <span /><span /><span />
      </div>
      <strong>{title}</strong>
      {children && <p>{children}</p>}
    </div>
  );
}
