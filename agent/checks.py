"""Contrôles déterministes d'une PR : conteneur « checker » + résultat de la CI du dépôt.

Leurs remarques sont DÉTERMINISTES (agent.review.DETERMINISTIC_SOURCES) : elles
ne dépendent pas d'un modèle, donc elles peuvent rendre une PR bloquante même en
mode pilote (secret gitleaks, dépendance vulnérable grave, CI en échec).

Une panne (checker injoignable, outil en erreur, CI non terminée) n'est jamais
un succès : elle rend l'analyse incomplète.
"""
from __future__ import annotations

import json

import httpx

from agent.diff import FileDiff
from agent.review import Finding
from agent.secrets_scan import redact_text

CI_PATH = "(intégration continue)"
CI_FAILED = {"failure", "timed_out", "startup_failure"}
CI_INCOMPLETE = {"cancelled", "action_required", "stale"}
TOOL_LABEL = {"gitleaks": "gitleaks", "composer-audit": "composer audit", "phpstan": "PHPStan",
              "php-cs-fixer": "PHP-CS-Fixer", "ci": "CI du dépôt"}


def changed_map(files: list[FileDiff], skipped: list[tuple[str, str]]) -> dict[str, list[int] | None]:
    """Fichiers modifiés → lignes ajoutées (None : diff inconnu, fichier exclu ou trop gros)."""
    out: dict[str, list[int] | None] = {f.path: sorted(f.added) for f in files if f.status != "removed"}
    for path, reason in skipped:
        if "supprimé" not in reason:
            out.setdefault(path, None)
    return out


class CheckerClient:
    def __init__(self, url: str, timeout: float, transport: httpx.AsyncBaseTransport | None = None):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self._transport = transport

    async def check(self, archive: bytes, changed: dict, phpstan_level: int) -> list[dict]:
        async with httpx.AsyncClient(timeout=self.timeout, transport=self._transport) as c:
            resp = await c.post(f"{self.url}/check",
                                files={"archive": ("src.tar.gz", archive, "application/gzip")},
                                data={"meta": json.dumps({"changed": changed, "phpstan_level": phpstan_level})})
            resp.raise_for_status()
            return resp.json()["tools"]


def _clean(text: str, limit: int) -> str:
    return redact_text(str(text or ""))[0][:limit]


def tool_findings(tools: list[dict]) -> list[Finding]:
    """Rapport du checker → remarques (textes re-masqués : un outil peut citer du code)."""
    out = []
    for t in tools:
        for raw in t.get("findings", []):
            out.append(Finding(
                path=str(raw.get("path", "")), line=raw.get("line"), severity=raw.get("severity", "minor"),
                category=t["name"], title=_clean(raw.get("title"), 200),
                explanation=_clean(raw.get("explanation"), 1500), source=t["name"]))
    return out


def tool_incomplete(tools: list[dict]) -> list[str]:
    return [f"{TOOL_LABEL.get(t['name'], t['name'])} : {'délai dépassé' if t['status'] == 'timeout' else 'en erreur'}"
            + (f" ({_clean(t.get('message'), 160)})" if t.get("message") else "")
            for t in tools if t.get("status") in ("error", "timeout")]


def evaluate_ci(runs: list[dict], own_check: str, wanted: list[str]) -> tuple[str, list[Finding], list[str], list[dict]]:
    """État de la CI au commit : ("none" | "pending" | "done", remarques, incomplet, résumé par check)."""
    relevant = [r for r in runs if r.get("name") != own_check and (not wanted or r.get("name") in wanted)]
    summary = [{"name": r.get("name"), "status": r.get("status"), "conclusion": r.get("conclusion"),
                "url": r.get("html_url") or r.get("details_url") or ""} for r in relevant]
    if not relevant:
        return "none", [], [], summary
    if any(r.get("status") != "completed" for r in relevant):
        return "pending", [], [], summary
    findings, incomplete = [], []
    for r in relevant:
        conclusion = r.get("conclusion")
        if conclusion in CI_FAILED:
            detail = ((r.get("output") or {}).get("title") or "").strip()
            findings.append(Finding(
                path=CI_PATH, line=None, severity="critical", category="ci",
                title=f"CI en échec : {r.get('name')}",
                explanation=_clean(f"Conclusion « {conclusion} »" + (f" — {detail}" if detail else "")
                                   + (f". Détail : {r.get('html_url')}" if r.get("html_url") else "."), 600),
                source="ci", inline=False))
        elif conclusion in CI_INCOMPLETE:
            incomplete.append(f"CI « {r.get('name')} » : {conclusion}, résultat des tests inconnu")
    return "done", findings, incomplete, summary
