from agent.review import (
    VERDICT_BLOCKING, VERDICT_CHECK, VERDICT_READY, Finding,
    compute_verdict, finding_from_llm, render_comment, render_summary, validate_findings,
)


def F(path="src/A.php", line=11, severity="major", title="Bug", source="llm"):
    return Finding(path=path, line=line, severity=severity, category="bug", title=title, source=source)


COMMENTABLE = {"src/A.php": {10, 11, 12}}


def test_validate_drops_hallucinations_and_low_severity():
    out = validate_findings([
        F(path="src/Ghost.php"),            # fichier hors diff → écartée
        F(severity="info"),                  # sous le seuil → écartée
        F(line=99, title="Hors diff"),       # ligne hors diff → résumé seulement
        F(title="Doublon"), F(title="doublon"),
        F(severity="critical", title="Faille"),
        F(severity="weird"),
    ], COMMENTABLE, "minor")
    titles = [f.title for f in out]
    assert titles[0] == "Faille"                 # trié par gravité
    assert "Hors diff" in titles and titles.count("Doublon") == 1
    assert "src/Ghost.php" not in {f.path for f in out}
    assert next(f for f in out if f.title == "Hors diff").inline is False


def test_secret_findings_bypass_severity_threshold():
    out = validate_findings([F(severity="minor", source="secret-scan")], COMMENTABLE, "critical")
    assert len(out) == 1


def test_verdict():
    assert compute_verdict([F(severity="critical")], []) == VERDICT_BLOCKING
    assert compute_verdict([F(severity="major")], []) == VERDICT_CHECK
    assert compute_verdict([F(severity="minor")], ["trop gros"]) == VERDICT_CHECK
    assert compute_verdict([F(severity="minor")], []) == VERDICT_READY
    assert compute_verdict([], []) == VERDICT_READY


def test_finding_from_llm_tolerates_bad_input():
    assert finding_from_llm({"title": "x"}) is None
    f = finding_from_llm({"path": "/src/A.php", "line": "12", "severity": "MAJOR", "title": "t"})
    assert (f.path, f.line, f.severity) == ("src/A.php", 12, "major")


def test_rendering_neutralizes_mentions():
    f = F(title="ping @team")
    assert "@team" not in render_comment(f)
    s = render_summary(VERDICT_CHECK, [f], 0, [("composer.lock", "exclu (lock / généré)")],
                       ["`x` non analysé : trop volumineux"], "m", "abcdef1234")
    assert "@team" not in s and "Revue incomplète" in s and "composer.lock" in s
