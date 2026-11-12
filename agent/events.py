"""Émission d'événements depuis les nœuds (flux « custom » de LangGraph).

Les nœuds n'écrivent jamais directement en base : ils émettent, le runner
consomme `graph.astream(stream_mode=["custom", "values"])` et transmet au
journal d'événements, qui masque à nouveau les secrets avant d'écrire.
"""
import time

from langgraph.config import get_stream_writer


def emit(type_: str, **data) -> None:
    try:
        writer = get_stream_writer()
    except Exception:  # noqa: BLE001 — hors exécution du graphe : rien à émettre
        return
    writer({"type": type_, "ts": time.time(), "data": data})
