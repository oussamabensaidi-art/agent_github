"""Graphe complet avec GitHub, modèle et SMTP simulés."""
import json

import pytest

from agent.audit import AuditLog
from agent.runner import run_review
from agent.state import Services
from config import Settings

SHA = "b" * 40
PATCH = """@@ -1,2 +1,4 @@
 <?php
+$id = $_GET['id'];
+$rows = $conn->query("SELECT * FROM t WHERE id = " . $id);
 return $rows;"""


class FakeGitHub:
    def __init__(self, files=None, head=SHA, fail_files=False):
        self.files = files if files is not None else [
            {"filename": "src/Repo.php", "status": "modified", "patch": PATCH, "additions": 2, "deletions": 0},
            {"filename": "composer.lock", "status": "modified", "patch": "@@ -1 +1 @@\n+x", "additions": 1, "deletions": 0},
        ]
        self.head, self.fail_files = head, fail_files
        self.reviews, self.statuses = [], []

    async def get_pr(self, repo, number):
        return {"head": {"sha": self.head}, "state": "open", "title": "Ajout repo",
                "body": "desc", "user": {"login": "dev1"}, "html_url": "https://github.com/x/y/pull/3"}

    async def list_files(self, repo, number):
        if self.fail_files:
            raise RuntimeError("API down")
        return self.files

    async def start_status(self, repo, sha, name, details_url=""):
        self.statuses.append(("start", None))
        return 123

    async def finish_status(self, repo, sha, name, check_id, outcome, title, summary, details_url=""):
        self.statuses.append((outcome, title))
        self.last_summary = summary

    async def create_review(self, repo, number, sha, body, comments, fallback_body):
        self.reviews.append({"body": body, "comments": comments})
        return {}


class FakeLLM:
    model, host = "fake-model", "localhost"

    def __init__(self, findings=None, fail=False):
        self.findings, self.fail, self.prompts = findings or [], fail, []

    async def review(self, system, user):
        self.prompts.append(user)
        if self.fail:
            raise TimeoutError("modèle trop lent")
        return self.findings


class FakeMailer:
    configured = True

    def __init__(self):
        self.sent = []

    async def send(self, msg):
        self.sent.append(msg)


def make(tmp_path, github=None, llm=None, **overrides):
    settings = Settings(_env_file=None, AUDIT_LOG_PATH=str(tmp_path / "audit.jsonl"),
                        ALERT_EMAILS="lead@calipso.fr", SMTP_HOST="smtp", **overrides)
    return Services(github=github or FakeGitHub(), llm=llm or FakeLLM(), mailer=FakeMailer(),
                    audit=AuditLog(settings.AUDIT_LOG_PATH), settings=settings, rules="R")


JOB = {"delivery_id": "d", "repo": "calipso/app", "pr_number": 3, "head_sha": SHA, "installation_id": 1}


def audit_lines(s):
    with open(s.settings.AUDIT_LOG_PATH, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh]


async def test_blocking_pr_is_commented_flagged_and_alerted(tmp_path):
    llm = FakeLLM([
        {"path": "src/Repo.php", "line": 3, "severity": "critical", "category": "security",
         "title": "Injection SQL", "explanation": "Concaténation de $_GET", "suggestion": "Paramètres liés"},
        {"path": "src/Invented.php", "line": 1, "severity": "major", "category": "bug", "title": "Fantôme",
         "explanation": "x"},
    ])
    # Hors mode pilote : une remarque critique de l'IA rend la PR bloquante.
    s = make(tmp_path, llm=llm, PILOT_MODE=False)
    result = await run_review(JOB, s)

    assert result["verdict"] == "BLOQUANTE"
    assert [f.title for f in result["findings"]] == ["Injection SQL"]
    review = s.github.reviews[0]
    assert review["comments"][0]["line"] == 3 and review["comments"][0]["side"] == "RIGHT"
    assert s.github.statuses[-1][0] == "BLOQUANTE"
    assert len(s.mailer.sent) == 1 and "PR bloquante" in s.mailer.sent[0]["Subject"]
    # Le lock file n'a pas été envoyé au modèle.
    assert "composer.lock" not in llm.prompts[0]
    rec = audit_lines(s)[-1]
    assert rec["status"] == "ok" and rec["verdict"] == "BLOQUANTE" and rec["llm_host"] == "localhost"
    assert rec["findings"]["critical"] == 1 and rec["alert_sent"] is True


async def test_clean_pr_is_ready_without_alert(tmp_path):
    s = make(tmp_path)
    result = await run_review(JOB, s)
    assert result["verdict"] == "CONTROLES_SATISFAITS"
    assert s.github.statuses[-1][0] == "CONTROLES_SATISFAITS"
    assert s.mailer.sent == []


async def test_secret_is_masked_before_llm_and_blocks(tmp_path):
    secret = "ghp_" + "a1B2" * 9
    patch = f"@@ -1,1 +1,2 @@\n <?php\n+$t = '{secret}';"
    gh = FakeGitHub(files=[{"filename": "src/K.php", "status": "added", "patch": patch,
                            "additions": 1, "deletions": 0}])
    llm = FakeLLM()
    s = make(tmp_path, github=gh, llm=llm)
    result = await run_review(JOB, s)
    assert secret not in llm.prompts[0]
    assert result["verdict"] == "BLOQUANTE"
    assert secret not in gh.reviews[0]["body"] + json.dumps(gh.reviews[0]["comments"])
    assert secret not in open(s.settings.AUDIT_LOG_PATH, encoding="utf-8").read()


async def test_llm_failure_gives_analyse_incomplete(tmp_path):
    s = make(tmp_path, llm=FakeLLM(fail=True))
    result = await run_review(JOB, s)
    assert result["verdict"] == "ANALYSE_INCOMPLETE"
    assert "Analyse incomplète" in result["summary"]
    assert s.github.statuses[-1][0] == "ANALYSE_INCOMPLETE"


async def test_stale_job_is_skipped(tmp_path):
    s = make(tmp_path, github=FakeGitHub(head="c" * 40))
    result = await run_review(JOB, s)
    assert result["stale"] is True and "verdict" not in result
    assert s.github.reviews == [] and s.github.statuses == []
    assert audit_lines(s)[-1]["status"] == "stale"


async def test_github_error_goes_to_fail(tmp_path):
    s = make(tmp_path, github=FakeGitHub(fail_files=True))
    result = await run_review(JOB, s)
    assert "load_diff" in result["error"]
    assert s.github.statuses[-1][0] == "ECHEC_AGENT"
    assert audit_lines(s)[-1]["status"] == "error"


async def test_dry_run_publishes_nothing(tmp_path):
    s = make(tmp_path, llm=FakeLLM([{"path": "src/Repo.php", "line": 3, "severity": "critical",
                                     "category": "security", "title": "Injection SQL", "explanation": "x"}]),
             DRY_RUN=True, PILOT_MODE=False)
    result = await run_review(JOB, s)
    assert result["verdict"] == "BLOQUANTE"
    assert s.github.reviews == [] and s.github.statuses == [] and s.mailer.sent == []
