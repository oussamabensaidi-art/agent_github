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
    run_id: str
    queued_at: float | None
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
    # Contrôles statiques + CI (branche parallèle : clés distinctes de ai_review)
    static_findings: list[Finding]
    static_incomplete: list[str]
    checks: list[dict]

    # Résultat
    verdict: str
    summary: str
    inline_count: int
    published: bool
    publish_skipped: str | None   # "dry_run" | "kill_switch"
    superseded: bool              # un commit plus récent est arrivé avant la publication
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
    rules_version: str = ""
    controls: Any = None   # .publishing_enabled() -> bool (interrupteur, lu à chaque écriture)
    events: Any = None     # journal d'événements (store.EventSink)
    checker: Any = None    # agent.checks.CheckerClient (None : contrôles statiques désactivés)
