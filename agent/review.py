"""Remarques, validation anti-hallucination, verdict et rendu Markdown.

Verdict v2 (règles déterministes, versionnées) — 4 états :

  1. BLOQUANTE            : remarque critique d'une source DÉTERMINISTE (détection de
                            secrets, gitleaks, dépendance vulnérable grave, CI en échec).
                            Hors mode pilote, une remarque critique de l'IA bloque aussi.
  2. ANALYSE_INCOMPLETE   : une partie de la PR n'a pas été analysée (fichier trop gros,
                            diff non fourni par GitHub, limite de taille, lot en échec,
                            outil de contrôle en erreur, CI non terminée).
  3. A_VERIFIER           : remarque majeure, ou critique de l'IA en mode pilote.
  4. CONTROLES_SATISFAITS : sinon.

En mode pilote (par défaut), l'IA est consultative : elle ne peut jamais, seule,
rendre une PR bloquante.
"""
import hashlib
from dataclasses import asdict, dataclass

SEVERITIES = ["info", "minor", "major", "critical"]
SEVERITY_LABEL = {"critical": "CRITIQUE", "major": "MAJEUR", "minor": "MINEUR", "info": "INFO"}

# Sources dont le résultat ne dépend pas d'un modèle : seules autorisées à bloquer en pilote.
DETERMINISTIC_SOURCES = {"secret-scan", "gitleaks", "composer-audit", "phpstan", "php-cs-fixer", "ci"}
# Sources de détection de secrets : les autres remarques sur la même ligne sont des doublons.
SECRET_SOURCES = {"secret-scan", "gitleaks"}

VERDICT_BLOCKING = "BLOQUANTE"
VERDICT_CHECK = "A_VERIFIER"
VERDICT_OK = "CONTROLES_SATISFAITS"
VERDICT_INCOMPLETE = "ANALYSE_INCOMPLETE"
VERDICTS = [VERDICT_BLOCKING, VERDICT_INCOMPLETE, VERDICT_CHECK, VERDICT_OK]

# Issues hors verdict, publiées elles aussi sur le check / statut.
OUTCOME_FAILED = "ECHEC_AGENT"        # l'analyse n'a pas abouti
OUTCOME_SUPERSEDED = "REMPLACEE"      # un commit plus récent est arrivé pendant l'analyse

VERDICT_TEXT = {
    VERDICT_BLOCKING: "🔴 Bloquante",
    VERDICT_CHECK: "🟠 À vérifier",
    VERDICT_OK: "🟢 Contrôles satisfaits",
    VERDICT_INCOMPLETE: "⚪ Analyse incomplète",
    OUTCOME_FAILED: "⚠️ Analyse en échec — relecture humaine requise",
    OUTCOME_SUPERSEDED: "↪️ Analyse remplacée par un commit plus récent",
}

# Check run (mode App). `neutral` n'empêche pas la fusion : réservé à « à vérifier »,
# qui est un avis. Ce qui n'a pas été analysé n'est jamais présenté comme réussi.
CHECK_CONCLUSION = {
    VERDICT_BLOCKING: "failure",
    VERDICT_CHECK: "neutral",
    VERDICT_OK: "success",
    VERDICT_INCOMPLETE: "action_required",
    OUTCOME_FAILED: "action_required",
    OUTCOME_SUPERSEDED: "cancelled",
}

# Statut de commit (mode jeton) : pas d'état neutre → seul « contrôles satisfaits » est vert.
STATUS_STATE = {
    VERDICT_BLOCKING: "failure",
    VERDICT_CHECK: "failure",
    VERDICT_OK: "success",
    VERDICT_INCOMPLETE: "error",
    OUTCOME_FAILED: "error",
    OUTCOME_SUPERSEDED: "error",
}

# Version des règles de verdict : à incrémenter à chaque changement de compute_verdict.
VERDICT_RULES_VERSION = "verdict-v3"  # v3 : contrôles statiques et CI comme sources déterministes

