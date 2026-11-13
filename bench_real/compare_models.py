"""Tableau comparatif des modèles à partir des résultats du banc.

    python bench_real/compare_models.py m14b:Qwen3-14B m30b:Qwen3-Coder-30B-A3B mnext:Qwen3-Coder-Next
Écrit bench_real/results/comparaison-modeles.md (et l'affiche).
"""
import json
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"


def pct(values, p):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    k = (len(values) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def secs(ms):
    return "—" if ms is None else f"{ms / 1000:.0f} s"


def load(tag):
    return json.loads((RESULTS / tag / "results.json").read_text(encoding="utf-8"))["results"]


def stats(rs):
    ai = [(r["id"], f) for r in rs for f in r["found"] if f.get("ai_expected")]
    det = [(r["id"], f) for r in rs for f in r["found"] if not f.get("ai_expected")]
    clean = [r for r in rs if r["kind"] == "clean"]
    llm_other = [(r, f) for r in rs for f in r["other_findings"] if (f.get("source") or "llm") == "llm"]
    cost = [r.get("cost_usd") for r in rs if r.get("cost_usd")]
    return {
        "n": len(rs),
        "verdicts": sum(r["verdict_ok"] for r in rs),
        "ai_total": len(ai), "ai_found": sum(1 for _, f in ai if "llm" in f.get("by", [])),
        "ai_missed": [cid for cid, f in ai if "llm" not in f.get("by", [])],
        "det_total": len(det), "det_found": sum(1 for _, f in det if f["found"]),
        "clean_total": len(clean), "clean_ok": sum(1 for r in clean if not r["noise_major"]),
        "clean_silent": sum(1 for r in clean if not r["kept"]),
        "other_llm": len(llm_other),
        "other_llm_major": sum(1 for _, f in llm_other if f["severity"] in ("major", "critical")),
        "run_p50": pct([r["run_ms"] for r in rs], .5), "run_p95": pct([r["run_ms"] for r in rs], .95),
        "chunks_failed": sum(r["chunks_failed"] or 0 for r in rs), "chunks": sum(r["chunks"] or 0 for r in rs),
        "cost": sum(cost) if cost else None,
        "errors": sum(1 for r in rs if r["status"] != "ok"),
    }


def main():
    models = [a.split(":", 1) for a in sys.argv[1:]]
    data = {tag: load(tag) for tag, _ in models}
    st = {tag: stats(rs) for tag, rs in data.items()}
    head = "| Indicateur | " + " | ".join(name for _, name in models) + " |"
    lines = ["# Comparaison des modèles — banc vrai GitHub (30 PR, code fictif)", "",
             head, "|---|" + "---|" * len(models)]

    def row(label, fn):
        lines.append(f"| {label} | " + " | ".join(fn(st[tag]) for tag, _ in models) + " |")

    row("Verdicts conformes", lambda s: f"**{s['verdicts']}/{s['n']}**")
    row("Défauts trouvés **par l'IA** (hors outils et CI)", lambda s: f"**{s['ai_found']}/{s['ai_total']}**")
    row("Défauts trouvés par les contrôles déterministes", lambda s: f"{s['det_found']}/{s['det_total']}")
    row("PR propres sans remarque majeure", lambda s: f"**{s['clean_ok']}/{s['clean_total']}**")
    row("PR propres sans aucune remarque", lambda s: f"{s['clean_silent']}/{s['clean_total']}")
    row("Autres remarques de l'IA (à juger)", lambda s: f"{s['other_llm']} (dont {s['other_llm_major']} majeures ou critiques)")
    row("Durée d'analyse p50 / p95", lambda s: f"{secs(s['run_p50'])} / {secs(s['run_p95'])}")
    row("Lots en échec (erreur du modèle)", lambda s: f"{s['chunks_failed']}/{s['chunks']}")
    row("Analyses en erreur", lambda s: str(s["errors"]))
    row("Coût (30 PR)", lambda s: "interne" if s["cost"] is None else f"{s['cost']:.3f} $")

    lines += ["", "## Défauts attendus de l'IA : détail", "",
              "| Cas | Défaut | " + " | ".join(name for _, name in models) + " |", "|---|---|" + "---|" * len(models)]
    first = data[models[0][0]]
    for r in first:
        for i, f in enumerate(r["found"]):
            if not f.get("ai_expected"):
                continue
            cells = []
            for tag, _ in models:
                other = next((x for x in data[tag] if x["id"] == r["id"]), None)
                g = other["found"][i] if other else None
                cells.append("—" if g is None else "✅" if "llm" in g.get("by", []) else
                             "⚠️ outil seul" if g["found"] else "❌")
            lines.append(f"| `{r['id']}` | {f['label']} | " + " | ".join(cells) + " |")

    lines += ["", "## Verdicts non conformes", ""]
    for tag, name in models:
        bad = [f"`{r['id']}` → {r['verdict'] or r['status']}" for r in data[tag] if not r["verdict_ok"]]
        lines.append(f"- **{name}** : " + (", ".join(bad) or "aucun"))

    lines += ["", "## Autres remarques de l'IA (hors défauts attendus)", ""]
    for tag, name in models:
        lines.append(f"### {name}")
        for r in data[tag]:
            for f in r["other_findings"]:
                if (f.get("source") or "llm") == "llm":
                    lines.append(f"- `{r['id']}` ({r['kind']}) **{f['severity']}** `{f['path']}:{f['line']}` — {f['title']}")
        lines.append("")
    out = "\n".join(lines) + "\n"
    (RESULTS / "comparaison-modeles.md").write_text(out, encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
