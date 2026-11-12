"""v2 — exigences de la revue de M. Hicham (partie 1) et flux d'événements (partie 2)."""
import asyncio
import json

import httpx
import pytest

from agent.diff import file_from_github, filter_files
from agent.github import GitHubClient
from agent.review import (
    OUTCOME_FAILED, OUTCOME_SUPERSEDED, PR_TEXT_PATH, VERDICT_BLOCKING, VERDICT_CHECK, VERDICT_INCOMPLETE,
    VERDICT_OK, Finding, compute_verdict, rules_version,
)
from agent.runner import run_review
from store import MemoryStore
from tests.test_graph import JOB, PATCH, SHA, FakeGitHub, FakeLLM, audit_lines, make

GH_TOKEN = "ghp_" + "Zx9Y" * 9
AWS = "AKIA" + "ZXCVBNMASDFGHJKL"
SQL_CRITICAL = {"path": "src/Repo.php", "line": 3, "severity": "critical", "category": "security",
                "title": "Injection SQL", "explanation": "Concaténation de $_GET"}


def F(severity="major", source="llm"):
    return Finding(path="a.php", line=1, severity=severity, category="bug", title="t", source=source)


def secret_files():
    patch = f"@@ -1,1 +1,2 @@\n <?php\n+$k = '{AWS}';"
    return [{"filename": "src/K.php", "status": "added", "patch": patch, "additions": 1, "deletions": 0}]


class TextGitHub(FakeGitHub):
    """PR dont le titre et la description contiennent des secrets."""

    def __init__(self, title, body, **kw):
        super().__init__(**kw)
        self.title, self.body = title, body

    async def get_pr(self, repo, number):
        pr = await super().get_pr(repo, number)
        return {**pr, "title": self.title, "body": self.body}


