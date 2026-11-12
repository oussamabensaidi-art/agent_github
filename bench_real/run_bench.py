"""Banc « vrai GitHub » : ouvre de vraies PR sur les dépôts de test, en même temps,
attend les analyses de l'agent et note les résultats.

    python bench_real/run_bench.py prepare --tag r1   # branches + commits locaux (rien n'est poussé)
    python bench_real/run_bench.py launch  --tag r1   # pousse puis ouvre toutes les PR en parallèle
    python bench_real/run_bench.py collect --tag r1   # attend les analyses, note, écrit le rapport

Prérequis : `gh` connecté, la pile lancée avec docker-compose.github.yml.
Rapport : bench_real/results/<tag>/report.md + results.json.
"""
import argparse
import json
import re
import statistics
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cases import CASES  # noqa: E402

ROOT = Path(__file__).resolve().parent
AGENT = ROOT.parent
WORK = ROOT / ".work"
RESULTS = ROOT / "results"
APP_SLUG = "calipso-revue-pr-test"
COMPOSE = ["docker", "compose", "-f", "docker-compose.yml", "-f", "docker-compose.github.yml"]
SEVERITY_RANK = {"info": 0, "minor": 1, "major": 2, "critical": 3}
CONCLUSION = {"BLOQUANTE": "failure", "A_VERIFIER": "neutral", "CONTROLES_SATISFAITS": "success",
              "ANALYSE_INCOMPLETE": "action_required"}
# Valeurs secrètes des cas : ne doivent JAMAIS apparaître dans le journal de l'agent.
SECRET_VALUES = ["crm_live_9f8a7c6d5e4b3a2f1e0d4c5b", "Rct-2026!crm#9f8a7c"]


def sh(cmd: list[str], cwd: Path | None = None, check: bool = True, input_: str | None = None) -> str:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", input=input_)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} → {r.returncode}\n{r.stderr.strip()}")
    return r.stdout.strip()


def clone(repo: str) -> Path:
    path = WORK / repo.split("/")[1]
    if not path.exists():
        WORK.mkdir(parents=True, exist_ok=True)
        sh(["gh", "repo", "clone", repo, str(path), "--", "-q"])
    sh(["git", "fetch", "-q", "origin"], cwd=path)
    sh(["git", "checkout", "-q", "-B", "main", "origin/main"], cwd=path)
    return path


def branch_name(tag: str, case: dict) -> str:
    return f"bench/{tag}/{case['id']}"


def state_file(tag: str) -> Path:
    return RESULTS / tag / "state.json"


def load_state(tag: str) -> dict:
    p = state_file(tag)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"tag": tag, "cases": {}}


