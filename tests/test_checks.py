"""Contrôles statiques (conteneur checker) et CI du dépôt : lecture des rapports,
extraction sûre, et effet sur le verdict dans le graphe complet."""
import io
import json
import tarfile

import httpx
import pytest

from agent.checks import CI_PATH, CheckerClient, changed_map, evaluate_ci
from agent.diff import file_from_github
from agent.review import VERDICT_BLOCKING, VERDICT_CHECK, VERDICT_INCOMPLETE, VERDICT_OK
from agent.runner import run_review
from checker import tools
from store import MemoryStore
from tests.test_graph import JOB, FakeGitHub, FakeLLM, make

ROOT = tools.Path("/work/pr-1/src/owner-repo-abc")
# src/Repo.php : lignes ajoutées 2 et 3 (voir tests.test_graph.PATCH)
CHANGED = {"src/Repo.php": [2, 3], "composer.lock": None}


# ------------------------------------------------------------------ rapports des outils
def test_phpstan_keeps_only_errors_on_added_lines():
    report = {"files": {f"{ROOT}/src/Repo.php": {"messages": [
        {"message": "Undefined variable $x", "line": 3, "identifier": "variable.undefined"},
        {"message": "Erreur déjà présente", "line": 1}]},
        f"{ROOT}/src/Other.php": {"messages": [{"message": "hors PR", "line": 3}]}}}
    out = tools.parse_phpstan(report, ROOT, CHANGED)
    assert [(f.path, f.line, f.severity) for f in out] == [("src/Repo.php", 3, "major")]
    assert out[0].rule == "variable.undefined"


def test_cs_fixer_reports_only_style_on_added_lines():
    diff = "--- a\n+++ b\n@@ -1,4 +1,4 @@\n <?php\n-$a=1;\n+$a = 1;\n $b = 2;\n-$c=3;\n+$c = 3;\n"
    touched = tools.lines_touched_by_fix(diff)
    assert touched == {2, 4}
    out = tools.parse_cs_fixer({"files": [{"name": "src/Repo.php", "diff": diff, "appliedFixers": ["binary_operator_spaces"]}]},
                               ROOT, {"src/Repo.php": [2, 3]})
    assert len(out) == 1 and out[0].line == 2 and out[0].severity == "minor"
    # Le style de l'existant (ligne 4 non ajoutée) n'est pas imputé à la PR.
    assert tools.parse_cs_fixer({"files": [{"name": "src/Repo.php", "diff": diff}]}, ROOT, {"src/Repo.php": [3]}) == []


def test_gitleaks_never_carries_the_secret_and_ignores_existing_ones():
    report = [
        {"File": f"{ROOT}/src/Repo.php", "StartLine": 2, "RuleID": "generic-api-key",
         "Secret": "s3cr3t-value", "Match": "key = 's3cr3t-value'", "Description": "Generic API Key"},
        {"File": f"{ROOT}/src/Repo.php", "StartLine": 1, "RuleID": "generic-api-key", "Secret": "old"},
        {"File": f"{ROOT}/src/Untouched.php", "StartLine": 5, "RuleID": "x", "Secret": "y"},
    ]
    out = tools.parse_gitleaks(report, ROOT, CHANGED)
    assert [(f.path, f.line, f.severity) for f in out] == [("src/Repo.php", 2, "critical")]
    assert "s3cr3t" not in json.dumps([vars(f) for f in out])


def test_composer_audit_severity_and_empty_report():
    report = {"advisories": {"guzzlehttp/guzzle": [
        {"advisoryId": "PKSA-1", "cve": "CVE-2022-29248", "title": "Cookie leak", "severity": "high",
         "affectedVersions": "<7.4.3", "link": "https://x"},
        {"advisoryId": "PKSA-2", "title": "Moins grave", "severity": "medium"}]}}
    out = tools.parse_composer_audit(report)
    # Une remarque par paquet, à la gravité la plus haute de ses avis.
    assert [(f.severity, f.path) for f in out] == [("critical", "composer.lock")]
    assert "2 avis" in out[0].title and "CVE-2022-29248" in out[0].explanation
    assert tools.parse_composer_audit({"advisories": []}) == []


def _tar(members: dict[str, bytes], extra=None) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        for info in extra or []:
            tar.addfile(info)
    return buf.getvalue()


def test_safe_extract_returns_repo_root_and_skips_links(tmp_path):
    link = tarfile.TarInfo("owner-repo-abc/evil")
    link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
    archive = tmp_path / "a.tar.gz"
    archive.write_bytes(_tar({"owner-repo-abc/src/A.php": b"<?php"}, [link]))
    root = tools.safe_extract(archive, tmp_path / "out")
    assert root.name == "owner-repo-abc" and (root / "src/A.php").read_bytes() == b"<?php"
    assert not (root / "evil").exists()


