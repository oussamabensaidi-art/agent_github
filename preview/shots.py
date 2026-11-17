"""Lancer l'application d'un dépôt, s'y connecter, photographier des pages, comparer.

Tout tourne dans le conteneur « preview » (isolé, sans secret). Le navigateur ne
peut joindre que l'application locale : toute autre requête est bloquée.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import shutil
import socket
import time
from pathlib import Path
from urllib.parse import urlparse

from checker.tools import run

VIEWPORT = {"width": 1280, "height": 800}
MAX_TEXT = 20000           # texte visible gardé par page (pour dire CE QUI a changé)
MAX_HEIGHT = 2400         # pages très longues : coupées (le haut suffit pour comparer)
DIFF_THRESHOLD = 6         # écart (0-255, canal le plus touché) en dessous duquel un pixel est identique ; même navigateur des deux côtés : pas de bruit
NO_ANIM = "*,*::before,*::after{transition:none!important;animation:none!important;caret-color:transparent!important}"


# ------------------------------------------------------------------ installation

async def install(root: Path, cfg: dict, timeout: float) -> str | None:
    """composer install puis commandes de préparation du dépôt (ex. chargement des données).
    Renvoie un message d'erreur ou None. Seules des commandes `php …` sont acceptées."""
    if (root / "composer.json").exists() and not (root / "vendor" / "autoload.php").exists():
        code, out, err = await run(["composer", "install", "--no-interaction", "--no-progress", "--prefer-dist",
                                    "--no-scripts", "--ignore-platform-reqs"], root, timeout)
        if code != 0:
            return "composer install : " + (err or out).strip()[-300:]
    for cmd in cfg.get("setup") or []:
        if not isinstance(cmd, list) or not cmd or cmd[0] != "php":
            return f"commande de préparation refusée (seul « php … » est accepté) : {cmd!r}"[:300]
        code, out, err = await run([str(c) for c in cmd], root, timeout, env=app_env(cfg))
        if code != 0:
            return f"{' '.join(map(str, cmd))} : " + (err or out).strip()[-300:]
    return None


def same_dependencies(a: Path, b: Path) -> bool:
    la, lb = a / "composer.lock", b / "composer.lock"
    return la.is_file() and lb.is_file() and la.read_bytes() == lb.read_bytes()


def copy_vendor(src: Path, dst: Path) -> None:
    """Même composer.lock des deux côtés : on recopie vendor/ au lieu de réinstaller."""
    if (src / "vendor").is_dir() and not (dst / "vendor").exists():
        shutil.copytree(src / "vendor", dst / "vendor", symlinks=True)


def app_env(cfg: dict) -> dict:
    env = {"APP_ENV": "dev", "APP_DEBUG": "1"}
    env.update({str(k): str(v) for k, v in (cfg.get("env") or {}).items()})
    return env


async def routes(root: Path, cfg: dict, timeout: float) -> dict:
    code, out, err = await run(["php", "bin/console", "debug:router", "--format=json"], root, timeout,
                               env=app_env(cfg))
    if code != 0:
        raise RuntimeError("liste des routes illisible : " + (err or out).strip()[-200:])
    return json.loads(out[out.find("{"):])


# ------------------------------------------------------------------ serveur

ROUTER = """<?php
$docroot = '__DOCROOT__';
$path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH) ?: '/';
if ($path !== '/' && is_file($docroot . $path)) {
    return false;
}
$_SERVER['SCRIPT_FILENAME'] = $docroot . '/index.php';
$_SERVER['SCRIPT_NAME'] = '/index.php';
$_SERVER['PHP_SELF'] = '/index.php';
require $docroot . '/index.php';
"""

