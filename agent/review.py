"""Remarques, validation anti-hallucination, verdict et rendu Markdown."""
from dataclasses import asdict, dataclass

SEVERITIES = ["info", "minor", "major", "critical"]
SEVERITY_LABEL = {"critical": "BLOQUANT", "major": "MAJEUR", "minor": "MINEUR", "info": "INFO"}

VERDICT_BLOCKING = "BLOQUANTE"
VERDICT_CHECK = "A_VERIFIER"
VERDICT_READY = "PRETE"

VERDICT_TEXT = {
    VERDICT_BLOCKING: "🔴 PR bloquante",
    VERDICT_CHECK: "🟠 À vérifier",
    VERDICT_READY: "🟢 Prête à fusionner (côté revue automatique)",
}

MARKER = "<!-- calipso-pr-review -->"


@dataclass
class Finding:
    path: str
    line: int | None
    severity: str
    category: str
    title: str
    explanation: str = ""
    suggestion: str = ""
    source: str = "llm"
    inline: bool = True  # False : la ligne n'est pas dans le diff → résumé seulement

    def to_dict(self) -> dict:
        return asdict(self)


def rank(severity: str) -> int:
    return SEVERITIES.index(severity) if severity in SEVERITIES else 0


def finding_from_llm(raw: dict) -> Finding | None:
    try:
        line = raw.get("line")
        return Finding(
            path=str(raw["path"]).strip().lstrip("/"),
            line=int(line) if line not in (None, "", 0) else None,
            severity=str(raw.get("severity", "info")).lower().strip(),
            category=str(raw.get("category", "quality")).lower().strip(),
            title=str(raw.get("title", "")).strip()[:200],
            explanation=str(raw.get("explanation", "")).strip()[:2000],
            suggestion=str(raw.get("suggestion", "")).strip()[:2000],
        )
    except (KeyError, TypeError, ValueError):
        return None


def validate_findings(
    findings: list[Finding],
    commentable: dict[str, set[int]],
    min_severity: str,
) -> list[Finding]:
    """Écarte les remarques inventées, sous le seuil, ou en double.

    - fichier absent du diff analysé → écartée (hallucination) ;
    - ligne hors du diff → gardée, mais dans le résumé (pas inline) ;
    - gravité sous MIN_COMMENT_SEVERITY → écartée (anti faux positifs).
    Les remarques du scanner de secrets passent toujours.
    """
    out: list[Finding] = []
    seen: set[tuple] = set()
    for f in findings:
        if f.severity not in SEVERITIES or not f.title:
            continue
        if f.source == "llm" and rank(f.severity) < rank(min_severity):
            continue
        if f.path not in commentable:
            continue
        f.inline = f.line is not None and f.line in commentable[f.path]
        key = (f.path, f.line, f.title.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    out.sort(key=lambda f: (-rank(f.severity), f.path, f.line or 0))
    return out


def compute_verdict(findings: list[Finding], incomplete_reasons: list[str]) -> str:
    if any(f.severity == "critical" for f in findings):
        return VERDICT_BLOCKING
    if any(f.severity == "major" for f in findings) or incomplete_reasons:
        return VERDICT_CHECK
    return VERDICT_READY


def _neutralize(text: str) -> str:
    """Évite qu'un texte généré notifie des personnes (@mention) ou ferme le bloc."""
    return text.replace("@", "@​")


def render_comment(f: Finding) -> str:
    parts = [f"**[{SEVERITY_LABEL.get(f.severity, f.severity)} · {f.category}] {_neutralize(f.title)}**"]
    if f.explanation:
        parts.append(_neutralize(f.explanation))
    if f.suggestion:
        parts.append(f"**Suggestion :** {_neutralize(f.suggestion)}")
    parts.append(f"<sub>source : {f.source}</sub>")
    return "\n\n".join(parts)


def render_summary(
    verdict: str,
    findings: list[Finding],
    inline_count: int,
    skipped: list[tuple[str, str]],
    incomplete_reasons: list[str],
    model: str,
    head_sha: str,
) -> str:
    counts = {s: sum(1 for f in findings if f.severity == s) for s in reversed(SEVERITIES)}
    rows = [
        MARKER,
        f"## Revue automatique — {VERDICT_TEXT[verdict]}",
        "",
        f"Commit analysé : `{head_sha[:7]}` · modèle : `{model}`",
        "",
        "| Bloquant | Majeur | Mineur | Info |",
        "|---:|---:|---:|---:|",
        f"| {counts['critical']} | {counts['major']} | {counts['minor']} | {counts['info']} |",
    ]

    summary_only = [f for f in findings if not f.inline] + [f for f in findings if f.inline][inline_count:]
    if summary_only:
        rows += ["", "### Remarques hors commentaires en ligne"]
        for f in summary_only:
            where = f"`{f.path}`" + (f" ligne {f.line}" if f.line else "")
            rows.append(f"- **[{SEVERITY_LABEL[f.severity]}]** {where} — {_neutralize(f.title)}")

    if incomplete_reasons:
        rows += ["", "### ⚠️ Revue incomplète"]
        rows += [f"- {r}" for r in incomplete_reasons]

    excluded = [(p, r) for p, r in skipped]
    if excluded:
        rows += ["", f"<details><summary>{len(excluded)} fichier(s) non analysé(s)</summary>", ""]
        rows += [f"- `{p}` — {r}" for p, r in excluded]
        rows += ["", "</details>"]

    rows += [
        "",
        "---",
        "<sub>Cette revue est un premier filtre : elle ne remplace pas la relecture humaine "
        "et ne fusionne rien. La décision de fusion reste humaine.</sub>",
    ]
    return "\n".join(rows)
