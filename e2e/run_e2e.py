"""Banc e2e : vraie API, vrai worker, vrai Redis, vrai Ollama ; faux GitHub + Mailpit.

    .venv/Scripts/python e2e/run_e2e.py                       # modèle 0.5b
    E2E_MODEL=qwen2.5-coder:7b .venv/Scripts/python e2e/run_e2e.py --only 101

Étapes : clés de l'App de test → stack docker (fichiers e2e) → webhooks signés
→ attente des analyses → vérifications → rapport.
"""
import argparse
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from e2e.fixtures import EXPECTED, FAKE_AWS_KEY, PRS, REFERENCE_101, REPO, WEBHOOK_SHA  # noqa: E402

KEYS = ROOT / "e2e" / ".keys"
COMPOSE = ["docker", "compose", "-f", "docker-compose.yml", "-f", "docker-compose.override.yml",
           "-f", "e2e/docker-compose.e2e.yml"]
API, FAKE_GH, MAILPIT = "http://localhost:8020", "http://localhost:9000", "http://localhost:8025"
SECRET = "e2e-webhook-secret"


def sh(*args: str, check: bool = True) -> str:
    env = {**os.environ, "MSYS_NO_PATHCONV": "1"}
    r = subprocess.run([*COMPOSE, *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", env=env)
    if check and r.returncode:
        raise RuntimeError(f"{' '.join(args)} : {r.stderr.strip()}")
    return r.stdout


def http(method: str, url: str, body: bytes | None = None, headers: dict | None = None):
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
        try:
            return json.loads(raw) if raw else None
        except ValueError:  # ex. Mailpit DELETE → "ok"
            return raw.decode()


def ensure_keys() -> None:
    if (KEYS / "app.pem").exists():
        return
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    KEYS.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    (KEYS / "app.pem").write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    (KEYS / "app.pub.pem").write_bytes(key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))


def wait_up() -> None:
    for _ in range(60):
        try:
            http("GET", f"{API}/health")
            http("GET", f"{FAKE_GH}/_recorded")
            http("GET", f"{MAILPIT}/api/v1/messages")
            return
        except Exception:  # noqa: BLE001
            time.sleep(2)
    raise RuntimeError("la stack e2e ne répond pas")


def reset() -> None:
    http("POST", f"{FAKE_GH}/_reset")
    http("DELETE", f"{MAILPIT}/api/v1/messages")
    sh("exec", "-T", "redis", "redis-cli", "EVAL",
       "for _,k in ipairs(redis.call('keys','prreview:*')) do redis.call('del',k) end return 1", "0")
    sh("exec", "-T", "worker", "sh", "-c", "rm -f /data/audit-e2e.jsonl")
    # Le worker garde son jeton d'installation 1 h : on le redémarre pour que
    # chaque passage exerce réellement l'authentification GitHub App.
    sh("restart", "worker")


def send_webhook(number: int, run_id: str) -> str:
    sha = WEBHOOK_SHA.get(number, PRS[number]["sha"])
    body = json.dumps({
        "action": "opened", "repository": {"full_name": REPO}, "installation": {"id": 42},
        "pull_request": {"number": number, "draft": False, "state": "open", "head": {"sha": sha}},
    }).encode()
    sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    res = http("POST", f"{API}/webhook/github", body, {
        "X-GitHub-Event": "pull_request", "X-GitHub-Delivery": f"e2e-{run_id}-{number}",
        "X-Hub-Signature-256": sig, "Content-Type": "application/json"})
    return res["status"]


def psql(sql: str) -> list[list[str]]:
    out = sh("exec", "-T", "db", "psql", "-U", "prreview", "-d", "prreview", "-At", "-F", "|", "-c", sql)
    return [line.split("|") for line in out.splitlines() if line.strip()]


def audit_lines() -> list[dict]:
    out = sh("exec", "-T", "worker", "sh", "-c", "cat /data/audit-e2e.jsonl 2>/dev/null || true")
    return [json.loads(l) for l in out.splitlines() if l.strip()]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--only", type=int, nargs="*", help="numéros de PR à jouer (défaut : toutes)")
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--no-build", action="store_true")
    args = p.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    numbers = args.only or sorted(PRS)

    ensure_keys()
    sh("up", "-d", *([] if args.no_build else ["--build"]), "--wait")
    wait_up()
    reset()

    run_id = str(int(time.time()))
    t0 = time.time()
    for n in numbers:
        print(f"webhook #{n} → {send_webhook(n, run_id)}")
    # Une relivraison du même webhook doit être ignorée.
    print(f"relivraison #{numbers[0]} → {send_webhook(numbers[0], run_id)}")

    audits: dict[int, dict] = {}
    while time.time() - t0 < args.timeout and len(audits) < len(numbers):
        audits = {a["pr_number"]: a for a in audit_lines()}
        time.sleep(3)
    rec = http("GET", f"{FAKE_GH}/_recorded")
    mails = http("GET", f"{MAILPIT}/api/v1/messages")["messages"]
    calls = rec["calls"]

    failures: list[str] = []

    def expect(cond: bool, msg: str) -> None:
        if not cond:
            failures.append(msg)

    expect(not rec["violations"], f"actions interdites : {rec['violations']}")
    tokens = [c for c in calls if c["op"] == "token"]
    expect(bool(tokens), "aucun jeton d'installation demandé (mode App non exercé)")
    expect(not any(c["op"] == "review_rejected_422" for c in calls), "commentaire inline refusé (422)")

    print("\n=== Résultats ===")
    for n in numbers:
        a = audits.get(n)
        reviews = [c for c in calls if c["op"] == "review" and c["pr"] == n]
        sha = PRS[n]["sha"]
        creates = {c["id"] for c in calls if c["op"] == "check_create" and c["head_sha"] == sha}
        updates = [c for c in calls if c["op"] == "check_update" and c["id"] in creates]
        conclusion = updates[-1]["conclusion"] if updates else None
        mail = [m for m in mails if f"#{n} " in m["Subject"]]
        exp = EXPECTED[n]

        expect(a is not None, f"#{n} : pas de ligne d'audit (analyse non terminée ?)")
        expect(conclusion in exp["verdicts"], f"#{n} : check {conclusion!r}, attendu parmi {exp['verdicts']}")
        if exp["alert"] is not None:
            expect(bool(mail) == exp["alert"],
                   f"#{n} : alerte email {'absente' if exp['alert'] else 'inattendue'}")
        # L'alerte suit toujours le verdict : mail ⇔ check failure.
        expect(bool(mail) == (conclusion == "failure"), f"#{n} : alerte email incohérente avec le check")
        if exp["verdicts"] == {None}:
            expect(not reviews, f"#{n} : PR obsolète mais une revue a été publiée")
            expect(a is None or a["status"] == "stale", f"#{n} : statut d'audit {a and a['status']}")
        else:
            expect(len(reviews) == 1, f"#{n} : {len(reviews)} revue(s) publiée(s), attendu 1")

        comments = reviews[0]["comments"] if reviews else []
        print(f"\n#{n} {PRS[n]['title']}")
        if a:
            print(f"   audit : {a['status']} · verdict {a['verdict']} · {a['duration_s']} s · "
                  f"remarques {a['findings']} · secrets {a['secrets_found']} · lots {a['chunks_total']} "
                  f"(échecs {a['chunks_failed']})"
                  + (f" · servi par {a['llm_served_by']}" if a.get("llm_served_by") else "")
                  + (f" · coût ${a['llm_cost_usd']}" if a.get("llm_cost_usd") else ""))
        print(f"   check : {conclusion} · revue : {len(reviews)} · inline : {len(comments)} · mail : {len(mail)}")
        for c in comments:
            first = c["body"].split("\n", 1)[0]
            print(f"     L{c['line']:<4} {first}")

    # 101 : le secret est signalé en ligne et ne ressort nulle part.
    if 101 in numbers:
        revs = [c for c in calls if c["op"] == "review" and c["pr"] == 101]
        lines = {c["line"] for r in revs for c in r["comments"]}
        expect(12 in lines, "#101 : pas de commentaire sur la ligne 12 (clé AWS)")
        full_mails = [http("GET", f"{MAILPIT}/api/v1/message/{m['ID']}") for m in mails]
        leaked = [where for where, blob in (
            ("appels GitHub", json.dumps(calls)), ("emails", json.dumps(full_mails)),
            ("audit", json.dumps(list(audits.values()))),
            ("logs worker", sh("logs", "worker", check=False))) if FAKE_AWS_KEY in blob]
        expect(not leaked, f"#101 : secret retrouvé dans : {leaked}")
        details = [c.get("details_url", "") for c in calls if c["op"] == "check_create"]
        expect(all("/ui/runs/" in d for d in details), "check sans lien vers la page de l'analyse")

        # Qualité du modèle (rapport, pas assertion) : a-t-il vu les vrais problèmes ?
        llm_lines = {c["line"] for r in revs for c in r["comments"] if "source : llm" in c["body"]}
        print("\n=== Pertinence du modèle sur #101 (référence humaine) ===")
        def near(line: int) -> set[int]:
            return {l for l in llm_lines if abs(l - line) <= 1}

        matched: set[int] = set()
        for line, issue in REFERENCE_101.items():
            matched |= near(line)
            print(f"   {'✔' if near(line) else '✘'} L{line} {issue}")
        extra = sorted(llm_lines - matched)
        if extra:
            print(f"   remarques hors référence (à juger) : lignes {extra}")

    # Journal d'événements (v2) : un run par analyse, rejouable, sans aucun secret.
    runs = {int(r[0]): r for r in psql(
        "SELECT pr_number, status, coalesce(verdict, ''), queue_ms, total_ms, "
        "(SELECT count(*) FROM events e WHERE e.run_id = runs.id) FROM runs "
        f"WHERE delivery_id LIKE 'e2e-{run_id}-%'")}
    print("\n=== Journal d'événements ===")
    for n in numbers:
        r = runs.get(n)
        expect(r is not None, f"#{n} : aucun run dans le journal d'événements")
        if r:
            print(f"   #{n} : {r[1]:<10} {r[2]:<22} attente {r[3]} ms · total {r[4]} ms · {r[5]} événements")
            expect(r[1] in ("ok", "stale"), f"#{n} : statut de run {r[1]}")
            expect(r[3] != "" and r[4] != "", f"#{n} : durée d'attente / totale non mesurée")
            if audits.get(n) and audits[n].get("verdict"):
                expect(r[2] == audits[n]["verdict"], f"#{n} : verdict du journal {r[2]} ≠ audit {audits[n]['verdict']}")
    leaks = psql("SELECT count(*) FROM events WHERE data::text LIKE '%" + FAKE_AWS_KEY + "%'")[0][0]
    leaks_f = psql("SELECT count(*) FROM findings WHERE row_to_json(findings)::text LIKE '%" + FAKE_AWS_KEY + "%'")[0][0]
    expect(leaks == "0" and leaks_f == "0", f"secret retrouvé dans le journal d'événements ({leaks} événements, {leaks_f} remarques)")
    print(f"   secret dans le journal : {leaks} événement(s), {leaks_f} remarque(s)")

    if 103 in numbers:
        revs = [c for c in calls if c["op"] == "review" and c["pr"] == 103]
        expect(bool(revs) and "trop volumineux" in revs[0]["body"], "#103 : fichier trop gros non signalé")
        expect(bool(revs) and "Analyse incomplète" in revs[0]["body"], "#103 : verdict « analyse incomplète » absent")

    print(f"\nDurée totale : {time.time() - t0:.0f} s")
    if failures:
        print("\n❌ ÉCHECS :")
        for f in failures:
            print(f"   - {f}")
        return 1
    print("\n✅ Tous les contrôles e2e passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
