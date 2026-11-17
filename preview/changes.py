"""Décrire en clair ce qui a changé sur une page entre « avant » et « après ».

Deux sources, toutes deux déterministes :
  - le TEXTE visible de la page (lignes ajoutées / retirées) ;
  - les ZONES de pixels changés (changement visuel : couleur, taille, position).
Une page sans aucun changement n'est pas montrée : seulement citée comme vérifiée.
"""
from __future__ import annotations

import difflib
import re

MAX_LINES = 12
MAX_LINE_CHARS = 160


def _lines(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", l).strip() for l in (text or "").splitlines() if l.strip()]


def text_changes(before: str, after: str) -> tuple[list[str], list[str]]:
    """(lignes ajoutées, lignes retirées) du texte visible."""
    a, b = _lines(before), _lines(after)
    added, removed = [], []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op in ("replace", "delete"):
            removed += a[i1:i2]
        if op in ("replace", "insert"):
            added += b[j1:j2]
    cut = lambda xs: [x[:MAX_LINE_CHARS] for x in xs[:MAX_LINES]]  # noqa: E731
    return cut(added), cut(removed)


def where(zones: list[tuple[int, int, int, int]], height: int) -> list[str]:
    out: list[str] = []
    for _, y0, _, y1 in zones:
        mid = (y0 + y1) / 2
        label = ("en-tête" if mid < 70 else "haut de page" if mid < height / 3
                 else "milieu de page" if mid < 2 * height / 3 else "bas de page")
        if label not in out:
            out.append(label)
    return out


def _error_line(text: str) -> str:
    """Message principal d'une page d'erreur (la première phrase un peu longue)."""
    for line in _lines(text):
        if len(line) > 30:
            return line[:MAX_LINE_CHARS]
    return ""


def describe(before: dict, after: dict, pct: float | None, zones: list, height: int) -> dict:
    """{kind, changed, summary, text_added, text_removed, zones, where}.

    kind : missing | error | new | status | content | visual | none."""
    base = {"text_added": [], "text_removed": [], "zones": len(zones or []), "where": where(zones or [], height or 1)}
    b_status, a_status = before.get("status"), after.get("status")
    if not after.get("png"):
        return {**base, "kind": "missing", "changed": True,
                "summary": "La page ne s'affiche pas avec la PR" + (f" ({after.get('error')})" if after.get("error") else "") + "."}
    if (a_status or 0) >= 500:
        msg = _error_line(after.get("text", ""))
        return {**base, "kind": "error", "changed": True,
                "summary": f"La page renvoie une erreur {a_status} avec la PR" + (f" : « {msg} »" if msg else "") + "."}
    if not before.get("png") or b_status == 404:
        return {**base, "kind": "new", "changed": True, "summary": "Nouvelle page : elle n'existait pas avant la PR."}
    if b_status != a_status:
        return {**base, "kind": "status", "changed": True,
                "summary": f"Le statut HTTP de la page change : {b_status} → {a_status}."}

    added, removed = text_changes(before.get("text", ""), after.get("text", ""))
    if added or removed:
        parts = []
        if added:
            parts.append(f"{len(added)} ligne(s) de texte ajoutée(s)")
        if removed:
            parts.append(f"{len(removed)} retirée(s)")
        return {**base, "kind": "content", "changed": True, "text_added": added, "text_removed": removed,
                "summary": "Texte modifié : " + ", ".join(parts) + "."}
    if pct:
        spots = ", ".join(base["where"]) or "sur la page"
        return {**base, "kind": "visual", "changed": True,
                "summary": f"Changement visuel sans changement de texte (couleur, taille ou position) : "
                           f"{base['zones']} zone(s), {spots}."}
    return {**base, "kind": "none", "changed": False, "summary": "Rien de visible n'a changé."}
