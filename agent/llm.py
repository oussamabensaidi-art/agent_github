"""Client du modèle local (Ollama /api/chat, sortie JSON contrainte par schéma).

Garde-fou "aucun code ne sort de l'infrastructure" : l'hôte du modèle doit
figurer dans LLM_ALLOWED_HOSTS, sinon l'appel est refusé AVANT tout envoi.
Basculer vers un modèle cloud = ajouter son hôte, donc une décision explicite.
"""
import json
import re
from urllib.parse import urlparse

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from agent.prompts import FINDINGS_SCHEMA


class LLMHostNotAllowed(RuntimeError):
    pass


class LLMPromptTooLong(RuntimeError):
    """Le prompt ne laisse pas assez de place pour la réponse dans la fenêtre du modèle."""


class LLMInvalidOutput(RuntimeError):
    pass


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, LLMInvalidOutput)):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500


def _checked_host(base_url: str, allowed_hosts: list[str]) -> str:
    host = urlparse(base_url).hostname or ""
    if host not in allowed_hosts:
        raise LLMHostNotAllowed(
            f"hôte LLM '{host}' hors de LLM_ALLOWED_HOSTS : le code ne doit pas sortir de l'infra"
        )
    return host


def extract_findings(content: str) -> list[dict]:
    """Extrait {"findings": [...]} d'une réponse texte (bloc ```json, balises <think>, texte autour)."""
    text = re.sub(r"<think>.*?</think>", "", content or "", flags=re.S).strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.S)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise LLMInvalidOutput("aucun objet JSON dans la réponse du modèle")
    try:
        data = json.loads(text[start:end + 1])
    except ValueError as e:
        raise LLMInvalidOutput(f"JSON invalide renvoyé par le modèle : {e}") from e
    findings = data.get("findings") if isinstance(data, dict) else None
    if not isinstance(findings, list):
        raise LLMInvalidOutput("clé 'findings' absente ou invalide")
    return [f for f in findings if isinstance(f, dict)]


class OllamaClient:
    def __init__(self, base_url: str, model: str, allowed_hosts: list[str],
                 timeout: float = 240.0, num_ctx: int = 16384,
                 transport: httpx.AsyncBaseTransport | None = None):
        host = _checked_host(base_url, allowed_hosts)
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
        return extract_findings(content)


class OpenRouterClient:
    """OpenRouter (API compatible OpenAI) — BANC DE TEST UNIQUEMENT.

    Service externe : seul le code fictif du banc e2e peut y être envoyé.
    L'hôte openrouter.ai n'est pas dans LLM_ALLOWED_HOSTS par défaut.
    `provider.data_collection = deny` exclut les fournisseurs qui conservent
    ou entraînent sur les requêtes. Le fournisseur réellement servi et le coût
    sont relevés pour le journal (quantification variable selon fournisseur).
    """

    URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, model: str, api_key: str, allowed_hosts: list[str], timeout: float = 300.0,
                 max_tokens: int = 6144, transport: httpx.AsyncBaseTransport | None = None):
        if not model or not api_key:
            raise ValueError("OPENROUTER_MODEL et OPENROUTER_API_KEY sont requis")
        self.host = _checked_host(self.URL, allowed_hosts)
        self.model = f"openrouter:{model}"
        self._model_id = model
        self._key = api_key
        self.timeout = timeout
        self.max_tokens = max_tokens
        self._transport = transport
        self.providers_seen: set[str] = set()
        self.cost_usd = 0.0

    # Service mutualisé : les 429 (limite du fournisseur amont) sont fréquents et
    # passagers → plus d'essais et des attentes plus longues que pour un modèle local.
    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=5, min=5, max=60),
           retry=retry_if_exception(lambda e: _is_retryable(e) or (
               isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429)),
           reraise=True)
    async def review(self, system: str, user: str) -> list[dict]:
        payload = {
            "model": self._model_id,
            "messages": [
                {"role": "system", "content": system + Qwen3ApiClient.schema_instruction()},
                {"role": "user", "content": user},
            ],
            "temperature": 0.1,
            "max_tokens": self.max_tokens,
            "provider": {"data_collection": "deny"},
            "usage": {"include": True},
        }
        async with httpx.AsyncClient(timeout=self.timeout, transport=self._transport) as client:
            resp = await client.post(self.URL, json=payload, headers={
                "Authorization": f"Bearer {self._key}", "X-Title": "calipso-pr-review-bench"})
            resp.raise_for_status()
            data = resp.json()
        if data.get("error"):
            raise LLMInvalidOutput(f"erreur OpenRouter : {data['error']}")
        if data.get("provider"):
            self.providers_seen.add(data["provider"])
        self.cost_usd += float((data.get("usage") or {}).get("cost") or 0)
        content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        return extract_findings(content)


