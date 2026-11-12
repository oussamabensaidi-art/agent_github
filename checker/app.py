"""Service de contrôles statiques (conteneur isolé, sans secret).

POST /check (multipart) :
  - archive : tar.gz du dépôt au commit de la PR (tel que fourni par GitHub) ;
  - meta    : JSON {"changed": {chemin: [lignes ajoutées] | null}, "phpstan_level": 5}
              null = fichier modifié dont le diff n'est pas connu (trop gros, exclu).
Réponse : {"tools": [ToolResult…], "duration_ms": …}

Le worker est le seul client (réseau Docker interne). Chaque requête travaille dans
un dossier jetable, supprimé à la fin.
"""
import asyncio
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from checker import tools

MAX_ARCHIVE_BYTES = int(os.environ.get("CHECKER_MAX_ARCHIVE_MB", "50")) * 1024 * 1024
CONCURRENCY = int(os.environ.get("CHECKER_CONCURRENCY", "2"))
T_GITLEAKS = float(os.environ.get("CHECKER_TIMEOUT_GITLEAKS", "120"))
T_AUDIT = float(os.environ.get("CHECKER_TIMEOUT_AUDIT", "120"))
T_INSTALL = float(os.environ.get("CHECKER_TIMEOUT_INSTALL", "300"))
T_PHPSTAN = float(os.environ.get("CHECKER_TIMEOUT_PHPSTAN", "300"))
T_CS = float(os.environ.get("CHECKER_TIMEOUT_CS", "180"))
WORK = Path(os.environ.get("CHECKER_WORK_DIR", tempfile.gettempdir()))

app = FastAPI(title="calipso-pr-checker")
_slots = asyncio.Semaphore(CONCURRENCY)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/check")
async def check(archive: UploadFile = File(...), meta: str = Form(...)) -> dict:
    try:
        info = json.loads(meta)
        changed: dict[str, list[int] | None] = {
            str(k): (sorted({int(n) for n in v}) if v is not None else None)
            for k, v in (info.get("changed") or {}).items()}
        level = max(0, min(10, int(info.get("phpstan_level", 5))))
    except (ValueError, TypeError, AttributeError) as e:
        raise HTTPException(422, f"meta invalide : {e}") from e

    async with _slots:
        t0 = time.perf_counter()
        workdir = Path(tempfile.mkdtemp(prefix="pr-", dir=WORK))
        try:
            tar_path = workdir / "src.tar.gz"
            size = 0
            with open(tar_path, "wb") as out:
                while chunk := await archive.read(1 << 20):
                    size += len(chunk)
                    if size > MAX_ARCHIVE_BYTES:
                        raise HTTPException(413, "archive trop volumineuse")
                    out.write(chunk)
            try:
                root = await asyncio.to_thread(tools.safe_extract, tar_path, workdir / "src")
            except (tools.ArchiveError, OSError, EOFError) as e:
                raise HTTPException(422, f"archive refusée : {e}") from e
            tar_path.unlink(missing_ok=True)
            results = await run_all(root, changed, level)
        finally:
            await asyncio.to_thread(shutil.rmtree, workdir, True)
        return {"tools": [r.to_dict() for r in results],
                "duration_ms": round((time.perf_counter() - t0) * 1000)}


async def run_all(root: Path, changed: dict, level: int) -> list[tools.ToolResult]:
    php_files = [p for p, lines in changed.items()
                 if p.endswith(".php") and lines and (root / p).is_file()]
    first = await asyncio.gather(
        tools.timed("gitleaks", tools.gitleaks(root, changed, T_GITLEAKS), T_GITLEAKS + 5),
        tools.timed("composer-audit", tools.composer_audit(root, changed, T_AUDIT), T_AUDIT + 5),
    )
    if not php_files:
        skip = "aucune ligne PHP ajoutée"
        return [*first, tools.ToolResult("phpstan", "skipped", message=skip),
                tools.ToolResult("php-cs-fixer", "skipped", message=skip)]

    install_error = await tools.composer_install(root, T_INSTALL) if (root / "composer.json").exists() else None
    if install_error and install_error != "pas de composer.json":
        phpstan_res = tools.ToolResult("phpstan", "error",
                                       message=f"dépendances non installées : {install_error}"[:500])
        cs_res = await tools.timed("php-cs-fixer", tools.cs_fixer(root, php_files, changed, T_CS), T_CS + 5)
        return [*first, phpstan_res, cs_res]
    rest = await asyncio.gather(
        tools.timed("phpstan", tools.phpstan(root, php_files, changed, level, T_PHPSTAN), T_PHPSTAN + 5),
        tools.timed("php-cs-fixer", tools.cs_fixer(root, php_files, changed, T_CS), T_CS + 5),
    )
    return [*first, *rest]
