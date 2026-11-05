"""Faux GitHub pour le banc e2e (DEV UNIQUEMENT — jamais déployé).

Reproduit ce que l'agent utilise de l'API GitHub, avec les contrôles du vrai :
  - jeton d'installation délivré seulement sur un JWT RS256 valide de l'App ;
  - toutes les requêtes doivent porter ce jeton ;
  - un commentaire inline sur une ligne hors diff → 422, comme GitHub.
Il enregistre tous les appels (GET /_recorded) et signale toute action
interdite au bot (fusion, écriture de code, APPROVE / REQUEST_CHANGES).
"""
import os
import re
import secrets
from pathlib import Path

import jwt
from fastapi import FastAPI, Header, HTTPException, Request

from e2e.fixtures import PRS, REPO

APP_ID = os.environ.get("FAKE_GITHUB_APP_ID", "12345")
PUBLIC_KEY_PATH = os.environ.get("FAKE_GITHUB_PUBLIC_KEY", "/keys/app.pub.pem")
MINIMAL_PERMISSIONS = {"contents": "read", "metadata": "read", "pull_requests": "write", "checks": "write"}

app = FastAPI(title="fake-github")
TOKENS: set[str] = set()
RECORDED: list[dict] = []
VIOLATIONS: list[str] = []
CHECK_IDS = iter(range(1000, 100000))

HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def right_side_lines(patch: str) -> set[int]:
    lines, n = set(), 0
    for raw in patch.splitlines():
        m = HUNK_RE.match(raw)
        if m:
            n = int(m.group(1))
        elif raw.startswith("-") or raw.startswith("\\"):
            continue
        else:
            lines.add(n)
            n += 1
    return lines


def auth(authorization: str | None) -> None:
    if not authorization or authorization.removeprefix("Bearer ").strip() not in TOKENS:
        raise HTTPException(401, "Bad credentials")


def pr_or_404(repo: str, number: int) -> dict:
    if repo != REPO or number not in PRS:
        raise HTTPException(404, "Not Found")
    return PRS[number]


@app.post("/app/installations/{installation_id}/access_tokens", status_code=201)
async def access_token(installation_id: int, request: Request, authorization: str | None = Header(None)):
    try:
        claims = jwt.decode(authorization.removeprefix("Bearer "), Path(PUBLIC_KEY_PATH).read_text(),
                            algorithms=["RS256"])
    except Exception as e:  # noqa: BLE001
        raise HTTPException(401, f"JWT invalide : {e}")
    if str(claims.get("iss")) != APP_ID:
        raise HTTPException(401, "mauvais App ID")
    body = await request.json()
    if body.get("permissions") != MINIMAL_PERMISSIONS:
        VIOLATIONS.append(f"jeton demandé avec des droits non minimaux : {body.get('permissions')}")
    token = "ghs_" + secrets.token_hex(16)
    TOKENS.add(token)
    RECORDED.append({"op": "token", "installation_id": installation_id, "permissions": body.get("permissions")})
    return {"token": token, "expires_at": "2099-01-01T00:00:00Z"}


@app.get("/repos/{owner}/{name}/pulls/{number}")
async def get_pr(owner: str, name: str, number: int, authorization: str | None = Header(None)):
    auth(authorization)
    pr = pr_or_404(f"{owner}/{name}", number)
    return {"number": number, "state": "open", "draft": False, "title": pr["title"], "body": pr["body"],
            "user": {"login": "dev-e2e"}, "html_url": f"https://github.com/{REPO}/pull/{number}",
            "head": {"sha": pr["sha"]}}


@app.get("/repos/{owner}/{name}/pulls/{number}/files")
async def list_files(owner: str, name: str, number: int, page: int = 1, authorization: str | None = Header(None)):
    auth(authorization)
    pr = pr_or_404(f"{owner}/{name}", number)
    return pr["files"] if page == 1 else []


@app.post("/repos/{owner}/{name}/check-runs", status_code=201)
async def create_check(owner: str, name: str, request: Request, authorization: str | None = Header(None)):
    auth(authorization)
    body = await request.json()
    check_id = next(CHECK_IDS)
    RECORDED.append({"op": "check_create", "id": check_id, **body})
    return {"id": check_id}


@app.patch("/repos/{owner}/{name}/check-runs/{check_id}")
async def update_check(owner: str, name: str, check_id: int, request: Request,
                       authorization: str | None = Header(None)):
    auth(authorization)
    RECORDED.append({"op": "check_update", "id": check_id, **(await request.json())})
    return {"id": check_id}


@app.post("/repos/{owner}/{name}/pulls/{number}/reviews")
async def create_review(owner: str, name: str, number: int, request: Request,
                        authorization: str | None = Header(None)):
    auth(authorization)
    pr = pr_or_404(f"{owner}/{name}", number)
    body = await request.json()
    if body.get("event") != "COMMENT":
        VIOLATIONS.append(f"revue avec event={body.get('event')} sur #{number}")
    patches = {f["filename"]: right_side_lines(f["patch"]) for f in pr["files"]}
    for c in body.get("comments", []):
        if c.get("side") != "RIGHT" or c.get("line") not in patches.get(c.get("path"), set()):
            RECORDED.append({"op": "review_rejected_422", "pr": number, "comment": c})
            raise HTTPException(422, "Pull request review thread line must be part of the diff")
    RECORDED.append({"op": "review", "pr": number, **body})
    return {"id": len(RECORDED)}


# --- Routes de contrôle du banc (avant le catch-all) ---
@app.get("/_recorded")
async def recorded():
    return {"calls": RECORDED, "violations": VIOLATIONS}


@app.post("/_reset")
async def reset():
    RECORDED.clear()
    VIOLATIONS.clear()
    return {"ok": True}


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def anything_else(path: str, request: Request):
    """Toute autre route (fusion, contenus, labels, …) : le bot n'a rien à y faire."""
    VIOLATIONS.append(f"appel non prévu : {request.method} /{path}")
    raise HTTPException(404, "Not Found")
