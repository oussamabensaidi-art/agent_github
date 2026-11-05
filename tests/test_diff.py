from agent.diff import build_chunks, file_from_github, filter_files, parse_patch, render_for_llm

PATCH = """@@ -10,3 +10,4 @@ class A
 context10
-old11
+new11
+new12
 context13
@@ -40,2 +41,2 @@
 c41
\\ No newline at end of file
+n42"""


def gh(path, patch=PATCH, status="modified", additions=3, deletions=1):
    return file_from_github({"filename": path, "status": status, "patch": patch,
                             "additions": additions, "deletions": deletions})


def test_parse_patch_new_line_numbers():
    f = gh("src/A.php")
    assert f.added == {11: "new11", 12: "new12", 42: "n42"}
    assert f.commentable == {10, 11, 12, 13, 41, 42}
    assert [l.kind for l in parse_patch(PATCH)].count("-") == 1


def test_render_for_llm_shows_numbers():
    out = render_for_llm(gh("src/A.php"))
    assert "   11 + new11" in out
    assert "      - old11" in out


def test_filter_files_excludes_and_limits():
    files = [
        gh("composer.lock"),
        gh("vendor/x/y.php"),
        gh("src/Removed.php", status="removed"),
        gh("img/logo.png", patch=""),
        gh("src/Big.php", additions=5000, deletions=0),
        gh("src/Ok.php"),
        gh("src/Over.php", additions=10, deletions=0),
    ]
    kept, skipped = filter_files(files, ["composer.lock", "vendor/*"], max_files=100,
                                 max_file_lines=1500, max_total_lines=8)
    assert [f.path for f in kept] == ["src/Ok.php"]
    reasons = dict(skipped)
    assert reasons["composer.lock"].startswith("exclu")
    assert reasons["vendor/x/y.php"].startswith("exclu")
    assert reasons["src/Removed.php"].startswith("exclu")
    assert reasons["img/logo.png"].startswith("exclu")
    assert reasons["src/Big.php"].startswith("trop volumineux")
    assert reasons["src/Over.php"].startswith("limite")


def test_build_chunks_respects_size_and_splits_big_file():
    hunks = "\n".join(f"@@ -{i*10},1 +{i*10},1 @@\n+line {i} " + "x" * 80 for i in range(1, 30))
    big = gh("src/Big.php", patch=hunks, additions=29, deletions=0)
    small = gh("src/Small.php")
    chunks = build_chunks([small, big], max_chars=800)
    assert len(chunks) > 2
    assert all(len(c) <= 800 for c in chunks)
    assert "src/Small.php" in chunks[0]
    joined = "\n".join(chunks)
    assert all(f"line {i} " in joined for i in range(1, 30))
