"""État du graphe de revue."""
from dataclasses import dataclass
from typing import Any, TypedDict

from agent.diff import FileDiff
from agent.review import Finding


class ReviewState(TypedDict, total=False):
    # Entrée (job de la file)
    delivery_id: str
    repo: str
    pr_number: int
    head_sha: str
    installation_id: int | None
    started_at: float

    # PR
    pr_title: str
    pr_body: str
    pr_author: str
    pr_url: str
    stale: bool
    check_id: int | None

    # Diff
    files: list[FileDiff]
    skipped: list[tuple[str, str]]
    total_files: int

    # Analyse
    secret_findings: list[Finding]
    llm_findings: list[Finding]
    findings: list[Finding]
    chunks_total: int
    chunks_failed: int
    incomplete_reasons: list[str]

    # Résultat
    verdict: str
    summary: str
    inline_count: int
    published: bool
    alert_sent: bool
    error: str | None


@dataclass
class Services:
    """Dépendances injectées via config["configurable"]["services"] (testable)."""
    github: Any
    llm: Any
    mailer: Any
    audit: Any
    settings: Any
    rules: str
