"""StateGraph LangGraph — agent de revue des PR.

fetch_pr → load_diff → scan_secrets → load_context ─┬─ ai_review ──────┬─ decide → publish → alert → audit
                                                    ├─ static_checks ──┤
                                                    └─ ui_preview ─────┘
Les trois branches s'exécutent en parallèle ; `decide` les attend toutes.
Toute erreur → fail (statut neutre + audit). PR obsolète (nouveau push) → audit.
`static_checks` ne lève jamais d'erreur : une panne rend l'analyse incomplète.
`ui_preview` (aperçu avant / après) non plus : c'est une information, sans effet sur le verdict.

load_context : règles du dépôt (branche de base) et en-têtes des fichiers modifiés.
"""
from langgraph.graph import END, StateGraph

from agent import nodes
from agent.state import ReviewState

BEFORE = ["fetch_pr", "load_diff", "scan_secrets", "load_context"]
PARALLEL = ["ai_review", "static_checks", "ui_preview"]
AFTER = ["decide", "publish", "alert"]
PIPELINE = BEFORE + PARALLEL + AFTER


def _next(after: str, default):
    def route(state: ReviewState):
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
    g.set_entry_point(BEFORE[0])

    for current, following in zip(BEFORE, BEFORE[1:]):
        g.add_conditional_edges(current, _next(current, following),
                                {following: following, "fail": "fail", "audit": "audit"})
    # Fan-out : la route renvoie les deux branches à lancer en parallèle.
    g.add_conditional_edges(BEFORE[-1], _next(BEFORE[-1], PARALLEL),
                            {**{p: p for p in PARALLEL}, "fail": "fail", "audit": "audit"})
    # Fan-in : decide attend la fin des deux branches (et route vers fail si ai_review a échoué).
    g.add_edge(PARALLEL, AFTER[0])

    for current, following in zip(AFTER, AFTER[1:] + ["audit"]):
        targets = {following: following, "fail": "fail"}
        if following != "audit":
            targets["audit"] = "audit"
        g.add_conditional_edges(current, _next(current, following), targets)
    g.add_edge("audit", END)
    g.add_edge("fail", END)
    return g.compile()


review_graph = build_graph()
