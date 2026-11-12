"""Contrôles statiques d'une PR : extraction sûre de l'archive, exécution des outils,
lecture de leurs rapports.

Aucun outil n'exécute volontairement le code de la PR :
  - composer : --no-scripts --no-plugins, et les `autoload.files` sont retirés ;
  - PHPStan et PHP-CS-Fixer : configuration de l'agent, jamais celle du dépôt
    (un phpstan.neon ou .php-cs-fixer.php du dépôt peut charger du PHP) ;
  - PHPUnit n'est pas lancé ici : son résultat vient de la CI du dépôt.
Le conteneur reste isolé (sans secret, sans accès à la base, limites de ressources)
en défense en profondeur.

Seules les remarques sur des lignes AJOUTÉES par la PR sont rapportées (sauf
composer audit / gitleaks sur des fichiers modifiés) : l'existant n'est pas imputé à la PR.
"""
from __future__ import annotations

import asyncio
import json
import os
import posixpath
import re
import tarfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

CONF = Path(os.environ.get("CHECKER_CONF_DIR", "/opt/checker"))
TOOLS_BIN = os.environ.get("CHECKER_TOOLS_BIN", "/opt/tools/vendor/bin")

MAX_MEMBERS = 50_000
MAX_TOTAL_BYTES = 300 * 1024 * 1024
MAX_FINDINGS_PER_TOOL = 50


class ArchiveError(ValueError):
    pass


@dataclass
class ToolFinding:
    path: str
    line: int | None
    severity: str
    title: str
    explanation: str = ""
    rule: str = ""


@dataclass
class ToolResult:
    name: str
    status: str                 # ok | findings | skipped | error | timeout
    duration_ms: int = 0
    message: str = ""
    findings: list[ToolFinding] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------- archive
def safe_extract(archive: Path, dest: Path) -> Path:
    """Extrait une archive tar(.gz) GitHub sans lien, sans chemin sortant, avec limites.

    Renvoie la racine du dépôt (le dossier unique de premier niveau des archives GitHub)."""
    dest = dest.resolve()
    total = 0
    tops: set[str] = set()
    with tarfile.open(archive, "r:*") as tar:
        members = tar.getmembers()
        if len(members) > MAX_MEMBERS:
            raise ArchiveError(f"archive trop volumineuse ({len(members)} entrées)")
        for m in members:
            name = posixpath.normpath(m.name)
            if name.startswith(("/", "../")) or name == ".." or "\\" in m.name or ":" in name.split("/")[0]:
                raise ArchiveError(f"chemin refusé dans l'archive : {m.name!r}")
            if m.issym() or m.islnk() or m.isdev() or m.isfifo():
                continue  # liens et fichiers spéciaux ignorés
            if not (m.isfile() or m.isdir()):
                continue
            total += m.size
            if total > MAX_TOTAL_BYTES:
                raise ArchiveError("archive trop volumineuse une fois décompressée")
            target = (dest / name).resolve()
            if dest not in target.parents and target != dest:
                raise ArchiveError(f"chemin refusé dans l'archive : {m.name!r}")
            tops.add(name.split("/")[0])
            if m.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tar.extractfile(m)
            if src is None:
                continue
            with src, open(target, "wb") as out:
                while chunk := src.read(1 << 20):
                    out.write(chunk)
            os.chmod(target, 0o644)
    if len(tops) == 1 and (dest / next(iter(tops))).is_dir():
        return dest / next(iter(tops))
    return dest


def rel(path: str, root: Path) -> str:
    p = Path(path)
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.replace("\\", "/").lstrip("./")


# --------------------------------------------------------------- exécution
async def run(cmd: list[str], cwd: Path, timeout: float, env: dict | None = None) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=str(cwd), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        env={**_base_env(), **(env or {})})
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return proc.returncode, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


def _base_env() -> dict:
    keep = ("PATH", "HOME", "LANG", "COMPOSER_HOME", "COMPOSER_CACHE_DIR", "TMPDIR")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env.update(COMPOSER_NO_INTERACTION="1", COMPOSER_ALLOW_SUPERUSER="0", XDEBUG_MODE="off")
    return env


