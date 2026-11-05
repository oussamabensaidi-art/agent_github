"""StateGraph LangGraph — agent de revue des PR (prototype semaines 1-2).

fetch_pr → load_diff → scan_secrets → ai_review → decide → publish → alert → audit
Toute erreur → fail (statut neutre + audit). PR obsolète (nouveau push) → audit.

Semaines 3-4 : un nœud static_checks (PHPStan, PHP-CS-Fixer, PHPUnit,
composer audit, gitleaks) s'insérera entre scan_secrets et ai_review.
Semaines 5-6 : un nœud load_context (code lié, règles du dépôt) avant ai_review.
"""
from langgraph.graph import END, StateGraph

from agent import nodes
from agent.state import ReviewState

PIPELINE = ["fetch_pr", "load_diff", "scan_secrets", "ai_review", "decide", "publish", "alert"]


def _next(after: str, default: str):
    def route(state: ReviewState) -> str:
        if state.get("error"):
            return "fail"
        if after == "fetch_pr" and state.get("stale"):
            return "audit"
        return default
    return route


def build_graph():
    g = StateGraph(ReviewState)
    for name in PIPELINE:
        g.add_node(name, getattr(nodes, name))
    g.add_node("audit", nodes.audit)
    g.add_node("fail", nodes.fail)

    g.set_entry_point(PIPELINE[0])
    for current, following in zip(PIPELINE, PIPELINE[1:] + ["audit"]):
        g.add_conditional_edges(current, _next(current, following),
                                {following: following, "fail": "fail", "audit": "audit"}
                                if following != "audit" else {"audit": "audit", "fail": "fail"})
    g.add_edge("audit", END)
    g.add_edge("fail", END)
    return g.compile()


review_graph = build_graph()
