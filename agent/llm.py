"""Client du modèle local (Ollama /api/chat, sortie JSON contrainte par schéma).

Garde-fou "aucun code ne sort de l'infrastructure" : l'hôte du modèle doit
figurer dans LLM_ALLOWED_HOSTS, sinon l'appel est refusé AVANT tout envoi.
Basculer vers un modèle cloud = ajouter son hôte, donc une décision explicite.
"""
import json
from urllib.parse import urlparse

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from agent.prompts import FINDINGS_SCHEMA


class LLMHostNotAllowed(RuntimeError):
    pass


class LLMInvalidOutput(RuntimeError):
    pass


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, LLMInvalidOutput)):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500


class OllamaClient:
    def __init__(self, base_url: str, model: str, allowed_hosts: list[str],
                 timeout: float = 240.0, num_ctx: int = 16384,
                 transport: httpx.AsyncBaseTransport | None = None):
        host = urlparse(base_url).hostname or ""
        if host not in allowed_hosts:
            raise LLMHostNotAllowed(
                f"hôte LLM '{host}' hors de LLM_ALLOWED_HOSTS : le code ne doit pas sortir de l'infra"
            )
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.host = host
        self.timeout = timeout
        self.num_ctx = num_ctx
        self._transport = transport

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=2, min=2, max=10),
           retry=retry_if_exception(_is_retryable), reraise=True)
    async def review(self, system: str, user: str) -> list[dict]:
        payload = {
            "model": self.model,
            "stream": False,
            "format": FINDINGS_SCHEMA,
            "options": {"temperature": 0.1, "num_ctx": self.num_ctx},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        async with httpx.AsyncClient(timeout=self.timeout, transport=self._transport) as client:
            resp = await client.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            content = resp.json().get("message", {}).get("content", "")
        try:
            data = json.loads(content)
        except ValueError as e:
            raise LLMInvalidOutput(f"JSON invalide renvoyé par le modèle : {e}") from e
        findings = data.get("findings") if isinstance(data, dict) else None
        if not isinstance(findings, list):
            raise LLMInvalidOutput("clé 'findings' absente ou invalide")
        return [f for f in findings if isinstance(f, dict)]
