"""Aperçu avant / après : client du conteneur « preview » et règles d'activation.

L'aperçu est une INFORMATION pour le relecteur : il ne change jamais le verdict et
une panne ne rend pas l'analyse incomplète (elle est simplement signalée).

Il ne tourne que si :
  - PREVIEW_ENABLED et le dépôt est listé dans PREVIEW_REPOS (il exécute le code de la PR) ;
  - le dépôt a un `.github/pr-preview.json` sur sa branche de BASE (une PR ne peut
    pas changer la façon dont elle est lancée) ;
  - la PR modifie au moins un fichier d'interface.
"""
from __future__ import annotations

import base64
import json

import httpx

from agent.secrets_scan import redact_text
from preview.pages import ui_files

KINDS = ("before", "after", "diff")


def allowed(settings, repo: str) -> bool:
    return bool(settings.PREVIEW_ENABLED and repo.lower() in settings.preview_repos)


def parse_config(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        cfg = json.loads(raw)
    except ValueError:
        return None
    return cfg if isinstance(cfg, dict) else None


def ui_changed(changed: dict, cfg: dict | None) -> list[str]:
    return ui_files(list(changed), (cfg or {}).get("ui_files"))


class PreviewClient:
    def __init__(self, url: str, timeout: float, transport: httpx.AsyncBaseTransport | None = None):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self._transport = transport

    async def preview(self, base: bytes, head: bytes, changed: dict, cfg: dict) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout, transport=self._transport) as c:
            resp = await c.post(f"{self.url}/preview",
                                files={"base": ("base.tar.gz", base, "application/gzip"),
                                       "head": ("head.tar.gz", head, "application/gzip")},
                                data={"meta": json.dumps({"changed": changed, "config": cfg})})
            resp.raise_for_status()
            return resp.json()


def split_page(page: dict) -> tuple[dict, dict[str, bytes]]:
    """Page renvoyée par le conteneur → (métadonnées pour l'événement, images à stocker)."""
    images: dict[str, bytes] = {}
    for kind, data in (("before", (page.get("before") or {}).get("png")),
                       ("after", (page.get("after") or {}).get("png")),
                       ("diff", page.get("diff_png"))):
        if data:
            images[kind] = base64.b64decode(data)

    def side(s: dict | None) -> dict:
        s = s or {}
        return {"status": s.get("status"), "final_path": str(s.get("final_path") or "")[:300],
                "error": redact_text(str(s.get("error") or ""))[0][:200], "image": bool(s.get("png"))}

    change = page.get("change") or {}
    clean = lambda xs: [redact_text(str(x))[0][:160] for x in (xs or [])][:12]  # noqa: E731
    meta = {"path": str(page.get("path", ""))[:300], "route": str(page.get("route", ""))[:120],
            "reason": redact_text(str(page.get("reason", "")))[0][:300], "diff_pct": page.get("diff_pct"),
            "before": side(page.get("before")), "after": side(page.get("after")),
            "change": {"kind": str(change.get("kind", ""))[:20],
                       "summary": redact_text(str(change.get("summary", "")))[0][:400],
                       "text_added": clean(change.get("text_added")), "text_removed": clean(change.get("text_removed")),
                       "zones": int(change.get("zones") or 0), "where": clean(change.get("where"))},
            "images": sorted(images)}
    return meta, images


# ------------------------------------------------------------------ suggestions de l'IA

SUGGEST_SYSTEM = """Tu aides une personne qui va tester À LA MAIN une application web modifiée par une pull request.
On te donne : les changements réellement observés sur les pages (captures avant / après comparées)
et le code des fichiers d'interface modifiés.

Propose de 2 à 5 vérifications concrètes à faire dans l'application : quelle page ouvrir, quoi cliquer
ou saisir, quoi regarder. Règles :
- appuie-toi UNIQUEMENT sur ce qui est fourni ; n'invente ni page, ni bouton, ni fonctionnalité ;
- une vérification = une action précise, réalisable par une personne dans le navigateur ;
- pense aux cas que les captures ne montrent pas : autre rôle (lecteur / gestionnaire), donnée vide,
  clic sur le nouveau bouton, petit écran, message d'erreur ;
- pas de remarque sur le style du code.

Réponds au format JSON demandé : un élément de « findings » par vérification, avec
path = chemin de la page concernée (ex. /contrats/1), line = 0, severity = "info", category = "tests",
title = la vérification (une phrase à l'impératif), explanation = le changement qui la motive."""

MAX_SUGGESTIONS = 5


def suggestion_prompt(pages: list[dict], files: list, max_chars: int = 5000) -> str:
    """Changements observés + diff des fichiers d'interface (déjà masqués par scan_secrets)."""
    rows = ["## Changements observés sur les pages (avant → après la PR)"]
    for p in pages:
        c = p.get("change") or {}
        rows.append(f"- Page {p['path']} ({p.get('reason', '')}) : {c.get('summary', '')}")
        if c.get("text_added"):
            rows.append("  Texte ajouté : " + " | ".join(c["text_added"][:8]))
        if c.get("text_removed"):
            rows.append("  Texte retiré : " + " | ".join(c["text_removed"][:8]))
    rows += ["", "## Code modifié (fichiers d'interface)"]
    used = 0
    for f in files:
        if not getattr(f, "patch", ""):
            continue
        block = f"### {f.path}\n```diff\n{f.patch}\n```"
        if used + len(block) > max_chars:
            rows.append(f"### {f.path} (diff non montré : trop long)")
            continue
        rows.append(block)
        used += len(block)
    return "\n".join(rows)


def parse_suggestions(items: list[dict], known_paths: set[str]) -> list[dict]:
    out = []
    for it in items or []:
        check = redact_text(str(it.get("title") or "").strip())[0][:300]
        if not check:
            continue
        page = str(it.get("path") or "").strip()[:300]
        out.append({"page": page if page in known_paths else "", "check": check,
                    "why": redact_text(str(it.get("explanation") or "").strip())[0][:400]})
    return out[:MAX_SUGGESTIONS]