async def timed(name: str, coro, timeout: float) -> ToolResult:
    t0 = time.perf_counter()
    try:
        res = await asyncio.wait_for(coro, timeout)
    except asyncio.TimeoutError:
        res = ToolResult(name, "timeout", message=f"délai dépassé ({int(timeout)} s)")
    except Exception as e:  # noqa: BLE001 — un outil en panne n'arrête pas les autres
        res = ToolResult(name, "error", message=f"{type(e).__name__}: {e}"[:500])
    res.duration_ms = round((time.perf_counter() - t0) * 1000)
    if res.status == "ok" and res.findings:
        res.status = "findings"
    res.findings = res.findings[:MAX_FINDINGS_PER_TOOL]
    return res


# --------------------------------------------------------------- lecture des rapports
def parse_gitleaks(report: list[dict], root: Path, changed: dict[str, list[int] | None]) -> list[ToolFinding]:
    out = []
    for leak in report or []:
        path = rel(leak.get("File", ""), root)
        if path not in changed:
            continue
        line = leak.get("StartLine") or None
        added = changed[path]
        if added is not None and line is not None and line not in added:
            continue  # secret déjà présent avant la PR : pas imputé à cette PR
        rule = str(leak.get("RuleID", "secret"))
        # Jamais la valeur : ni Secret ni Match ne sont repris.
        out.append(ToolFinding(path, line, "critical", f"Secret détecté par gitleaks ({rule})",
                               str(leak.get("Description", ""))[:300], rule))
    return out


AUDIT_SEVERITY = {"critical": "critical", "high": "critical", "medium": "major", "low": "minor"}


def parse_composer_audit(report: dict) -> list[ToolFinding]:
    """Une remarque par paquet vulnérable (gravité la plus haute de ses avis), pas une par CVE."""
    advisories = report.get("advisories") or {}
    if isinstance(advisories, list):  # composer renvoie [] quand il n'y a rien
        advisories = {}
    rank = ["minor", "major", "critical"]
    out = []
    for package, items in advisories.items():
        items = list(items.values() if isinstance(items, dict) else items)
        if not items:
            continue
        sevs = [AUDIT_SEVERITY.get(str(a.get("severity") or "").lower(), "major") for a in items]
        worst = max(sevs, key=rank.index)
        ids = [str(a.get("cve") or a.get("advisoryId") or "?") for a in items]
        shown = ", ".join(ids[:6]) + (f" et {len(ids) - 6} autre(s)" if len(ids) > 6 else "")
        details = "; ".join(f"{a.get('cve') or a.get('advisoryId')}: {a.get('title', '')} ({a.get('affectedVersions', '?')})"
                            for a in items[:6])
        out.append(ToolFinding(
            "composer.lock", None, worst,
            f"Dépendance vulnérable : {package} ({len(items)} avis de sécurité)",
            f"Avis : {shown}. {details}"[:1500], ",".join(ids)[:200]))
    return out


def parse_phpstan(report: dict, root: Path, changed: dict[str, list[int] | None]) -> list[ToolFinding]:
    out = []
    for path, data in (report.get("files") or {}).items():
        path = rel(path, root)
        added = changed.get(path)
        if added is None:
            continue
        for msg in data.get("messages", []):
            line = msg.get("line")
            if line not in added:
                continue  # erreur sur une ligne existante : pas imputée à la PR
            tip = msg.get("tip") or ""
            out.append(ToolFinding(path, line, "major", f"PHPStan : {msg.get('message', '')}"[:200],
                                   tip[:600], str(msg.get("identifier") or "")))
    return out


HUNK_OLD_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@")


def lines_touched_by_fix(diff: str) -> set[int]:
    """Lignes du fichier actuel (côté « - » du diff de PHP-CS-Fixer) qu'un correctif modifierait."""
    touched, old = set(), 0
    for raw in diff.splitlines():
        m = HUNK_OLD_RE.match(raw)
        if m:
            old = int(m.group(1))
            continue
        if raw.startswith(("---", "+++")):
            continue
        if raw.startswith("-"):
            touched.add(old)
            old += 1
        elif raw.startswith(" "):
            old += 1
    return touched


def parse_cs_fixer(report: dict, root: Path, changed: dict[str, list[int] | None]) -> list[ToolFinding]:
    out = []
    for f in report.get("files") or []:
        path = rel(f.get("name", ""), root)
        added = changed.get(path)
        if not added:
            continue
        hits = sorted(lines_touched_by_fix(f.get("diff", "")) & set(added))
        if not hits:
            continue  # le style de l'existant n'est pas imputé à la PR
        fixers = ", ".join(f.get("appliedFixers", [])[:8])
        out.append(ToolFinding(path, hits[0], "minor",
                               f"Style non conforme ({len(hits)} ligne(s) ajoutée(s))",
                               f"Règles concernées : {fixers}. Lignes : {', '.join(map(str, hits[:15]))}.",
                               "php-cs-fixer"))
    return out