class MovingGitHub(FakeGitHub):
    """Un commit plus récent arrive pendant l'analyse (2e lecture de la PR)."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.reads = 0

    async def get_pr(self, repo, number):
        self.reads += 1
        pr = await super().get_pr(repo, number)
        return pr if self.reads == 1 else {**pr, "head": {"sha": "d" * 40}}


def with_store(s, publishing=True):
    s.controls = s.events = MemoryStore(publishing)
    return s.events


# ---------------------------------------------------------------- verdict v2

def test_verdict_four_states_and_pilot_mode():
    llm_crit, secret = F("critical"), F("critical", source="secret-scan")
    # Mode pilote : l'IA seule ne bloque jamais ; une source déterministe bloque.
    assert compute_verdict([llm_crit], [], pilot_mode=True) == VERDICT_CHECK
    assert compute_verdict([secret], [], pilot_mode=True) == VERDICT_BLOCKING
    assert compute_verdict([llm_crit], [], pilot_mode=False) == VERDICT_BLOCKING
    # Incomplet passe avant « à vérifier », après « bloquante ».
    assert compute_verdict([llm_crit], ["x"], pilot_mode=True) == VERDICT_INCOMPLETE
    assert compute_verdict([secret], ["x"], pilot_mode=True) == VERDICT_BLOCKING
    assert compute_verdict([F("minor")], ["x"]) == VERDICT_INCOMPLETE
    assert compute_verdict([F("major")], []) == VERDICT_CHECK
    assert compute_verdict([F("minor")], []) == VERDICT_OK


async def test_pilot_mode_ai_critical_is_advisory(tmp_path):
    s = make(tmp_path, llm=FakeLLM([SQL_CRITICAL]))
    assert s.settings.PILOT_MODE is True  # activé par défaut
    result = await run_review(JOB, s)
    assert result["verdict"] == VERDICT_CHECK
    assert s.github.statuses[-1][0] == VERDICT_CHECK
    assert s.mailer.sent == []
    assert "avis IA" in s.github.reviews[0]["comments"][0]["body"]
    assert "Mode pilote" in result["summary"]


async def test_pilot_mode_secret_still_blocks(tmp_path):
    s = make(tmp_path, github=FakeGitHub(files=secret_files()))
    result = await run_review(JOB, s)
    assert result["verdict"] == VERDICT_BLOCKING
    assert len(s.mailer.sent) == 1


async def test_rules_version_is_in_every_output(tmp_path):
    s = make(tmp_path)
    events = with_store(s)
    result = await run_review(JOB, s)
    ver = rules_version("R")
    assert ver.startswith("verdict-v3+regles-") and ver != rules_version("R modifiée")
    assert ver in result["summary"] and ver in s.github.last_summary
    assert audit_lines(s)[-1]["rules_version"] == ver
    verdict_ev = next(e for e in events.events if e["type"] == "verdict")
    assert verdict_ev["data"]["rules_version"] == ver


# ------------------------------------------------------- patch omis par GitHub

def test_omitted_patch_is_incomplete_never_excluded():
    omitted = file_from_github({"filename": "src/Huge.php", "status": "modified", "additions": 900, "deletions": 40})
    binary = file_from_github({"filename": "img/logo.png", "status": "added", "additions": 0, "deletions": 0})
    kept, skipped = filter_files([omitted, binary], [], 100, 1500, 4000)
    reasons = dict(skipped)
    assert kept == []
    assert reasons["src/Huge.php"].startswith("diff non fourni par GitHub")
    assert reasons["img/logo.png"].startswith("exclu")


async def test_omitted_patch_makes_the_run_incomplete(tmp_path):
    files = [{"filename": "src/Repo.php", "status": "modified", "patch": PATCH, "additions": 2, "deletions": 0},
             {"filename": "src/Huge.php", "status": "modified", "additions": 900, "deletions": 40}]
    s = make(tmp_path, github=FakeGitHub(files=files))
    result = await run_review(JOB, s)
    assert result["verdict"] == VERDICT_INCOMPLETE
    assert "src/Huge.php" in result["summary"] and "diff non fourni" in result["summary"]
    assert s.github.statuses[-1][0] == VERDICT_INCOMPLETE


# -------------------------------------------------------- correspondance GitHub

@pytest.mark.parametrize("outcome,state", [
    (VERDICT_OK, "success"), (VERDICT_CHECK, "failure"), (VERDICT_BLOCKING, "failure"),
    (VERDICT_INCOMPLETE, "error"), (OUTCOME_FAILED, "error"), (OUTCOME_SUPERSEDED, "error"),
])
async def test_token_mode_is_green_only_for_controles_satisfaits(outcome, state):
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(201, json={})

    gh = GitHubClient("tok", "https://api.github.com", use_checks=False, transport=httpx.MockTransport(handler))
    await gh.finish_status("o/r", "abc", "ctx", None, outcome, "t", "s", "http://ui/runs/1")
    await gh.aclose()
    assert calls[0]["state"] == state and calls[0]["target_url"] == "http://ui/runs/1"


@pytest.mark.parametrize("outcome,conclusion", [
    (VERDICT_OK, "success"), (VERDICT_CHECK, "neutral"), (VERDICT_BLOCKING, "failure"),
    (VERDICT_INCOMPLETE, "action_required"), (OUTCOME_FAILED, "action_required"),
    (OUTCOME_SUPERSEDED, "cancelled"),
])
async def test_app_mode_check_conclusions(outcome, conclusion):
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={})

    gh = GitHubClient("tok", "https://api.github.com", use_checks=True, transport=httpx.MockTransport(handler))
    await gh.finish_status("o/r", "abc", "ctx", 7, outcome, "t", "s", "http://ui/runs/1")
    await gh.aclose()
    assert calls[0]["conclusion"] == conclusion and calls[0]["details_url"] == "http://ui/runs/1"


async def test_agent_failure_in_token_mode_is_not_green(tmp_path):
    calls = []

    def handler(request):
        if request.url.path.endswith("/files"):
            return httpx.Response(500, json={})
        if request.method == "GET":
            return httpx.Response(200, json={"head": {"sha": SHA}, "state": "open"})
        calls.append(json.loads(request.content))
        return httpx.Response(201, json={})

    gh = GitHubClient("tok", "https://api.github.com", use_checks=False, transport=httpx.MockTransport(handler))
    s = make(tmp_path, github=gh)
    result = await run_review(JOB, s)
    await gh.aclose()
    assert "load_diff" in result["error"]
    assert [c["state"] for c in calls] == ["pending", "error"]


# --------------------------------------------- re-vérification avant publication

async def test_newer_commit_during_analysis_is_not_overwritten(tmp_path):
    gh = MovingGitHub(files=secret_files())
    s = make(tmp_path, github=gh)
    events = with_store(s)
    result = await run_review(JOB, s)
    assert result["verdict"] == VERDICT_BLOCKING and result["superseded"] is True
    assert gh.reviews == []                               # rien publié sur la PR
    assert gh.statuses[-1][0] == OUTCOME_SUPERSEDED       # check de l'ancien commit clos
    assert s.mailer.sent == []                            # pas d'alerte pour un résultat périmé
    assert audit_lines(s)[-1]["status"] == "superseded"
    assert events.events[-1]["data"]["status"] == "superseded"


# ------------------------------------------------------------- interrupteur

async def test_kill_switch_blocks_every_write(tmp_path):
    s = make(tmp_path, github=FakeGitHub(files=secret_files()))
    events = with_store(s, publishing=False)
    result = await run_review(JOB, s)
    assert result["verdict"] == VERDICT_BLOCKING          # l'analyse tourne quand même
    assert s.github.statuses == [] and s.github.reviews == [] and s.mailer.sent == []
    skipped = [e["data"]["step"] for e in events.events if e["type"] == "publication_skipped"]
    assert skipped == ["check en cours", "revue et check", "alerte email"]
    assert audit_lines(s)[-1]["publish_skipped"] == "kill_switch"


async def test_kill_switch_blocks_failure_status(tmp_path):
    s = make(tmp_path, github=FakeGitHub(fail_files=True))
    with_store(s, publishing=False)
    result = await run_review(JOB, s)
    assert result["error"] and s.github.statuses == []


async def test_kill_switch_is_read_before_each_write(tmp_path):
    class FlipAfterFirstRead:
        def __init__(self):
            self.reads = 0

        async def publishing_enabled(self):
            self.reads += 1
            return self.reads <= 2  # 1 : état noté dans run_started ; 2 : début du check

    s = make(tmp_path, github=FakeGitHub(files=secret_files()))
    s.controls = FlipAfterFirstRead()
    await run_review(JOB, s)
    # Coupé pendant l'analyse : le check a démarré, mais ni revue, ni conclusion, ni email.
    assert s.github.statuses == [("start", None)]
    assert s.github.reviews == [] and s.mailer.sent == []


# ---------------------------------------------------- titre et description PR

async def test_pr_title_and_body_secrets_never_reach_the_model(tmp_path):
    gh = TextGitHub(title=f"Fix {GH_TOKEN}", body=f"clé AWS : {AWS}")
    llm = FakeLLM()
    s = make(tmp_path, github=gh, llm=llm)
    events = with_store(s)
    result = await run_review(JOB, s)
    prompt = "\n".join(llm.prompts)
    assert GH_TOKEN not in prompt and AWS not in prompt and "[SECRET MASQUÉ]" in prompt
    assert result["verdict"] == VERDICT_BLOCKING
    assert {f.path for f in result["findings"] if f.source == "secret-scan"} == {PR_TEXT_PATH}
    published = json.dumps(gh.reviews) + json.dumps(gh.statuses)
    assert GH_TOKEN not in published and AWS not in published
    stored = json.dumps(events.events, ensure_ascii=False)
    assert GH_TOKEN not in stored and AWS not in stored
    assert GH_TOKEN not in s.mailer.sent[0].as_string() and AWS not in s.mailer.sent[0].as_string()


# ----------------------------------------------------------- flux d'événements

async def test_event_stream_covers_the_run_and_never_stores_a_secret(tmp_path):
    s = make(tmp_path, github=FakeGitHub(files=secret_files()), llm=FakeLLM([
        {"path": "src/K.php", "line": 2, "severity": "major", "category": "bug", "title": "Variable globale",
         "explanation": f"voir {AWS}"}]))  # un modèle qui recopierait un secret : masqué à l'écriture
    events = with_store(s)
    job = {**JOB, "run_id": "r1", "queued_at": __import__("time").time() - 2.0}
    await events.create_run(job)
    result = await run_review(job, s)
    types = [e["type"] for e in events.events]
    assert types[0] == "run_queued" and types[1] == "run_started" and types[-1] == "run_finished"
    assert [e["seq"] for e in events.events] == list(range(len(events.events)))
    started = {e["data"]["node"] for e in events.events if e["type"] == "node_started"}
    finished = [e["data"] for e in events.events if e["type"] == "node_finished"]
    assert started == {"fetch_pr", "load_diff", "scan_secrets", "ai_review", "static_checks", "decide", "publish", "alert", "audit"}
    assert all(isinstance(d["duration_ms"], int) for d in finished)
    for t in ("diff_loaded", "chunks_planned", "chunk_started", "chunk_finished", "finding",
              "findings_validated", "verdict", "published"):
        assert t in types, t
    end = events.events[-1]["data"]
    assert end["queue_ms"] >= 1900 and end["total_ms"] == end["run_ms"] + end["queue_ms"]
    assert end["verdict"] == result["verdict"] == VERDICT_BLOCKING
    excerpt = next(e for e in events.events if e["type"] == "finding" and e["data"]["source"] == "secret-scan")
    assert any(line["target"] and "[SECRET MASQUÉ]" in line["text"] for line in excerpt["data"]["excerpt"])
    assert AWS not in json.dumps(events.events, ensure_ascii=False)


async def test_store_redacts_even_if_a_node_leaks():
    store = MemoryStore()
    await store.emit("r", "finding", {"title": f"clé {AWS}", "nested": [{"x": GH_TOKEN}]})
    assert AWS not in json.dumps(store.events) and GH_TOKEN not in json.dumps(store.events)


# -------------------------------------------------------------- lots parallèles

class SlowLLM(FakeLLM):
    def __init__(self, fail_on: str | None = None):
        super().__init__()
        self.active = self.peak = 0
        self.fail_on = fail_on

    async def review(self, system, user):
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(0.05)
            if self.fail_on and self.fail_on in user:
                raise TimeoutError("lot trop long")
            path = user.split("### ", 1)[1].split(" (", 1)[0]
            return [{"path": path, "line": 2, "severity": "major", "category": "bug", "title": f"bug {path}",
                     "explanation": "x"}]
        finally:
            self.active -= 1


def many_files(n=6):
    patch = "@@ -1,1 +1,2 @@\n <?php\n+$x = compute();"
    return [{"filename": f"src/F{i}.php", "status": "modified", "patch": patch, "additions": 1, "deletions": 0}
            for i in range(n)]


async def test_chunks_run_in_parallel_within_the_limit(tmp_path):
    llm = SlowLLM()
    s = make(tmp_path, github=FakeGitHub(files=many_files()), llm=llm, CHUNK_MAX_CHARS=60, LLM_CONCURRENCY=2)
    result = await run_review(JOB, s)
    assert result["chunks_total"] == 6 and llm.peak == 2
    assert len(result["findings"]) == 6


async def test_a_failed_chunk_does_not_stop_the_others(tmp_path):
    llm = SlowLLM(fail_on="src/F3.php")
    s = make(tmp_path, github=FakeGitHub(files=many_files()), llm=llm, CHUNK_MAX_CHARS=60, LLM_CONCURRENCY=4)
    events = with_store(s)
    result = await run_review(JOB, s)
    assert result["chunks_failed"] == 1 and len(result["findings"]) == 5
    assert result["verdict"] == VERDICT_INCOMPLETE
    assert [e["data"]["index"] for e in events.events if e["type"] == "chunk_failed"] == [4]
