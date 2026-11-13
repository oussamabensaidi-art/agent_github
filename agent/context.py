"""Contexte donné au modèle en plus du diff (lecture seule).

1. Règles propres au dépôt : `.github/pr-review.md`, lu sur la branche de BASE
   (jamais sur celle de la PR : une PR ne peut pas modifier les règles de sa
   propre revue).
2. En-tête des fichiers PHP modifiés (namespace, imports, attributs et
   déclaration de la classe) : le diff seul ne montre pas, par exemple, un
   `#[IsGranted]` posé sur la classe, d'où des fausses alertes « route non protégée ».

Tout est masqué (secrets) avant d'être envoyé au modèle. Un échec de lecture
n'arrête jamais la revue : le contexte est simplement absent.
"""
from __future__ import annotations

import re

from agent.secrets_scan import redact_text

CLASS_RE = re.compile(r"^\s*(?:(?:abstract|final|readonly)\s+)*(?:class|interface|trait|enum)\s+\w+")
HEADER_MAX_LINES = 80


def file_header(source: str, max_chars: int = 1200) -> str:
    """Du début du fichier jusqu'à la déclaration de la classe (incluse), sans lignes vides
    ni commentaires. Chaîne vide si aucune classe n'est déclarée dans les premières lignes."""
    kept: list[str] = []
    in_block_comment = False
    for raw in source.splitlines()[:HEADER_MAX_LINES]:
        line = raw.rstrip()
        stripped = line.strip()
        if in_block_comment:
            in_block_comment = "*/" not in stripped
            continue
        if stripped.startswith("/*"):
            in_block_comment = "*/" not in stripped
            continue
        if not stripped or stripped.startswith(("//", "#!")) or stripped == "<?php":
            continue
        kept.append(line)
        if CLASS_RE.match(line):
            text = "\n".join(kept)
            if len(text) > max_chars:   # trop d'imports : on garde la fin (attributs + classe)
                text = "…\n" + text[-max_chars:].split("\n", 1)[-1]
            return redact_text(text)[0]
    return ""


def context_for_chunk(paths: list[str], headers: dict[str, str], max_chars: int) -> str:
    parts: list[str] = []
    total = 0
    for path in paths:
        header = headers.get(path)
        if not header:
            continue
        block = f"### {path} — début du fichier (existant, non modifié)\n{header}"
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts)


def clean_repo_rules(text: str, max_chars: int) -> str:
    text = redact_text((text or "").strip())[0]
    return text[:max_chars] + ("\n… (tronqué)" if len(text) > max_chars else "")
