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

from agent.review import CHECK_CONCLUSION, STATUS_STATE

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

    async def token(self, installation_id: int, force: bool = False) -> str:
        cached = self._cache.get(installation_id)
        if cached and cached[1] > time.time() + 120 and not force:
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
                 transport: httpx.AsyncBaseTransport | None = None, refresh_token=None):
        """`refresh_token` (mode App) : jeton révoqué avant son expiration (App réinstallée,
        droits modifiés) → 401 → un nouveau jeton est demandé, une seule fois."""
        self.use_checks = use_checks
        self._refresh = refresh_token
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
        if resp.status_code == 401 and self._refresh is not None:
            self._http.headers["Authorization"] = f"Bearer {await self._refresh()}"
            self._refresh = None
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
    # Correspondance verdict → GitHub : agent.review.CHECK_CONCLUSION / STATUS_STATE.

    async def start_status(self, repo: str, sha: str, name: str, details_url: str = "") -> int | None:
        if self.use_checks:
            body = {"name": name, "head_sha": sha, "status": "in_progress"}
            if details_url:
                body["details_url"] = details_url
            data = (await self._req("POST", f"/repos/{repo}/check-runs", json=body)).json()
            return data["id"]
        body = {"state": "pending", "context": name, "description": "Revue automatique en cours…"}
        if details_url:
            body["target_url"] = details_url
        await self._req("POST", f"/repos/{repo}/statuses/{sha}", json=body)
        return None

    async def finish_status(self, repo: str, sha: str, name: str, check_id: int | None,
                            outcome: str, title: str, summary: str, details_url: str = "") -> None:
        """outcome : un verdict ou OUTCOME_FAILED / OUTCOME_SUPERSEDED (agent.review)."""
        if self.use_checks and check_id:
            body = {"status": "completed", "conclusion": CHECK_CONCLUSION[outcome],
                    "output": {"title": title[:250], "summary": _cut(summary)}}
            if details_url:
                body["details_url"] = details_url
            await self._req("PATCH", f"/repos/{repo}/check-runs/{check_id}", json=body)
            return
        # Statut de commit : seul « contrôles satisfaits » est vert (pas d'état neutre).
        body = {"state": STATUS_STATE[outcome], "context": name, "description": title[:140]}
        if details_url:
            body["target_url"] = details_url
        await self._req("POST", f"/repos/{repo}/statuses/{sha}", json=body)

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
