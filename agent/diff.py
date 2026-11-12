"""Diff GitHub : parsing des patchs, filtrage des fichiers, découpage en lots.

GitHub renvoie, par fichier, un `patch` au format unifié (hunks `@@`). On en
tire les numéros de ligne côté nouveau fichier : ce sont les seules lignes
sur lesquelles un commentaire inline est accepté par l'API (side=RIGHT).
"""
import fnmatch
import re
from dataclasses import dataclass, field

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass
class DiffLine:
    kind: str            # "+", "-", " " ou "@" (en-tête de hunk)
    new_line: int | None  # numéro dans le nouveau fichier (None pour "-" et "@")
    text: str


@dataclass
class FileDiff:
    path: str
    status: str          # added | modified | renamed | removed | ...
    patch: str
    additions: int = 0
    deletions: int = 0
    lines: list[DiffLine] = field(default_factory=list)

    @property
    def changed_lines(self) -> int:
        return self.additions + self.deletions

    @property
    def commentable(self) -> set[int]:
        return {l.new_line for l in self.lines if l.new_line is not None}

    @property
    def added(self) -> dict[int, str]:
        return {l.new_line: l.text for l in self.lines if l.kind == "+" and l.new_line is not None}

    def reparse(self) -> None:
        self.lines = parse_patch(self.patch)


def parse_patch(patch: str) -> list[DiffLine]:
    out: list[DiffLine] = []
    new_no = 0
    for raw in patch.splitlines():
        m = HUNK_RE.match(raw)
        if m:
            new_no = int(m.group(3))
            out.append(DiffLine("@", None, raw))
            continue
        if raw.startswith("\\"):  # "\ No newline at end of file"
            continue
        kind, text = (raw[:1] or " "), raw[1:]
        if kind == "+":
            out.append(DiffLine("+", new_no, text))
            new_no += 1
        elif kind == "-":
            out.append(DiffLine("-", None, text))
        else:
            out.append(DiffLine(" ", new_no, text))
            new_no += 1
    return out


def file_from_github(item: dict) -> FileDiff:
    fd = FileDiff(
        path=item["filename"],
        status=item.get("status", "modified"),
        patch=item.get("patch") or "",
        additions=item.get("additions", 0),
        deletions=item.get("deletions", 0),
    )
    fd.reparse()
    return fd


def is_ignored(path: str, patterns: list[str]) -> bool:
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(path, p) or fnmatch.fnmatch(name, p) for p in patterns)


def filter_files(
    files: list[FileDiff],
    patterns: list[str],
    max_files: int,
    max_file_lines: int,
    max_total_lines: int,
) -> tuple[list[FileDiff], list[tuple[str, str]]]:
    """Renvoie (fichiers à analyser, [(fichier ignoré, raison)]).

    Raisons "exclu" (lock, généré, supprimé, binaire) : normales, sans impact
    sur le verdict. Raisons "trop volumineux" / "limite" : la revue est
    incomplète, le verdict ne peut pas être "prête".
    """
    kept: list[FileDiff] = []
    skipped: list[tuple[str, str]] = []
    total = 0
    for f in files:
        if is_ignored(f.path, patterns):
            skipped.append((f.path, "exclu (lock / généré)"))
        elif f.status == "removed":
            skipped.append((f.path, "exclu (fichier supprimé)"))
        elif not f.patch and f.changed_lines > 0:
            # GitHub omet le patch des diffs texte trop volumineux : ce fichier a
            # changé mais n'a pas été relu → incomplet, jamais « exclu ».
            skipped.append((f.path, f"diff non fourni par GitHub ({f.changed_lines} lignes modifiées)"))
        elif not f.patch:
            skipped.append((f.path, "exclu (binaire ou sans diff)"))
        elif f.changed_lines > max_file_lines:
            skipped.append((f.path, f"trop volumineux ({f.changed_lines} lignes)"))
        elif len(kept) >= max_files or total + f.changed_lines > max_total_lines:
            skipped.append((f.path, "limite de taille de la PR atteinte"))
        else:
            kept.append(f)
            total += f.changed_lines
    return kept, skipped


def is_incomplete_reason(reason: str) -> bool:
    return not reason.startswith("exclu")


def render_for_llm(f: FileDiff, lines: list[DiffLine] | None = None) -> str:
    """Diff annoté avec les numéros de ligne du nouveau fichier.

    Le modèle cite ces numéros dans ses remarques : c'est beaucoup plus fiable
    que de lui faire recompter les lignes depuis les en-têtes de hunk.
    """
    rows = [f"### {f.path} ({f.status})"]
    for l in lines if lines is not None else f.lines:
        if l.kind == "@":
            rows.append(l.text)
        elif l.kind == "-":
            rows.append(f"{'':>5} - {l.text}")
        else:
            rows.append(f"{l.new_line:>5} {l.kind} {l.text}")
    return "\n".join(rows)


def _hunks(lines: list[DiffLine]) -> list[list[DiffLine]]:
    hunks: list[list[DiffLine]] = []
    for l in lines:
        if l.kind == "@" or not hunks:
            hunks.append([])
        hunks[-1].append(l)
    return hunks


def build_chunks(files: list[FileDiff], max_chars: int) -> list[str]:
    """Regroupe les diffs en lots de taille bornée pour le contexte du modèle.

    Un fichier trop gros pour un lot est découpé par hunks.
    """
    pieces: list[str] = []
    for f in files:
        whole = render_for_llm(f)
        if len(whole) <= max_chars:
            pieces.append(whole)
            continue
        current: list[DiffLine] = []
        for hunk in _hunks(f.lines):
            if current and len(render_for_llm(f, current + hunk)) > max_chars:
                pieces.append(render_for_llm(f, current))
                current = []
            current += hunk
        if current:
            pieces.append(render_for_llm(f, current))

    chunks: list[str] = []
    buf = ""
    for p in pieces:
        if buf and len(buf) + len(p) + 2 > max_chars:
            chunks.append(buf)
            buf = ""
        buf = f"{buf}\n\n{p}" if buf else p
    if buf:
        chunks.append(buf)
    return chunks


def excerpt(f: FileDiff, line: int | None, radius: int = 3) -> list[dict]:
    """Lignes du diff (déjà masqué) autour de `line`, pour l'interface de suivi."""
    if line is None:
        return []
    idx = next((i for i, l in enumerate(f.lines) if l.new_line == line), None)
    if idx is None:
        return []
    out = []
    for l in f.lines[max(0, idx - radius): idx + radius + 1]:
        if l.kind == "@":
            continue
        out.append({"n": l.new_line, "kind": l.kind, "text": l.text[:300], "target": l.new_line == line})
    return out
