from agent.diff import file_from_github
from agent.secrets_scan import REDACTED, scan_and_redact

AWS = "AKIA" + "ABCDEFGHIJKLMNOP"
PWD = "S3cr3t-Prod-Pass!"


def make(patch):
    return file_from_github({"filename": "src/C.php", "status": "modified", "patch": patch,
                             "additions": 3, "deletions": 0})


def test_detects_and_redacts():
    f = make(f"""@@ -1,1 +1,4 @@
 <?php
+$aws = '{AWS}';
+$config = ['password' => '{PWD}'];
+$user = $request->get('password');""")
    findings = scan_and_redact([f])
    assert {(x.line, x.severity) for x in findings} == {(2, "critical"), (3, "critical")}
    assert AWS not in f.patch and PWD not in f.patch
    assert REDACTED in f.patch
    # Le secret n'est jamais recopié dans la remarque.
    assert all(AWS not in x.explanation + x.title and PWD not in x.explanation + x.title for x in findings)
    # Numéros de ligne inchangés après masquage.
    assert f.added[4] == "$user = $request->get('password');"


def test_placeholders_and_removed_lines_are_not_findings():
    f = make(f"""@@ -1,2 +1,2 @@
-$token = '{PWD}';
+$token = 'changeme-later';
+$dsn = '%env(DATABASE_URL)%';""")
    assert scan_and_redact([f]) == []
    # Une ligne supprimée est quand même masquée avant l'envoi au modèle.
    assert PWD not in f.patch