class Qwen3ApiClient:
    """API LLM Calipso (Qwen3 14B AWQ) : POST /api/qwen3/{chat|think}, en-tête x-api-key.

    Pas de sortie JSON contrainte : le schéma est donné dans le prompt et la
    réponse est validée (`extract_findings`) ; une réponse invalide est
    retentée une fois puis compte comme lot en échec.
      - /think : {"response", "reasoning", "thinking_truncated", ...}
      - /chat  : format OpenAI, choices[0].message.content (raisonne aussi).
    max_tokens inclut le raisonnement : il faut de la marge.

    La fenêtre du modèle (prompt + réponse) est limitée (QWEN3_CONTEXT_TOKENS) :
    max_tokens est donc calculé à chaque appel à partir de la taille du prompt.
    Si vLLM refuse quand même (la passerelle renvoie alors 502 « 400 Client
    Error »), on réessaie avec un budget divisé par deux.
    """

    CHARS_PER_TOKEN = 3       # estimation prudente (code + français ≈ 3,5 à 3,8 mesurés)
    PROMPT_OVERHEAD = 128     # gabarit de chat, rôles
    MIN_OUTPUT_TOKENS = 512   # en dessous, la réponse JSON n'a pas la place

    def __init__(self, base_url: str, endpoint: str, api_key: str, allowed_hosts: list[str],
                 timeout: float = 600.0, max_tokens: int = 6144, max_thinking_tokens: int = 3072,
                 transport: httpx.AsyncBaseTransport | None = None, context_tokens: int = 8192):
        if endpoint not in ("chat", "think"):
            raise ValueError("QWEN3_ENDPOINT doit valoir 'chat' ou 'think'")
        if not api_key:
            raise ValueError("QWEN3_API_KEY manquante")
        self.host = _checked_host(base_url, allowed_hosts)
        self.url = f"{base_url.rstrip('/')}/api/qwen3/{endpoint}"
        self.endpoint = endpoint
        self.model = f"qwen3-14b-awq/{endpoint}"
        self._key = api_key
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.max_thinking_tokens = max_thinking_tokens
        self.context_tokens = context_tokens
        self._transport = transport

    @staticmethod
    def schema_instruction() -> str:
        return ("\n\nFormat de sortie OBLIGATOIRE : un unique objet JSON, sans texte autour, "
                "conforme à ce schéma JSON :\n" + json.dumps(FINDINGS_SCHEMA, ensure_ascii=False))

    def output_budget(self, system: str, user: str) -> int:
        """Jetons de réponse disponibles une fois le prompt (estimé) placé dans la fenêtre."""
        prompt = (len(system) + len(user)) // self.CHARS_PER_TOKEN + self.PROMPT_OVERHEAD
        budget = min(self.max_tokens, self.context_tokens - prompt)
        if budget < self.MIN_OUTPUT_TOKENS:
            raise LLMPromptTooLong(
                f"prompt ≈ {prompt} jetons : trop long pour la fenêtre de {self.context_tokens} "
                f"(réduire CHUNK_MAX_CHARS)")
        return budget

    @staticmethod
    def _context_overflow(resp: httpx.Response) -> bool:
        return resp.status_code in (400, 502) and "400 Client Error" in resp.text

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=2, min=2, max=10),
           retry=retry_if_exception(_is_retryable), reraise=True)
    async def review(self, system: str, user: str) -> list[dict]:
        system = system + self.schema_instruction()
        budget = self.output_budget(system, user)
        payload = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.1,
        }
        async with httpx.AsyncClient(timeout=self.timeout, transport=self._transport) as client:
            while True:
                payload["max_tokens"] = budget
                if self.endpoint == "think":
                    payload["max_thinking_tokens"] = min(self.max_thinking_tokens, budget // 2)
                resp = await client.post(self.url, json=payload, headers={"x-api-key": self._key})
                if self._context_overflow(resp) and budget // 2 >= self.MIN_OUTPUT_TOKENS:
                    budget //= 2   # l'estimation était trop optimiste pour ce contenu
                    continue
                resp.raise_for_status()
                data = resp.json()
                break
        if "choices" in data:
            content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        else:
            content = data.get("response") or ""
        return extract_findings(content)