def save_state(state: dict) -> None:
    p = state_file(state["tag"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# --------------------------------------------------------------------- prepare
def apply_changes(path: Path, changes: list[tuple]) -> None:
    for change in changes:
        if change[0] == "edit":
            _, rel, old, new = change
            f = path / rel
            text = f.read_text(encoding="utf-8")
            if text.count(old) != 1:
                raise RuntimeError(f"{rel} : extrait introuvable ou ambigu ({text.count(old)}) : {old[:70]!r}")
            f.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
        elif change[0] == "new":
            _, rel, content = change
            f = path / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(content, encoding="utf-8", newline="\n")
        else:
            raise ValueError(change[0])


def prepare(tag: str, only: list[str] | None) -> None:
    state = load_state(tag)
    for case in CASES:
        if only and case["id"] not in only:
            continue
        path = clone(case["repo"])
        br = branch_name(tag, case)
        sh(["git", "checkout", "-q", "-B", br, "origin/main"], cwd=path)
        apply_changes(path, case["changes"])
        sh(["git", "add", "-A"], cwd=path)
        sh(["git", "-c", "core.autocrlf=false", "commit", "-q", "-m", case["title"]], cwd=path)
        sha = sh(["git", "rev-parse", "HEAD"], cwd=path)
        state["cases"][case["id"]] = {"repo": case["repo"], "branch": br, "sha": sha}
        print(f"  préparé {case['id']:<24} {case['repo']}  {br}  {sha[:7]}")
        sh(["git", "checkout", "-q", "main"], cwd=path)
    save_state(state)


# ---------------------------------------------------------------------- launch
def launch(tag: str, only: list[str] | None) -> None:
    state = load_state(tag)
    todo = [c for c in CASES if c["id"] in state["cases"] and (not only or c["id"] in only)
            and "pr" not in state["cases"][c["id"]]]
    # 1) pousser toutes les branches (sans PR, aucun webhook « pull_request »)
    for repo in sorted({c["repo"] for c in todo}):
        path = WORK / repo.split("/")[1]
        refs = [f"{branch_name(tag, c)}:{branch_name(tag, c)}" for c in todo if c["repo"] == repo]
        sh(["git", "push", "-q", "-f", "origin", *refs], cwd=path)
        print(f"  poussé {len(refs)} branche(s) vers {repo}")

    # 2) ouvrir toutes les PR en même temps
    def open_pr(case: dict) -> tuple[str, int, float, str]:
        body = case["body"] + f"\n\n_Banc agent de revue · cas `{case['id']}` · série `{tag}`_"
        url = sh(["gh", "pr", "create", "--repo", case["repo"], "--base", "main",
                  "--head", branch_name(tag, case), "--title", case["title"], "--body-file", "-"], input_=body)
        return case["id"], int(url.rstrip("/").rsplit("/", 1)[1]), time.time(), url

    started = time.time()
    with ThreadPoolExecutor(max_workers=len(todo) or 1) as pool:
        for cid, number, opened_at, url in pool.map(open_pr, todo):
            state["cases"][cid].update(pr=number, opened_at=opened_at, url=url)
            print(f"  PR ouverte {cid:<24} {url}")
    state["launched_at"] = started
    state["launch_spread_s"] = round(time.time() - started, 1)
    save_state(state)
    print(f"{len(todo)} PR ouvertes en {state['launch_spread_s']} s")


# --------------------------------------------------------------------- collect
def psql_json(sql: str):
    out = sh([*COMPOSE, "exec", "-T", "db", "psql", "-U", "prreview", "-d", "prreview", "-At", "-c",
              f"select coalesce(json_agg(t), '[]') from ({sql}) t"], cwd=AGENT)
    return json.loads(out or "[]")


def q(v: str) -> str:
    return "'" + v.replace("'", "''") + "'"


def wait_runs(state: dict, timeout_s: int) -> dict[str, dict]:
    deadline = time.time() + timeout_s
    while True:
        runs = {}
        for cid, c in state["cases"].items():
            rows = psql_json(f"select * from runs where repo={q(c['repo'])} and pr_number={c['pr']} "
                             f"and head_sha={q(c['sha'])} order by queued_at desc limit 1")
            if rows:
                runs[cid] = rows[0]
        done = [r for r in runs.values() if r["status"] not in ("queued", "running")]
        print(f"  {time.strftime('%H:%M:%S')} analyses terminées : {len(done)}/{len(state['cases'])}", flush=True)
        if len(done) == len(state["cases"]) or time.time() > deadline:
            return runs
        time.sleep(15)


def gh_json(path: str):
    return json.loads(sh(["gh", "api", path]) or "null")


def mails() -> list[dict]:
    try:
        with urllib.request.urlopen("http://localhost:8025/api/v1/messages?limit=500", timeout=10) as r:
            return json.load(r).get("messages", [])
    except OSError:
        return []


def matches(expected: dict, f: dict) -> bool:
    if f["path"] != expected["path"] or SEVERITY_RANK.get(f["severity"], 0) < SEVERITY_RANK[expected["min"]]:
        return False
    if "source" in expected:
        return f.get("source") == expected["source"]
    text = f"{f['title']} {f['explanation']} {f.get('category') or ''} {f.get('suggestion') or ''}".lower()
    return any(k.lower() in text for k in expected["kw"])


def score(case: dict, run: dict | None, findings: list[dict], check: dict | None,
          review: dict | None, inline: int, mailed: bool) -> dict:
    exp = case["expect"]
    verdict = run.get("verdict") if run else None
    kept = [f for f in findings if f["kept"]]
    found = [{"label": e["label"], "found": any(matches(e, f) for f in kept)} for e in exp["find"]]
    expected_ids = {id(f) for e in exp["find"] for f in kept if matches(e, f)}
    other = [f for f in kept if id(f) not in expected_ids]
    return {
        "id": case["id"], "repo": case["repo"], "kind": case["kind"], "pr": None,
        "status": run.get("status") if run else "absent",
        "verdict": verdict, "verdict_ok": verdict in exp["verdicts"], "expected_verdicts": exp["verdicts"],
        "found": found,
        "kept": [{k: f[k] for k in ("severity", "path", "line", "title", "source")} for f in kept],
        "other_findings": [{k: f[k] for k in ("severity", "path", "line", "title")} for f in other],
        "noise_major": sum(1 for f in other if SEVERITY_RANK.get(f["severity"], 0) >= 2),
        "dropped": sum(1 for f in findings if not f["kept"]),
        "check": check and {"conclusion": check["conclusion"], "title": check["output"]["title"],
                            "details_url": check.get("details_url")},
        "check_ok": bool(check) and verdict in CONCLUSION and check["conclusion"] == CONCLUSION[verdict],
        "review_state": review and review["state"], "inline_comments": inline,
        "mail_sent": mailed, "mail_ok": mailed == (verdict == "BLOQUANTE"),
        "queue_ms": run and run.get("queue_ms"), "run_ms": run and run.get("run_ms"),
        "total_ms": run and run.get("total_ms"),
        "chunks": run and run.get("chunks_total"), "chunks_failed": run and run.get("chunks_failed"),
        "incomplete_reasons": run and run.get("incomplete_reasons"), "error": run and run.get("error"),
    }


def pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    k = (len(values) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def secs(ms) -> str:
    return "—" if ms is None else f"{ms / 1000:.1f} s"


def collect(tag: str, timeout_s: int) -> None:
    state = load_state(tag)
    runs = wait_runs(state, timeout_s)
    inbox = mails()
    results = []
    for case in CASES:
        c = state["cases"].get(case["id"])
        if not c or "pr" not in c:
            continue
        run = runs.get(case["id"])
        findings = psql_json(f"select * from findings where run_id={q(run['id'])} order by id") if run else []
        checks = gh_json(f"repos/{c['repo']}/commits/{c['sha']}/check-runs")["check_runs"]
        check = next((x for x in checks if x["app"]["slug"] == APP_SLUG), None)
        reviews = [r for r in gh_json(f"repos/{c['repo']}/pulls/{c['pr']}/reviews")
                   if r["user"]["login"] == f"{APP_SLUG}[bot]" and r["commit_id"] == c["sha"]]
        comments = [x for x in gh_json(f"repos/{c['repo']}/pulls/{c['pr']}/comments?per_page=100")
                    if x["user"]["login"] == f"{APP_SLUG}[bot]" and x["commit_id"] == c["sha"]]
        mailed = any(f"{c['repo']}#{c['pr']} " in (m.get("Subject") or "") for m in inbox)
        r = score(case, run, findings, check, reviews[-1] if reviews else None, len(comments), mailed)
        r.update(pr=c["pr"], url=c["url"], sha=c["sha"][:7])
        results.append(r)

    # Aucun secret des cas dans le journal (événements + remarques).
    leaks = {}
    for value in SECRET_VALUES:
        n = psql_json(f"select 1 from events where data::text like {q('%' + value + '%')} union all "
                      f"select 1 from findings where (explanation || title || coalesce(excerpt::text, '')) "
                      f"like {q('%' + value + '%')}")
        leaks[value[:6] + "…"] = len(n)

    out = RESULTS / tag
    out.mkdir(parents=True, exist_ok=True)
    payload = {"tag": tag, "generated_at": datetime.now(timezone.utc).isoformat(),
               "launch_spread_s": state.get("launch_spread_s"), "results": results, "secret_leaks": leaks,
               "workers": state.get("workers")}
    (out / "results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "report.md").write_text(render(payload), encoding="utf-8")
    print(render(payload))


def render(p: dict) -> str:
    rs = p["results"]
    defects = [r for r in rs if r["kind"] == "defect"]
    clean = [r for r in rs if r["kind"] == "clean"]
    exp_total = sum(len(r["found"]) for r in defects)
    exp_found = sum(sum(1 for f in r["found"] if f["found"]) for r in defects)
    totals = [r["total_ms"] for r in rs if r["total_ms"] is not None]
    queues = [r["queue_ms"] for r in rs if r["queue_ms"] is not None]
    runs_ = [r["run_ms"] for r in rs if r["run_ms"] is not None]
    lines = [
        f"# Banc vrai GitHub — série `{p['tag']}`", "",
        f"Généré le {p['generated_at'][:19]} UTC · {len(rs)} PR ouvertes en {p.get('launch_spread_s')} s "
        f"sur {len({r['repo'] for r in rs})} dépôts" + (f" · {p['workers']} worker(s)" if p.get("workers") else ""), "",
        "## Synthèse", "",
        f"- Verdicts conformes : **{sum(r['verdict_ok'] for r in rs)}/{len(rs)}**",
        f"- Défauts attendus détectés : **{exp_found}/{exp_total}**",
        f"- PR propres sans remarque majeure ou critique : **{sum(1 for r in clean if not r['noise_major'])}/{len(clean)}**",
        f"- Check GitHub conforme au verdict : **{sum(r['check_ok'] for r in rs)}/{len(rs)}**",
        f"- Email d'alerte conforme (envoyé si et seulement si bloquante) : **{sum(r['mail_ok'] for r in rs)}/{len(rs)}**",
        f"- Secrets des cas retrouvés dans le journal de l'agent : **{sum(p['secret_leaks'].values())}**",
        f"- Durée totale (attente comprise) : p50 **{secs(pct(totals, .5))}**, p95 **{secs(pct(totals, .95))}**, "
        f"max {secs(max(totals) if totals else None)}",
        f"- Attente en file : p50 {secs(pct(queues, .5))}, p95 {secs(pct(queues, .95))} · "
        f"exécution : p50 {secs(pct(runs_, .5))}, p95 {secs(pct(runs_, .95))}",
        f"- Lots en échec : {sum(r['chunks_failed'] or 0 for r in rs)} / {sum(r['chunks'] or 0 for r in rs)}", "",
        "## Par PR", "",
        "| Cas | PR | Verdict | Attendu | Détection | Autres remarques | Check | Mail | Attente | Total |",
        "|---|---|---|---|---|---|---|---|---:|---:|",
    ]
    for r in rs:
        det = ", ".join(("✅ " if f["found"] else "❌ ") + f["label"] for f in r["found"]) or "—"
        others = ", ".join(f"{f['severity']}" for f in r["other_findings"]) or "—"
        lines.append(
            f"| `{r['id']}` | [{r['repo'].split('/')[1]}#{r['pr']}]({r['url']}) | "
            f"{'✅' if r['verdict_ok'] else '❌'} {r['verdict'] or r['status']} | {' / '.join(r['expected_verdicts'])} | "
            f"{det} | {others} | {(r['check'] or {}).get('conclusion', '—')}{'' if r['check_ok'] else ' ⚠'} | "
            f"{'oui' if r['mail_sent'] else 'non'}{'' if r['mail_ok'] else ' ⚠'} | {secs(r['queue_ms'])} | {secs(r['total_ms'])} |")
    lines += ["", "## Remarques retenues", ""]
    for r in rs:
        lines.append(f"### `{r['id']}` — {r['verdict'] or r['status']}")
        if r["incomplete_reasons"]:
            lines.append(f"- Incomplet : {'; '.join(r['incomplete_reasons'])}")
        if r["error"]:
            lines.append(f"- Erreur : {r['error']}")
        for f in r["kept"]:
            lines.append(f"- **{f['severity']}** `{f['path']}:{f['line']}` — {f['title']}"
                         + (f" _(source : {f['source']})_" if f["source"] and f["source"] != "llm" else ""))
        if not r["kept"]:
            lines.append("- aucune")
        lines.append(f"- écartées par la validation : {r['dropped']} · commentaires en ligne publiés : {r['inline_comments']}")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["prepare", "launch", "collect"])
    ap.add_argument("--tag", required=True)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--timeout", type=int, default=2400)
    ap.add_argument("--workers", type=int, help="nombre de workers (noté dans le rapport)")
    a = ap.parse_args()
    if a.step == "prepare":
        prepare(a.tag, a.only)
    elif a.step == "launch":
        launch(a.tag, a.only)
        if a.workers:
            st = load_state(a.tag)
            st["workers"] = a.workers
            save_state(st)
    else:
        collect(a.tag, a.timeout)


if __name__ == "__main__":
    main()