def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class AppServer:
    """`php -S` sur le dossier public du dépôt, le temps des captures."""

    def __init__(self, root: Path, cfg: dict):
        self.root, self.cfg = root, cfg
        self.port = free_port()
        self.proc: asyncio.subprocess.Process | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    async def __aenter__(self) -> "AppServer":
        docroot = self.root / str(self.cfg.get("docroot") or "public")
        env = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "/tmp"), **app_env(self.cfg)}
        # Routeur : un vrai fichier est servi tel quel, tout le reste va au contrôleur frontal
        # (sans lui, `php -S` répond 404 à toute URL avec extension, ex. /totaux.json).
        router = self.root.parent / f"router-{self.root.name}.php"
        router.write_text(ROUTER.replace("__DOCROOT__", str(docroot)), encoding="utf-8")
        self.proc = await asyncio.create_subprocess_exec(
            "php", "-S", f"127.0.0.1:{self.port}", "-t", str(docroot), str(router), cwd=str(self.root), env=env,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                _, w = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", self.port), 1)
                w.close()
                return self
            except (OSError, asyncio.TimeoutError):
                await asyncio.sleep(0.3)
        raise RuntimeError("l'application ne démarre pas")

    async def __aexit__(self, *exc) -> None:
        if self.proc and self.proc.returncode is None:
            self.proc.kill()
            await self.proc.wait()


# ------------------------------------------------------------------ captures

async def capture(browser, base_url: str, paths: list[str], login: dict | None, timeout_ms: int = 20000) -> list[dict]:
    """Une capture par page : {status, final_path, png | None, error}."""
    ctx = await browser.new_context(viewport=VIEWPORT, device_scale_factor=1, locale="fr-FR",
                                    timezone_id="Europe/Paris", reduced_motion="reduce")
    local = urlparse(base_url).netloc

    async def only_local(route):
        if urlparse(route.request.url).netloc == local:
            await route.continue_()
        else:
            await route.abort()

    await ctx.route("**/*", only_local)
    page = await ctx.new_page()
    out = []
    try:
        if login:
            await page.goto(base_url + login["path"], wait_until="networkidle", timeout=timeout_ms)
            await page.fill(login.get("username_selector", "#username"), str(login["username"]))
            await page.fill(login.get("password_selector", "#password"), str(login["password"]))
            async with page.expect_navigation(wait_until="networkidle", timeout=timeout_ms):
                await page.click(login.get("submit_selector", "button[type=submit]"))
        for path in paths:
            try:
                resp = await page.goto(base_url + path, wait_until="networkidle", timeout=timeout_ms)
                await page.add_style_tag(content=NO_ANIM)
                png = await page.screenshot(full_page=True, animations="disabled")
                try:
                    text = (await page.inner_text("body", timeout=5000))[:MAX_TEXT]
                except Exception:  # noqa: BLE001 — page sans <body> lisible (JSON brut…)
                    text = ""
                out.append({"status": resp.status if resp else None, "text": text,
                            "final_path": urlparse(page.url).path, "png": crop(png), "error": ""})
            except Exception as e:  # noqa: BLE001 — une page en échec n'arrête pas les autres
                out.append({"status": None, "final_path": "", "png": None, "text": "",
                            "error": f"{type(e).__name__}: {e}"[:200]})
    finally:
        await ctx.close()
    return out


def crop(png: bytes) -> bytes:
    from PIL import Image
    img = Image.open(io.BytesIO(png))
    if img.height <= MAX_HEIGHT:
        return png
    buf = io.BytesIO()
    img.crop((0, 0, img.width, MAX_HEIGHT)).save(buf, "PNG", optimize=True)
    return buf.getvalue()


def compare(before: bytes, after: bytes) -> tuple[float, bytes, list[tuple[int, int, int, int]], int]:
    """Part des pixels changés (en %), image « après » avec les zones changées encadrées,
    les zones elles-mêmes et la hauteur de la page."""
    from PIL import Image, ImageChops
    a = Image.open(io.BytesIO(before)).convert("RGB")
    b = Image.open(io.BytesIO(after)).convert("RGB")
    w, h = max(a.width, b.width), max(a.height, b.height)
    pa, pb = Image.new("RGB", (w, h), "white"), Image.new("RGB", (w, h), "white")
    pa.paste(a)
    pb.paste(b)
    r, g, bl = ImageChops.difference(pa, pb).split()
    mask = ImageChops.lighter(ImageChops.lighter(r, g), bl).point(lambda v: 255 if v > DIFF_THRESHOLD else 0)
    changed = mask.histogram()[255]
    pct = round(changed * 100 / (w * h), 2)
    if changed and pct == 0:
        pct = 0.01   # quelques pixels : jamais « aucun changement »
    zones = change_zones(mask) if changed else []
    buf = io.BytesIO()
    highlight(pb, zones).save(buf, "PNG", optimize=True)
    return pct, buf.getvalue(), zones, h


CELL = 12          # taille des cases (px) pour regrouper les pixels changés en zones
ZONE_PAD = 6


def change_zones(mask) -> list[tuple[int, int, int, int]]:
    """Pixels changés → quelques rectangles lisibles (cases voisines regroupées)."""
    from PIL import Image, ImageFilter
    gw, gh = max(1, -(-mask.width // CELL)), max(1, -(-mask.height // CELL))
    grid = mask.resize((gw, gh), Image.BOX).point(lambda v: 255 if v else 0).filter(ImageFilter.MaxFilter(3))
    px, seen, zones = grid.load(), set(), []
    for y in range(gh):
        for x in range(gw):
            if not px[x, y] or (x, y) in seen:
                continue
            stack, x0, y0, x1, y1 = [(x, y)], x, y, x, y
            seen.add((x, y))
            while stack:
                cx, cy = stack.pop()
                x0, y0, x1, y1 = min(x0, cx), min(y0, cy), max(x1, cx), max(y1, cy)
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < gw and 0 <= ny < gh and px[nx, ny] and (nx, ny) not in seen:
                        seen.add((nx, ny))
                        stack.append((nx, ny))
            zones.append((max(0, x0 * CELL - ZONE_PAD), max(0, y0 * CELL - ZONE_PAD),
                          min(mask.width, (x1 + 1) * CELL + ZONE_PAD), min(mask.height, (y1 + 1) * CELL + ZONE_PAD)))
    return zones


def highlight(img, zones):
    """Image « après » intacte, zones changées en rouge clair encadrées de rouge."""
    from PIL import Image, ImageDraw
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for box in zones:
        draw.rectangle(box, fill=(220, 38, 38, 38), outline=(220, 38, 38, 255), width=2)
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")
