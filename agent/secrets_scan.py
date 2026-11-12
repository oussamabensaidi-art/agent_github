"""Détection et masquage des secrets AVANT tout envoi au modèle.

Exigence sécurité du cahier des charges : les secrets sont détectés avant le
traitement. Ce scanner intégré couvre le prototype ; gitleaks s'ajoutera en
semaines 3-4 (contrôles statiques) sans retirer ce garde-fou.

Le secret lui-même n'est jamais recopié dans une remarque, un log ou un email.
"""
import re

from agent.diff import FileDiff
from agent.review import PR_TEXT_PATH, Finding

PATTERNS: list[tuple[str, re.Pattern]] = [
    ("Clé privée", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("Clé d'accès AWS", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("Jeton GitHub", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})\b")),
    ("Jeton Slack", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("Clé d'API Google", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("Clé Stripe", re.compile(r"\b(?:sk|rk)_live_[0-9A-Za-z]{16,}\b")),
    ("Jeton JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("URL avec identifiants", re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s:/@'\"]+:[^\s@'\"]{6,}@[^\s'\"]+", re.I)),
    ("Secret en dur", re.compile(
        r"""(?i)\b[\w-]*(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?key|token|private[_-]?key)[\w-]*['"]?\s*(?:=>|=|:)\s*['"]([^'"\s]{8,})['"]"""
    )),
]

# Valeurs factices fréquentes : pas une fuite.
PLACEHOLDER_RE = re.compile(
    r"(?i)^(?:change[-_]?me|example|exemple|your[-_]|xxx|\*\*\*|<|%env\(|\$\{|\{\{|test|dummy|placeholder|redacted)"
)

REDACTED = "[SECRET MASQUÉ]"


def _match_is_real(name: str, m: re.Match) -> bool:
    if name == "Secret en dur":
        return not PLACEHOLDER_RE.match(m.group(1))
    return True


def redact_text(text: str) -> tuple[str, list[str]]:
    """Masque les secrets d'un texte libre. Renvoie (texte masqué, types détectés)."""
    found: list[str] = []
    for name, rx in PATTERNS:
        if any(_match_is_real(name, m) for m in rx.finditer(text or "")):
            found.append(name)
            text = rx.sub(lambda m, n=name: REDACTED if _match_is_real(n, m) else m.group(0), text)
    return text or "", found


def redact_obj(obj):
    """Masque récursivement les chaînes d'une structure JSON (garde-fou du journal d'événements)."""
    if isinstance(obj, str):
        return redact_text(obj)[0]
    if isinstance(obj, list):
        return [redact_obj(v) for v in obj]
    if isinstance(obj, dict):
        return {k: redact_obj(v) for k, v in obj.items()}
    return obj


def scan_pr_text(title: str, body: str) -> tuple[str, str, list[Finding]]:
    """Titre et description de la PR : masqués avant le modèle, secret signalé comme bloquant."""
    title, in_title = redact_text(title)
    body, in_body = redact_text(body)
    findings = [
        Finding(path=PR_TEXT_PATH, line=None, severity="critical", category="secret",
                title=f"{name} détecté(e) dans le {where} de la PR",
                explanation=("Une valeur sensible apparaît dans le texte de la PR. Elle a été masquée "
                             "avant l'analyse IA et n'est pas reproduite ici. Modifiez le texte de la PR "
                             "et, si la valeur est réelle, révoquez-la."),
                source="secret-scan", inline=False)
        for where, names in (("titre", in_title), ("description", in_body)) for name in names
    ]
    return title, body, findings


def scan_and_redact(files: list[FileDiff]) -> list[Finding]:
    """Signale les secrets des lignes ajoutées puis masque tout le patch."""
    findings: list[Finding] = []
    for f in files:
        for line_no, text in f.added.items():
            for name, rx in PATTERNS:
                if any(_match_is_real(name, m) for m in rx.finditer(text)):
                    findings.append(Finding(
                        path=f.path, line=line_no, severity="critical", category="secret",
                        title=f"{name} détecté(e) dans le code",
                        explanation=("Une valeur sensible semble écrite en dur. Elle a été masquée "
                                     "avant l'analyse IA et n'est pas reproduite ici. Si elle est réelle, "
                                     "considérez-la comme compromise : révoquez-la et faites-la tourner."),
                        suggestion="Lire la valeur depuis une variable d'environnement ou un coffre de secrets.",
                        source="secret-scan",
                    ))
                    break

        redacted_lines = []
        for raw in f.patch.splitlines():
            for name, rx in PATTERNS:
                raw = rx.sub(lambda m, n=name: REDACTED if _match_is_real(n, m) else m.group(0), raw)
            redacted_lines.append(raw)
        f.patch = "\n".join(redacted_lines)
        f.reparse()
    return findings