# Chemin réservé aux remarques sur le titre / la description de la PR.
PR_TEXT_PATH = "(titre / description de la PR)"

MARKER = "<!-- calipso-pr-review -->"

CHECK_LABEL = {"gitleaks": "gitleaks (secrets)", "composer-audit": "composer audit (dépendances)",
               "phpstan": "PHPStan (analyse statique)", "php-cs-fixer": "PHP-CS-Fixer (style)",
               "ci": "CI du dépôt (tests)"}
CHECK_STATUS = {"ok": "✅ rien à signaler", "findings": "⚠️ remarques", "skipped": "➖ non applicable",
                "error": "⚪ en erreur", "timeout": "⚪ délai dépassé", "pending": "⚪ non terminée",
                "failed": "❌ en échec"}


def rules_version(rules_text: str) -> str:
    """Version publiée avec chaque verdict : règles de verdict + empreinte des règles d'équipe."""
    digest = hashlib.sha256(rules_text.encode("utf-8")).hexdigest()[:10]
    return f"{VERDICT_RULES_VERSION}+regles-{digest}"


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
    id: str = ""
    chunk: int | None = None

    @property
    def deterministic(self) -> bool:
        return self.source in DETERMINISTIC_SOURCES

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


def validate_findings_detailed(
    findings: list[Finding],
    commentable: dict[str, set[int]],
    min_severity: str,
) -> tuple[list[Finding], list[tuple[Finding, str]]]:
    """Écarte les remarques inventées, sous le seuil, ou en double.

    Renvoie (remarques gardées, [(remarque écartée, raison)]).
    - fichier absent du diff analysé → écartée (hallucination) ;
    - ligne hors du diff → gardée, mais dans le résumé (pas inline) ;
    - gravité sous MIN_COMMENT_SEVERITY → écartée (anti faux positifs).
    Les remarques du scanner de secrets passent toujours le seuil.
    """
    kept: list[Finding] = []
    dropped: list[tuple[Finding, str]] = []
    seen: set[tuple] = set()
    # Lignes déjà signalées par le scanner de secrets : le modèle y voit
    # "[SECRET MASQUÉ]" et la recommente malgré la consigne (constaté avec le 7b).
    secret_lines = {(f.path, f.line) for f in findings if f.source == "secret-scan"}
    any_secret_lines = {(f.path, f.line) for f in findings if f.source in SECRET_SOURCES}
    for f in findings:
        if f.severity not in SEVERITIES or not f.title:
            dropped.append((f, "format invalide"))
            continue
        if f.source == "llm" and rank(f.severity) < rank(min_severity):
            dropped.append((f, "sous le seuil de gravité"))
            continue
        if ((f.source == "llm" and (f.path, f.line) in any_secret_lines)
                or (f.source == "gitleaks" and (f.path, f.line) in secret_lines)):
            dropped.append((f, "doublon d'un secret détecté"))
            continue
        if f.source == "secret-scan" and f.path == PR_TEXT_PATH:
            f.inline = False
        elif f.path not in commentable:
            if not f.deterministic:
                dropped.append((f, "fichier absent du diff (remarque inventée)"))
                continue
            f.inline = False  # outil : fichier exclu du diff (composer.lock) ou CI → résumé
        else:
            f.inline = f.line is not None and f.line in commentable[f.path]
        key = (f.path, f.line, f.title.lower())
        if key in seen:
            dropped.append((f, "doublon"))
            continue
        seen.add(key)
        kept.append(f)
    kept.sort(key=lambda f: (-rank(f.severity), f.path, f.line or 0))
    return kept, dropped


def validate_findings(findings: list[Finding], commentable: dict[str, set[int]],
                      min_severity: str) -> list[Finding]:
    return validate_findings_detailed(findings, commentable, min_severity)[0]


