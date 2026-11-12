import { useState } from "react";
import { api, jsonBody } from "../api";
import { SOURCE_LABEL } from "../format";
import type { Finding, Rating } from "../types";
import { Icon, SeverityChip } from "./ui";

export function Excerpt({ lines }: { lines: Finding["excerpt"] }) {
  if (!lines?.length) return null;
  return (
    <pre className="excerpt" aria-label="Lignes du diff concernées">
      {lines.map((l, i) => (
        <div key={i} className={`ex-line ex-${l.kind === "+" ? "add" : l.kind === "-" ? "del" : "ctx"} ${l.target ? "ex-target" : ""}`}>
          <span className="ex-n">{l.n ?? ""}</span>
          <span className="ex-k">{l.kind === " " ? "" : l.kind}</span>
          <code>{l.text || " "}</code>
        </div>
      ))}
    </pre>
  );
}

interface Props {
  finding: Finding & { state?: "raw" | "kept" | "dropped" };
  runId: string;
  canRate: boolean;
  pilot?: boolean;
  onRated?: (id: string, rating: Rating | null) => void;
  animate?: boolean;
}

export function FindingCard({ finding: f, runId, canRate, pilot = true, onRated, animate }: Props) {
  const [rating, setRating] = useState<Rating | null>(f.rating ?? null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const dropped = f.state === "dropped" || f.kept === false;
  const pending = f.state === "raw";

  async function rate(r: Rating) {
    setBusy(true);
    setError("");
    try {
      if (rating === r) {
        await api(`/runs/${runId}/findings/${f.id}/feedback`, { method: "DELETE" });
        setRating(null);
        onRated?.(f.id, null);
      } else {
        await api(`/runs/${runId}/findings/${f.id}/feedback`, { method: "PUT", body: jsonBody({ rating: r }) });
        setRating(r);
        onRated?.(f.id, r);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "échec");
    } finally {
      setBusy(false);
    }
  }

  const advisory = pilot && f.source === "llm" && f.severity === "critical";
  return (
    <article className={`finding ${dropped ? "finding-dropped" : ""} ${pending ? "finding-pending" : ""} ${animate ? "finding-in" : ""}`}>
      <header className="finding-head">
        <SeverityChip severity={f.severity} />
        {advisory && <span className="tag tag-soft" title="Mode pilote : l'IA ne peut pas bloquer seule">avis IA</span>}
        <span className={`tag ${f.source === "secret-scan" ? "tag-det" : ""}`}>{SOURCE_LABEL[f.source] || f.source}</span>
        <span className="tag tag-ghost">{f.category}</span>
        <code className="finding-where">{f.path}{f.line ? `:${f.line}` : ""}</code>
      </header>
      <h3 className="finding-title">{f.title}</h3>
      {dropped && <p className="finding-drop"><Icon name="x" size={13} /> Écartée : {f.drop_reason || "non retenue"}</p>}
      {f.explanation && <p className="finding-text">{f.explanation}</p>}
      {f.suggestion && <p className="finding-suggestion"><strong>Suggestion</strong> {f.suggestion}</p>}
      <Excerpt lines={f.excerpt} />
      {canRate && !dropped && (
        <footer className="finding-foot">
          <span className="finding-ask">Cette remarque est-elle utile ?</span>
          <div className="seg" role="group" aria-label="Avis sur la remarque">
            <button type="button" disabled={busy} className={rating === "pertinente" ? "on on-good" : ""}
              aria-pressed={rating === "pertinente"} onClick={() => rate("pertinente")}>
              <Icon name="thumbUp" size={14} /> Pertinente
            </button>
            <button type="button" disabled={busy} className={rating === "fausse_alerte" ? "on on-bad" : ""}
              aria-pressed={rating === "fausse_alerte"} onClick={() => rate("fausse_alerte")}>
              <Icon name="thumbDown" size={14} /> Fausse alerte
            </button>
          </div>
          {error && <span className="form-error">{error}</span>}
        </footer>
      )}
    </article>
  );
}
