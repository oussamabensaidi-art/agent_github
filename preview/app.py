"""Service d'aperçu avant / après (conteneur isolé, sans secret).

POST /preview (multipart) :
  - base, head : tar.gz du dépôt au commit de base et au commit de la PR ;
  - meta       : JSON {"changed": {chemin: [lignes ajoutées] | null}, "config": {…}}
                 config = `.github/pr-preview.json` lu sur la branche de BASE.
Réponse : {"status": "ok" | "skipped" | "error", "message", "pages": [...], "duration_ms"}
  page = {path, route, reason, diff_pct, diff_png, before: {status, final_path, png, error},
          after: {...}} ; les images sont en base64.

Le worker est le seul client (réseau Docker interne). Chaque requête travaille dans
un dossier jetable, supprimé à la fin.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from checker.tools import ArchiveError, safe_extract
from preview import shots
from preview.changes import describe
from preview.pages import choose_pages, parse_routes, ui_files

MAX_ARCHIVE_BYTES = int(os.environ.get("PREVIEW_MAX_ARCHIVE_MB", "50")) * 1024 * 1024
T_INSTALL = float(os.environ.get("PREVIEW_TIMEOUT_INSTALL", "300"))
T_CONSOLE = float(os.environ.get("PREVIEW_TIMEOUT_CONSOLE", "120"))
WORK = Path(os.environ.get("PREVIEW_WORK_DIR", tempfile.gettempdir()))

app = FastAPI(title="calipso-pr-preview")
_slot = asyncio.Semaphore(1)   # un aperçu à la fois : deux applications + un navigateur, c'est lourd


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


async def _save(upload: UploadFile, dest: Path) -> None:
    size = 0
    with open(dest, "wb") as out:
        while chunk := await upload.read(1 << 20):
            size += len(chunk)
            if size > MAX_ARCHIVE_BYTES:
                raise HTTPException(413, "archive trop volumineuse")
            out.write(chunk)


def _b64(data: bytes | None) -> str | None:
    return base64.b64encode(data).decode() if data else None


@app.post("/preview")
async def preview(base: UploadFile = File(...), head: UploadFile = File(...), meta: str = Form(...)) -> dict:
    try:
        info = json.loads(meta)
        changed = {str(k): (sorted({int(n) for n in v}) if v is not None else None)
                   for k, v in (info.get("changed") or {}).items()}
        cfg = dict(info.get("config") or {})
    except (ValueError, TypeError, AttributeError) as e:
        raise HTTPException(422, f"meta invalide : {e}") from e

    t0 = time.perf_counter()
    if not ui_files(list(changed), cfg.get("ui_files")):
        return {"status": "skipped", "message": "aucun fichier d'interface modifié", "pages": [], "duration_ms": 0}

    async with _slot:
        workdir = Path(tempfile.mkdtemp(prefix="pv-", dir=WORK))
        try:
            roots = {}
            for side, upload in (("before", base), ("after", head)):
                tar = workdir / f"{side}.tar.gz"
                await _save(upload, tar)
                try:
                    roots[side] = await asyncio.to_thread(safe_extract, tar, workdir / side)
                except (ArchiveError, OSError, EOFError) as e:
                    raise HTTPException(422, f"archive refusée : {e}") from e
                tar.unlink(missing_ok=True)
            result = await run_preview(roots["before"], roots["after"], changed, cfg)
        finally:
            await asyncio.to_thread(shutil.rmtree, workdir, True)
    result["duration_ms"] = round((time.perf_counter() - t0) * 1000)
    return result


async def run_preview(before: Path, after: Path, changed: dict, cfg: dict) -> dict:
    # Installation : « après » d'abord ; « avant » réutilise vendor/ si les dépendances sont identiques.
    err_after = await shots.install(after, cfg, T_INSTALL)
    if err_after is None and shots.same_dependencies(after, before):
        await asyncio.to_thread(shots.copy_vendor, after, before)
    err_before = await shots.install(before, cfg, T_INSTALL)
    if err_after:
        return {"status": "error", "message": f"la version de la PR ne s'installe pas : {err_after}", "pages": []}

    try:
        routes = parse_routes(await shots.routes(after, cfg, T_CONSOLE))
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "message": f"{e}"[:300], "pages": []}
    pages = choose_pages(after, changed, routes, cfg)
    if not pages:
        return {"status": "skipped", "message": "aucune page de l'application n'affiche les fichiers modifiés",
                "pages": []}

    from playwright.async_api import async_playwright
    paths = [p.path for p in pages]
    login = cfg.get("login") or None
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--disable-dev-shm-usage", "--no-sandbox"])
        try:
            shots_after = await _side(browser, after, cfg, paths, login, None)
            shots_before = await _side(browser, before, cfg, paths, login, err_before)
        finally:
            await browser.close()

    out, unchanged = [], []
    for page, b, a in zip(pages, shots_before, shots_after):
        pct, diff, zones, height = None, None, [], 0
        # Comparaison pixel par pixel seulement entre deux pages comparables (même statut HTTP) :
        # une page 404 « avant » et une page 500 « après » n'ont rien en commun.
        if a["png"] and b["png"] and a["status"] == b["status"]:
            pct, diff, zones, height = await asyncio.to_thread(shots.compare, b["png"], a["png"])
        change = describe(b, a, pct, zones, height)
        if not change["changed"]:
            unchanged.append({"path": page.path, "reason": page.reason})
            continue   # deux captures identiques : rien à montrer
        side = lambda s: {k: v for k, v in {**s, "png": _b64(s["png"])}.items() if k != "text"}  # noqa: E731
        out.append({**page.to_dict(), "diff_pct": pct, "diff_png": _b64(diff) if zones else None,
                    "change": change, "before": side(b), "after": side(a)})
    message = f"version de base indisponible : {err_before}" if err_before else ""
    return {"status": "ok", "message": message[:300], "pages": out, "unchanged": unchanged}


async def _side(browser, root: Path, cfg: dict, paths: list[str], login, install_error: str | None) -> list[dict]:
    empty = lambda msg: [{"status": None, "final_path": "", "png": None, "error": msg[:200]} for _ in paths]  # noqa: E731
    if install_error:
        return empty(install_error)
    try:
        async with shots.AppServer(root, cfg) as server:
            return await shots.capture(browser, server.url, paths, login)
    except Exception as e:  # noqa: BLE001
        return empty(f"{type(e).__name__}: {e}")