def compute_verdict(findings: list[Finding], incomplete_reasons: list[str], pilot_mode: bool = True) -> str:
    critical = [f for f in findings if f.severity == "critical"]
    if any(f.deterministic for f in critical) or (critical and not pilot_mode):
        return VERDICT_BLOCKING
    if incomplete_reasons:
        return VERDICT_INCOMPLETE
    if critical or any(f.severity == "major" for f in findings):
        return VERDICT_CHECK
    return VERDICT_OK


def _neutralize(text: str) -> str:
    """Évite qu'un texte généré notifie des personnes (@mention) ou ferme le bloc."""
    return text.replace("@", "@​")


def severity_label(f: Finding, pilot_mode: bool) -> str:
    label = SEVERITY_LABEL.get(f.severity, f.severity)
    if pilot_mode and f.severity == "critical" and not f.deterministic:
        label += " · avis IA"
    return label


def render_comment(f: Finding, pilot_mode: bool = True) -> str:
    parts = [f"**[{severity_label(f, pilot_mode)} · {f.category}] {_neutralize(f.title)}**"]
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
    rules_ver: str = "",
    pilot_mode: bool = True,
    details_url: str = "",
    checks: list[dict] | None = None,
) -> str:
    counts = {s: sum(1 for f in findings if f.severity == s) for s in reversed(SEVERITIES)}
    meta = f"Commit analysé : `{head_sha[:7]}` · modèle : `{model}`"
    if rules_ver:
        meta += f" · règles : `{rules_ver}`"
    rows = [
        MARKER,
        f"## Revue automatique — {VERDICT_TEXT[verdict]}",
        "",
        meta,
        "",
        "| Critique | Majeur | Mineur | Info |",
        "|---:|---:|---:|---:|",
        f"| {counts['critical']} | {counts['major']} | {counts['minor']} | {counts['info']} |",
    ]
    if pilot_mode:
        rows += ["", "> Mode pilote : les remarques de l'IA sont des avis. Seules les détections "
                     "déterministes (secrets, contrôles automatiques, CI) peuvent rendre la PR bloquante."]
    if checks:
        rows += ["", "### Contrôles automatiques", "", "| Contrôle | Résultat | Durée |", "|---|---|---:|"]
        for c in checks:
            rows.append(f"| {CHECK_LABEL.get(c['name'], c['name'])} | {CHECK_STATUS.get(c['status'], c['status'])}"
                        + (f" ({c['count']})" if c.get("count") else "")
                        + (f" — {_neutralize(c['message'])[:120]}" if c.get("message") else "")
                        + f" | {round((c.get('duration_ms') or 0) / 1000, 1)} s |")

    summary_only = [f for f in findings if not f.inline] + [f for f in findings if f.inline][inline_count:]
    if summary_only:
        rows += ["", "### Remarques hors commentaires en ligne"]
        for f in summary_only:
            where = f"`{f.path}`" + (f" ligne {f.line}" if f.line else "")
            rows.append(f"- **[{severity_label(f, pilot_mode)}]** {where} — {_neutralize(f.title)}")

    if incomplete_reasons:
        rows += ["", "### ⚪ Analyse incomplète — ces éléments n'ont pas été relus"]
        rows += [f"- {r}" for r in incomplete_reasons]

    excluded = [(p, r) for p, r in skipped]
    if excluded:
        rows += ["", f"<details><summary>{len(excluded)} fichier(s) non analysé(s)</summary>", ""]
        rows += [f"- `{p}` — {r}" for p, r in excluded]
        rows += ["", "</details>"]

    if details_url:
        rows += ["", f"[Détail de l'analyse]({details_url})"]
    rows += [
        "",
        "---",
        "<sub>Cette revue est un premier filtre : elle ne remplace pas la relecture humaine "
        "et ne fusionne rien. La décision de fusion reste humaine.</sub>",
    ]
    return "\n".join(rows)
