"""Compétences de revue (« skills ») et relecteurs spécialisés.

Une compétence est un fichier Markdown de `skills/` avec un court en-tête :

    ---
    name: symfony
    reviewer: code                 # relecteur qui l'utilise
    applies: src/*.php, *.yaml     # fichiers concernés (motifs fnmatch)
    ---
    Fiche courte : ce qu'il faut signaler, et ce qu'il ne faut PAS signaler.

Chaque lot du diff est relu par chaque relecteur concerné, avec SEULEMENT les
compétences qui s'appliquent aux fichiers du lot : la fenêtre du modèle est
petite (8 192 jetons pour le Qwen3 de Calipso), un prompt unique avec toutes
les fiches ne tiendrait pas.
"""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Skill:
    name: str
    reviewer: str
    applies: tuple[str, ...]
    text: str

    def matches(self, path: str) -> bool:
        name = path.rsplit("/", 1)[-1]
        return any(fnmatch.fnmatch(path, p) or fnmatch.fnmatch(name, p) for p in self.applies)


@dataclass(frozen=True)
class Reviewer:
    name: str
    label: str
    focus: str
    always: bool   # True : relit chaque lot même sans compétence applicable


REVIEWERS: dict[str, Reviewer] = {
    "securite": Reviewer(
        "securite", "Sécurité",
        "Tu es le relecteur SÉCURITÉ. Ne signale que des failles de sécurité (catégorie « security ») : "
        "ignore le style, la qualité, les tests et les bogues sans impact de sécurité, d'autres relecteurs "
        "s'en chargent.",
        always=False),
    "code": Reviewer(
        "code", "Code & Symfony",
        "Tu es le relecteur CODE (bogues, bonnes pratiques Symfony / Doctrine / Twig, tests). Ne signale PAS "
        "les failles de sécurité (injection, XSS, droits d'accès, CSRF, redirection, désérialisation) : "
        "un relecteur sécurité dédié s'en charge.",
        always=True),
}


def parse_skill(text: str, default_name: str) -> Skill | None:
    if not text.startswith("---"):
        return None
    try:
        _, header, body = text.split("---", 2)
    except ValueError:
        return None
    meta = {}
    for line in header.strip().splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip()
    reviewer = meta.get("reviewer", "")
    if reviewer not in REVIEWERS:
        return None
    applies = tuple(p.strip() for p in meta.get("applies", "*").split(",") if p.strip())
    return Skill(meta.get("name", default_name), reviewer, applies, body.strip())


def load_skills(directory: str) -> list[Skill]:
    root = Path(directory)
    if not root.is_dir():
        return []
    skills = []
    for path in sorted(root.glob("*.md")):
        skill = parse_skill(path.read_text(encoding="utf-8"), path.stem)
        if skill:
            skills.append(skill)
    return skills


def plan(paths: list[str], skills: list[Skill], enabled: list[str]) -> list[tuple[Reviewer, list[Skill]]]:
    """Relecteurs à lancer sur un lot donné, avec leurs compétences applicables."""
    out = []
    for name in enabled:
        reviewer = REVIEWERS.get(name)
        if reviewer is None:
            continue
        mine = [s for s in skills if s.reviewer == name and any(s.matches(p) for p in paths)]
        if mine or reviewer.always:
            out.append((reviewer, mine))
    return out


def skills_text(skills: list[Skill]) -> str:
    return "\n\n".join(f"### Compétence : {s.name}\n{s.text}" for s in skills)