# --------------------------------------------------------------- outils
def strip_autoload_files(root: Path) -> None:
    """Retire autoload(-dev).files de composer.json : ces fichiers sont inclus dès le
    chargement de l'autoloader, ce serait exécuter du code de la PR."""
    cj = root / "composer.json"
    data = json.loads(cj.read_text(encoding="utf-8"))
    for key in ("autoload", "autoload-dev"):
        if isinstance(data.get(key), dict):
            data[key].pop("files", None)
    data.pop("scripts", None)
    cj.write_text(json.dumps(data, indent=2), encoding="utf-8")


async def gitleaks(root: Path, changed: dict, timeout: float) -> ToolResult:
    report = root.parent / "gitleaks.json"
    code, _, err = await run(["gitleaks", "dir", str(root), "--no-banner", "--redact", "--exit-code", "0",
                              "--log-level", "error", "--report-format", "json", "--report-path", str(report)],
                             root, timeout)
    if code != 0:
        return ToolResult("gitleaks", "error", message=err.strip()[-400:])
    data = json.loads(report.read_text(encoding="utf-8") or "[]") if report.exists() else []
    return ToolResult("gitleaks", "ok", findings=parse_gitleaks(data, root, changed))


async def composer_audit(root: Path, changed: dict, timeout: float) -> ToolResult:
    if not {"composer.json", "composer.lock"} & set(changed):
        return ToolResult("composer-audit", "skipped", message="dépendances inchangées par la PR")
    if not (root / "composer.lock").exists():
        return ToolResult("composer-audit", "skipped", message="pas de composer.lock")
    code, out, err = await run(["composer", "audit", "--locked", "--format=json", "--no-plugins",
                                "--no-scripts", "--abandoned=ignore"], root, timeout)
    if code not in (0, 1) and not out.strip().startswith("{"):  # 1 = vulnérabilités trouvées
        return ToolResult("composer-audit", "error", message=(err or out).strip()[-400:])
    return ToolResult("composer-audit", "ok", findings=parse_composer_audit(json.loads(out or "{}")))


async def composer_install(root: Path, timeout: float) -> str | None:
    """Installe les dépendances sans exécuter de code ; renvoie un message d'erreur ou None."""
    if not (root / "composer.json").exists():
        return "pas de composer.json"
    strip_autoload_files(root)
    code, out, err = await run(["composer", "install", "--no-scripts", "--no-plugins", "--no-progress",
                                "--prefer-dist", "--ignore-platform-reqs", "--no-interaction"], root, timeout)
    return None if code == 0 else (err or out).strip()[-400:]


async def phpstan(root: Path, php_files: list[str], changed: dict, level: int, timeout: float) -> ToolResult:
    report_cmd = [f"{TOOLS_BIN}/phpstan", "analyse", "--no-progress", "--error-format=json", "--no-interaction",
                  f"--level={level}", "--memory-limit=1G", f"--configuration={CONF / 'phpstan.neon'}",
                  f"--autoload-file={root / 'vendor' / 'autoload.php'}", "--", *php_files]
    code, out, err = await run(report_cmd, root, timeout)
    start = out.find("{")
    if start < 0:
        return ToolResult("phpstan", "error", message=(err or out).strip()[-400:])
    return ToolResult("phpstan", "ok", findings=parse_phpstan(json.loads(out[start:]), root, changed))


async def cs_fixer(root: Path, php_files: list[str], changed: dict, timeout: float) -> ToolResult:
    code, out, err = await run([f"{TOOLS_BIN}/php-cs-fixer", "fix", "--dry-run", "--diff", "--format=json",
                                "--using-cache=no", f"--config={CONF / 'cs.php'}", "-v",
                                "--show-progress=none", "--", *php_files], root, timeout,
                               env={"PHP_CS_FIXER_IGNORE_ENV": "1"})
    start = out.find("{")
    if code not in (0, 8) or start < 0:  # 8 = des fichiers seraient corrigés
        return ToolResult("php-cs-fixer", "error", message=(err or out).strip()[-400:])
    return ToolResult("php-cs-fixer", "ok", findings=parse_cs_fixer(json.loads(out[start:]), root, changed))