def test_safe_extract_refuses_path_traversal(tmp_path):
    archive = tmp_path / "a.tar.gz"
    archive.write_bytes(_tar({"../../etc/cron.d/x": b"boom"}))
    with pytest.raises(tools.ArchiveError):
        tools.safe_extract(archive, tmp_path / "out")


def test_composer_autoload_files_and_scripts_are_removed(tmp_path):
    (tmp_path / "composer.json").write_text(json.dumps({
        "autoload": {"psr-4": {"App\\": "src/"}, "files": ["src/boot.php"]},
        "autoload-dev": {"files": ["tests/x.php"]}, "scripts": {"post-install-cmd": "rm -rf /"}}))
    tools.strip_autoload_files(tmp_path)
    data = json.loads((tmp_path / "composer.json").read_text())
    assert "files" not in data["autoload"] and "files" not in data["autoload-dev"] and "scripts" not in data
    assert data["autoload"]["psr-4"] == {"App\\": "src/"}


# ------------------------------------------------------------------ CI du dépôt
def run_(name, status="completed", conclusion="success", **kw):
    return {"name": name, "status": status, "conclusion": conclusion, "html_url": f"https://ci/{name}", **kw}


def test_evaluate_ci_states():
    own = "calipso-pr-review"
    assert evaluate_ci([run_(own)], own, [])[0] == "none"
    assert evaluate_ci([run_("tests", "in_progress", None)], own, [])[0] == "pending"
    st, findings, incomplete, _ = evaluate_ci([run_("tests"), run_(own, conclusion="failure")], own, [])
    assert (st, findings, incomplete) == ("done", [], [])
    st, findings, _, _ = evaluate_ci([run_("tests", conclusion="failure", output={"title": "2 tests KO"})], own, [])
    assert findings[0].path == CI_PATH and findings[0].severity == "critical" and findings[0].deterministic
    assert "2 tests KO" in findings[0].explanation
    _, _, incomplete, _ = evaluate_ci([run_("tests", conclusion="cancelled")], own, [])
    assert "cancelled" in incomplete[0]
    # Liste blanche : seuls les checks nommés comptent.
    assert evaluate_ci([run_("lint", conclusion="failure")], own, ["tests"])[0] == "none"


def test_changed_map_marks_unknown_diffs():
    fd = file_from_github({"filename": "src/A.php", "status": "modified", "additions": 1, "deletions": 0,
                           "patch": "@@ -1,1 +1,2 @@\n <?php\n+$a = 1;"})
    out = changed_map([fd], [("composer.lock", "exclu (lock / généré)"), ("old.php", "exclu (fichier supprimé)"),
                             ("big.csv", "trop volumineux (6000 lignes)")])
    assert out == {"src/A.php": [2], "composer.lock": None, "big.csv": None}


async def test_checker_client_sends_archive_and_meta():
    seen = {}

    def handler(request: httpx.Request):
        body = request.content
        seen["has_archive"] = b"src.tar.gz" in body and b"ARCHIVE" in body
        seen["meta"] = b'"phpstan_level": 6' in body
        return httpx.Response(200, json={"tools": [{"name": "phpstan", "status": "ok", "findings": []}]})

    client = CheckerClient("http://checker:8090", 30, transport=httpx.MockTransport(handler))
    out = await client.check(b"ARCHIVE", {"a.php": [1]}, 6)
    assert out[0]["name"] == "phpstan" and seen == {"has_archive": True, "meta": True}


# ------------------------------------------------------------------ graphe complet
class CheckGitHub(FakeGitHub):
    def __init__(self, ci=None, **kw):
        super().__init__(**kw)
        self.ci = ci if ci is not None else [run_("tests")]
        self.tarballs = 0

    async def download_tarball(self, repo, sha, max_bytes):
        self.tarballs += 1
        return b"tar"

    async def list_check_runs(self, repo, sha):
        return self.ci


class FakeChecker:
    def __init__(self, tools_=None, fail=False):
        self.tools, self.fail, self.calls = tools_ or [], fail, []

    async def check(self, archive, changed, level):
        self.calls.append(changed)
        if self.fail:
            raise httpx.ConnectError("checker injoignable")
        return self.tools


def tool(name, status="ok", findings=(), message=""):
    return {"name": name, "status": status, "duration_ms": 10, "message": message, "findings": list(findings)}


def checked(tmp_path, github=None, checker=None, **overrides):
    s = make(tmp_path, github=github or CheckGitHub(), CHECKS_ENABLED=True, CI_POLL_SECONDS=0,
             CI_GRACE_SECONDS=0, **overrides)
    s.checker = checker or FakeChecker([tool("gitleaks"), tool("phpstan")])
    s.controls = s.events = MemoryStore(True)
    return s


async def test_clean_checks_and_green_ci_keep_the_pr_green(tmp_path):
    s = checked(tmp_path)
    result = await run_review(JOB, s)
    assert result["verdict"] == VERDICT_OK
    assert s.checker.calls[0]["src/Repo.php"] == [2, 3] and s.checker.calls[0]["composer.lock"] is None
    assert "Contrôles automatiques" in result["summary"] and "CI du dépôt" in result["summary"]
    types = [e["type"] for e in s.events.events]
    assert "check_tool" in types and "checks_finished" in types


