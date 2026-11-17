"""Quelles pages photographier pour une PR ? (logique pure, testable sans navigateur)

1. Seuls les fichiers d'INTERFACE comptent (gabarits Twig, CSS/JS, traductions,
   contrôleurs, formulaires). Une PR qui n'en touche aucun n'a pas d'aperçu.
2. Chaque fichier modifié est relié aux routes qui l'affichent :
   - contrôleur  → ses actions (celles dont les lignes ont changé, sinon toutes) ;
   - gabarit     → les actions qui le rendent, directement ou via les gabarits qui
                   l'incluent / l'étendent (jusqu'à 3 niveaux) ;
   - formulaire  → les actions qui créent ce formulaire ;
   - mise en page générale, CSS, JS, traductions → pages « générales » du dépôt.
3. Les paramètres de route ({id}) sont remplis avec des valeurs connues
   (configuration du dépôt, sinon 1) ; seules les routes GET sont photographiées.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_UI_FILES = [
    "templates/**", "assets/**", "public/**/*.css", "public/**/*.js", "translations/**",
    "src/Controller/**", "src/Form/**", "src/Twig/**",
]
SKIP_ROUTE_WORDS = ("logout", "deconnexion", "_profiler", "_wdt", "_error")
TWIG_REF = re.compile(r"""(?:extends|include|embed|import|from|use|form_theme)\s*\(?\s*['"]([^'"]+\.twig)['"]""")
FUNC = re.compile(r"function\s+(\w+)\s*\(")
NAMESPACE = re.compile(r"^\s*namespace\s+([\w\\]+)\s*;", re.M)
CLASS = re.compile(r"^\s*(?:(?:abstract|final|readonly)\s+)*class\s+(\w+)", re.M)
PARAM = re.compile(r"\{(\w+)(?:<[^>]*>)?(?:\?[^}]*)?\}")
MAX_TEMPLATE_DEPTH = 3


@dataclass
class Page:
    path: str     # URL relative, paramètres remplis : /contrats/1
    route: str    # nom de la route Symfony (ou "" pour une page configurée)
    reason: str   # pourquoi cette page : « templates/contract/show.html.twig modifié »

    def to_dict(self) -> dict:
        return asdict(self)


def _glob_re(pattern: str) -> re.Pattern:
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"; i += 3
        elif pattern.startswith("**", i):
            out += ".*"; i += 2
        elif pattern[i] == "*":
            out += "[^/]*"; i += 1
        elif pattern[i] == "?":
            out += "[^/]"; i += 1
        else:
            out += re.escape(pattern[i]); i += 1
    return re.compile(out + r"\Z")


def ui_files(paths: list[str], patterns: list[str] | None = None) -> list[str]:
    """Fichiers d'interface parmi les fichiers modifiés."""
    regs = [_glob_re(p) for p in (patterns or DEFAULT_UI_FILES)]
    return [p for p in paths if any(r.match(p) for r in regs)]


# ------------------------------------------------------------------ routes

def parse_routes(router_json: dict) -> list[dict]:
    """Sortie de `bin/console debug:router --format=json` → [{name, path, methods, controller}]."""
    out = []
    for name, r in (router_json or {}).items():
        raw = r.get("method") or r.get("methods") or "ANY"
        methods = raw if isinstance(raw, list) else str(raw).split("|")
        out.append({"name": name, "path": r.get("path", ""), "methods": [m.upper() for m in methods if m],
                    "controller": str((r.get("defaults") or {}).get("_controller") or "")})
    return out


def _gettable(route: dict, skip: list[str]) -> bool:
    name = route["name"].lower()
    if route["name"] in skip or any(w in name for w in SKIP_ROUTE_WORDS) or name.startswith("_"):
        return False
    return not route["methods"] or "ANY" in route["methods"] or "GET" in route["methods"]


def fill(path: str, params: dict) -> str:
    return PARAM.sub(lambda m: str(params.get(m.group(1), "1")), path)


# ------------------------------------------------------------------ code PHP / Twig

def php_class(source: str) -> str:
    ns, cls = NAMESPACE.search(source), CLASS.search(source)
    if not cls:
        return ""
    return f"{ns.group(1)}\\{cls.group(1)}" if ns else cls.group(1)


def _header_start(lines: list[str], func_line: int) -> int:
    """Première ligne de l'en-tête d'une méthode : attributs (#[Route]), commentaires, lignes vides."""
    k = func_line - 1                      # index 0 de la ligne `function`
    while k > 0:
        prev = lines[k - 1].strip()
        if prev.startswith(("#[", "*", "/*", "//", "]", ")")) or prev.endswith(("]", ",")) or not prev:
            k -= 1
        else:
            break
    return k + 1


def _method_spans(source: str) -> list[tuple[str, int, int]]:
    """[(méthode, première ligne, dernière ligne)] ; une méthode commence à ses attributs
    (#[Route…]) et s'arrête juste avant l'en-tête de la suivante."""
    lines = source.splitlines()
    funcs = [(m.group(1), source.count("\n", 0, m.start()) + 1) for m in FUNC.finditer(source)]
    starts = [(name, _header_start(lines, line)) for name, line in funcs]
    total = len(lines)
    return [(name, start, starts[k + 1][1] - 1 if k + 1 < len(starts) else total)
            for k, (name, start) in enumerate(starts)]


def _method_at(source: str, offset: int) -> str | None:
    line = source.count("\n", 0, offset) + 1
    for name, start, end in _method_spans(source):
        if start <= line <= end:
            return name
    return None


def _controllers(root: Path) -> list[tuple[str, str]]:
    out = []
    for f in sorted((root / "src").rglob("*.php")) if (root / "src").is_dir() else []:
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "Route" in src or "Controller" in f.name:
            out.append((php_class(src), src))
    return out


def actions_using(root: Path, needle: str) -> list[tuple[str, str]]:
    """Actions (Classe, méthode) dont le corps contient `needle` (nom de gabarit, de formulaire…)."""
    found = []
    for cls, src in _controllers(root):
        for m in re.finditer(re.escape(needle), src):
            method = _method_at(src, m.start())
            if cls and method and (cls, method) not in found:
                found.append((cls, method))
    return found


def template_parents(root: Path, template: str) -> list[str]:
    """Gabarits qui incluent / étendent / importent `template`."""
    tdir = root / "templates"
    if not tdir.is_dir():
        return []
    out = []
    for f in sorted(tdir.rglob("*.twig")):
        try:
            refs = TWIG_REF.findall(f.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if template in refs:
            out.append(f.relative_to(tdir).as_posix())
    return out


def is_layout(root: Path, template: str) -> bool:
    """Un gabarit étendu par beaucoup d'autres (base.html.twig) touche toutes les pages."""
    tdir = root / "templates"
    if not tdir.is_dir():
        return template.startswith("base")
    users = 0
    for f in tdir.rglob("*.twig"):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        users += bool(re.search(r"extends\s*\(?\s*['\"]" + re.escape(template), text))
    return users >= 3 or template.startswith("base")


# ------------------------------------------------------------------ choix des pages

def choose_pages(root: Path, changed: dict[str, list[int] | None], routes: list[dict], cfg: dict) -> list[Page]:
    """Pages à photographier, les plus directement concernées d'abord (au plus cfg.max_pages)."""
    params = cfg.get("params") or {}
    skip = cfg.get("skip_routes") or []
    limit = int(cfg.get("max_pages") or 4)
    general = [str(p) for p in (cfg.get("global_pages") or [])]
    by_action: dict[tuple[str, str], list[dict]] = {}
    for r in routes:
        if "::" in r["controller"] and _gettable(r, skip):
            cls, method = r["controller"].split("::", 1)
            by_action.setdefault((cls, method), []).append(r)

    direct: list[Page] = []
    wants_general: list[str] = []

    def add_actions(actions: list[tuple[str, str]], reason: str) -> bool:
        hit = False
        for a in actions:
            for r in by_action.get(a, []):
                direct.append(Page(fill(r["path"], params), r["name"], reason))
                hit = True
        return hit

    for path in ui_files(list(changed), cfg.get("ui_files")):
        reason = f"{path} modifié"
        if path.startswith("templates/") and path.endswith(".twig"):
            tpl = path[len("templates/"):]
            if is_layout(root, tpl):
                wants_general.append(reason)
                continue
            seen, frontier, hit = {tpl}, [tpl], False
            for _ in range(MAX_TEMPLATE_DEPTH):
                nxt = []
                for t in frontier:
                    hit |= add_actions(actions_using(root, t), reason)
                    nxt += [p for p in template_parents(root, t) if p not in seen and not is_layout(root, p)]
                seen.update(nxt)
                frontier = nxt
                if hit or not frontier:
                    break
            if not hit:
                wants_general.append(reason)
        elif path.startswith("src/") and path.endswith(".php"):
            try:
                src = (root / path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            cls = php_class(src)
            if path.startswith("src/Form/"):
                if not add_actions(actions_using(root, cls.rsplit("\\", 1)[-1] + "::class"), reason):
                    wants_general.append(reason)
                continue
            lines = changed.get(path)
            if lines is None:   # diff inconnu : toutes les pages de ce contrôleur
                actions = [a for a in by_action if a[0] == cls]
            else:               # seulement les actions GET dont des lignes (non vides) ont changé
                text = src.splitlines()
                lines = [n for n in lines if 0 < n <= len(text) and text[n - 1].strip()]
                touched = [m for m, start, end in _method_spans(src) if any(start <= n <= end for n in lines)]
                actions = [(cls, m) for m in touched if (cls, m) in by_action]
            add_actions(actions, reason)   # rien de visible (action POST, service) : pas de page
        else:
            wants_general.append(reason)   # CSS, JS, traductions : visibles partout

    pages: list[Page] = []
    for p in direct + [Page(g, "", wants_general[0]) for g in general if wants_general]:
        if p.path not in {x.path for x in pages}:
            pages.append(p)
    return pages[:limit]
