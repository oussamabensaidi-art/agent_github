"""Client GitHub du bot de revue.

Droits minimaux (cahier des charges : le bot ne peut ni fusionner ni modifier
le code). En mode "app", le jeton d'installation est en plus RESTREINT à la
demande à : contents:read, pull_requests:write, checks:write, metadata:read.
Le bot publie toujours des revues "COMMENT" : jamais APPROVE ni REQUEST_CHANGES.
"""
import time
from pathlib import Path

import httpx
import jwt

TOKEN_PERMISSIONS = {
    "contents": "read",
    "metadata": "read",
    "pull_requests": "write",
    "checks": "write",
}

MAX_TEXT = 60000  # limite GitHub ~65535 pour un corps de revue / un résumé de check


def _cut(text: str) -> str:
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "\n\n… (tronqué)"


class GitHubAppAuth:
    """JWT de l'App → jeton d'installation (1 h), mis en cache."""

    def __init__(self, app_id: str, private_key_path: str, api_url: str,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.app_id = app_id
        self.private_key_path = private_key_path
        self.api_url = api_url.rstrip("/")
        self._transport = transport
        self._cache: dict[int, tuple[str, float]] = {}

    def _jwt(self) -> str:
        now = int(time.time())
        key = Path(self.private_key_path).read_text()
        return jwt.encode({"iat": now - 60, "exp": now + 540, "iss": self.app_id}, key, algorithm="RS256")

    async def token(self, installation_id: int) -> str:
        cached = self._cache.get(installation_id)
        if cached and cached[1] > time.time() + 120:
            return cached[0]
        async with httpx.AsyncClient(base_url=self.api_url, timeout=20, transport=self._transport) as c:
            resp = await c.post(
                f"/app/installations/{installation_id}/access_tokens",
                headers={"Authorization": f"Bearer {self._jwt()}",
                         "Accept": "application/vnd.github+json"},
                json={"permissions": TOKEN_PERMISSIONS},
            )
            resp.raise_for_status()
            data = resp.json()
        # Durée de vie 1 h ; on garde une marge plutôt que de parser expires_at.
        self._cache[installation_id] = (data["token"], time.time() + 3300)
        return data["token"]


class GitHubClient:
    def __init__(self, token: str, api_url: str, use_checks: bool,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.use_checks = use_checks
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "calipso-pr-review-bot",
        }
        if token:  # sans jeton : lecture seule des dépôts publics (CLI en dry-run)
            headers["Authorization"] = f"Bearer {token}"
        self._http = httpx.AsyncClient(base_url=api_url.rstrip("/"), timeout=30,
                                       transport=transport, headers=headers)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _req(self, method: str, url: str, **kw) -> httpx.Response:
        resp = await self._http.request(method, url, **kw)
        resp.raise_for_status()
        return resp

    async def get_pr(self, repo: str, number: int) -> dict:
        return (await self._req("GET", f"/repos/{repo}/pulls/{number}")).json()

    async def list_files(self, repo: str, number: int) -> list[dict]:
        files: list[dict] = []
        page = 1
        while True:
            batch = (await self._req("GET", f"/repos/{repo}/pulls/{number}/files",
                                     params={"per_page": 100, "page": page})).json()
            files += batch
            if len(batch) < 100 or page >= 30:  # l'API plafonne à 3000 fichiers
                return files
            page += 1

    # ---- statut : check run (App) ou statut de commit (PAT) ----

    async def start_status(self, repo: str, sha: str, name: str) -> int | None:
        if self.use_checks:
            data = (await self._req("POST", f"/repos/{repo}/check-runs", json={
                "name": name, "head_sha": sha, "status": "in_progress",
            })).json()
            return data["id"]
        await self._req("POST", f"/repos/{repo}/statuses/{sha}", json={
            "state": "pending", "context": name, "description": "Revue automatique en cours…",
        })
        return None

    async def finish_status(self, repo: str, sha: str, name: str, check_id: int | None,
                            conclusion: str, title: str, summary: str) -> None:
        """conclusion : success | neutral | failure (vocabulaire des check runs)."""
        if self.use_checks and check_id:
            await self._req("PATCH", f"/repos/{repo}/check-runs/{check_id}", json={
                "status": "completed", "conclusion": conclusion,
                "output": {"title": title[:250], "summary": _cut(summary)},
            })
            return
        # Les statuts de commit n'ont pas de "neutral" : à vérifier → success + libellé.
        state = {"success": "success", "neutral": "success", "failure": "failure"}.get(conclusion, "error")
        await self._req("POST", f"/repos/{repo}/statuses/{sha}", json={
            "state": state, "context": name, "description": title[:140],
        })

    async def create_review(self, repo: str, number: int, sha: str, body: str,
                            comments: list[dict], fallback_body: str) -> dict:
        """Revue COMMENT avec commentaires inline.

        Si GitHub refuse un commentaire (422 : ligne non résolue), on republie
        sans inline avec `fallback_body`, qui liste toutes les remarques.
        """
        payload = {"commit_id": sha, "event": "COMMENT", "body": _cut(body), "comments": comments}
        try:
            return (await self._req("POST", f"/repos/{repo}/pulls/{number}/reviews", json=payload)).json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 422 or not comments:
                raise
            payload.update(body=_cut(fallback_body), comments=[])
            return (await self._req("POST", f"/repos/{repo}/pulls/{number}/reviews", json=payload)).json()