async def test_failing_ci_blocks_even_in_pilot_mode(tmp_path):
    gh = CheckGitHub(ci=[run_("tests", conclusion="failure", output={"title": "1 test en échec"})])
    s = checked(tmp_path, github=gh)
    result = await run_review(JOB, s)
    assert s.settings.PILOT_MODE and result["verdict"] == VERDICT_BLOCKING
    ci = [f for f in result["findings"] if f.source == "ci"]
    assert ci and ci[0].inline is False and len(s.mailer.sent) == 1


async def test_phpstan_error_on_added_line_asks_for_review(tmp_path):
    finding = {"path": "src/Repo.php", "line": 3, "severity": "major", "title": "PHPStan : méthode inconnue"}
    s = checked(tmp_path, checker=FakeChecker([tool("phpstan", "findings", [finding])]))
    result = await run_review(JOB, s)
    assert result["verdict"] == VERDICT_CHECK
    f = next(f for f in result["findings"] if f.source == "phpstan")
    assert f.inline and f.deterministic and f.category == "phpstan"


async def test_vulnerable_dependency_outside_the_diff_is_kept_and_blocks(tmp_path):
    adv = {"path": "composer.lock", "line": None, "severity": "critical", "title": "Dépendance vulnérable : a/b (CVE-1)"}
    s = checked(tmp_path, checker=FakeChecker([tool("composer-audit", "findings", [adv])]))
    result = await run_review(JOB, s)
    assert result["verdict"] == VERDICT_BLOCKING
    assert [f.path for f in result["findings"] if f.source == "composer-audit"] == ["composer.lock"]


async def test_unreachable_checker_makes_the_analysis_incomplete(tmp_path):
    s = checked(tmp_path, checker=FakeChecker(fail=True))
    result = await run_review(JOB, s)
    assert result["verdict"] == VERDICT_INCOMPLETE
    assert any("contrôles statiques indisponibles" in r for r in result["incomplete_reasons"])


async def test_tool_error_and_unfinished_ci_are_incomplete(tmp_path):
    gh = CheckGitHub(ci=[run_("tests", "in_progress", None)])
    s = checked(tmp_path, github=gh, checker=FakeChecker([tool("phpstan", "timeout", message="délai dépassé")]),
                CI_WAIT_SECONDS=0)
    result = await run_review(JOB, s)
    assert result["verdict"] == VERDICT_INCOMPLETE
    reasons = " ".join(result["incomplete_reasons"])
    assert "PHPStan : délai dépassé" in reasons and "CI du dépôt non terminée" in reasons


async def test_missing_ci_only_matters_when_required(tmp_path):
    s = checked(tmp_path, github=CheckGitHub(ci=[]))
    assert (await run_review(JOB, s))["verdict"] == VERDICT_OK
    s = checked(tmp_path, github=CheckGitHub(ci=[]), CI_REQUIRED=True)
    result = await run_review({**JOB, "delivery_id": "d2"}, s)
    assert result["verdict"] == VERDICT_INCOMPLETE and "aucune CI" in " ".join(result["incomplete_reasons"])


async def test_secrets_in_tool_output_are_masked_and_gitleaks_duplicates_dropped(tmp_path):
    aws = "AKIA" + "ZXCVBNMASDFGHJKL"
    patch = f"@@ -1,1 +1,2 @@\n <?php\n+$k = '{aws}';"
    gh = CheckGitHub(files=[{"filename": "src/K.php", "status": "added", "patch": patch, "additions": 1, "deletions": 0}])
    leak = {"path": "src/K.php", "line": 2, "severity": "critical", "title": "Secret détecté par gitleaks (aws)"}
    noisy = {"path": "src/K.php", "line": 2, "severity": "major", "title": f"PHPStan : constante {aws} inconnue"}
    s = checked(tmp_path, github=gh, checker=FakeChecker([tool("gitleaks", "findings", [leak]),
                                                          tool("phpstan", "findings", [noisy])]))
    result = await run_review(JOB, s)
    assert result["verdict"] == VERDICT_BLOCKING
    sources = [f.source for f in result["findings"]]
    assert "secret-scan" in sources and "gitleaks" not in sources  # doublon écarté
    dump = json.dumps(s.events.events, default=str) + result["summary"]
    assert aws not in dump


async def test_ai_failure_still_routes_to_fail_with_parallel_checks(tmp_path):
    s = checked(tmp_path)

    # Une erreur levée hors lot (ex. construction des lots) part dans `fail`.
    import agent.nodes as nodes_mod
    original = nodes_mod.build_chunks
    nodes_mod.build_chunks = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        result = await run_review(JOB, s)
    finally:
        nodes_mod.build_chunks = original
    assert result.get("error") and s.github.statuses[-1][0] == "ECHEC_AGENT"
