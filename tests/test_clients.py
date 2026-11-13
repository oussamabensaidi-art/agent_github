import json

import httpx
import pytest

from agent.github import GitHubClient
from agent.llm import (LLMHostNotAllowed, LLMInvalidOutput, OllamaClient, OpenRouterClient,
                       LLMPromptTooLong, Qwen3ApiClient, extract_findings)

FINDING = {"path": "a.php", "line": 1, "severity": "major", "category": "bug", "title": "t", "explanation": "e"}


def test_extract_findings_tolerates_fences_think_and_text():
    body = json.dumps({"findings": [FINDING]})
    assert extract_findings(body)[0]["title"] == "t"
    assert extract_findings(f"<think>hmm {{}}</think>\nVoici :\n```json\n{body}\n```\nFin.")[0]["line"] == 1
    with pytest.raises(LLMInvalidOutput):
        extract_findings("je ne sais pas")
    with pytest.raises(LLMInvalidOutput):
        extract_findings('{"autre": 1}')


@pytest.mark.parametrize("endpoint,response", [
    ("think", {"response": json.dumps({"findings": [FINDING]}), "reasoning": "...", "thinking_truncated": False}),
    ("chat", {"choices": [{"message": {"content": json.dumps({"findings": [FINDING]}), "reasoning": "..."}}]}),
])
async def test_qwen3_client_both_endpoints(endpoint, response):
    seen = {}

    def handler(request: httpx.Request):
        seen["url"], seen["key"] = str(request.url), request.headers.get("x-api-key")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=response)

    llm = Qwen3ApiClient("http://llm.internal:8085", endpoint, "k-test", ["llm.internal"],
                         transport=httpx.MockTransport(handler))
    out = await llm.review("sys", "user")
    assert out[0]["severity"] == "major"
    assert seen["url"].endswith(f"/api/qwen3/{endpoint}") and seen["key"] == "k-test"
    assert "schéma JSON" in seen["body"]["messages"][0]["content"]
    assert ("max_thinking_tokens" in seen["body"]) == (endpoint == "think")


async def test_qwen3_sends_model_and_disables_thinking_when_configured():
    seen = {}

    def handler(request: httpx.Request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"response": json.dumps({"findings": [FINDING]})})

    llm = Qwen3ApiClient("http://llm.internal:8085", "think", "k", ["llm.internal"],
                         transport=httpx.MockTransport(handler),
                         model_name="Qwen3-14B-AWQ", enable_thinking=False)
    await llm.review("sys", "user")
    body = seen["body"]
    assert body["model"] == "Qwen3-14B-AWQ"
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["temperature"] == 0.1
    assert "max_thinking_tokens" not in body   # raisonnement coupé : pas de budget de réflexion


async def test_qwen3_max_tokens_fits_the_context_window():
    seen = []

    def handler(request: httpx.Request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"findings": []})}}]})

    llm = Qwen3ApiClient("http://llm.internal:8085", "chat", "k", ["llm.internal"], max_tokens=6144,
                         context_tokens=8192, transport=httpx.MockTransport(handler))
    await llm.review("sys", "x" * 300)            # petit prompt : plafond configuré
    await llm.review("sys", "x" * 12000)          # gros lot : réduit pour tenir dans 8192
    small, big = seen[0]["max_tokens"], seen[1]["max_tokens"]
    assert small == 6144
    prompt_chars = sum(len(m["content"]) for m in seen[1]["messages"])
    assert big + prompt_chars // 3 + 128 <= 8192 and big >= 512


async def test_qwen3_halves_budget_when_vllm_rejects_the_context():
    budgets = []

    def handler(request: httpx.Request):
        body = json.loads(request.content)
        budgets.append(body["max_tokens"])
        if body["max_tokens"] > 2000:   # le vrai serveur : 502 enveloppant le 400 de vLLM
            return httpx.Response(502, json={"detail": "Erreur vLLM: 400 Client Error: Bad Request for url: "
                                                       "http://vllm-qwen3-14b:8000/v1/chat/completions"})
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"findings": [FINDING]})}}]})

    llm = Qwen3ApiClient("http://llm.internal:8085", "chat", "k", ["llm.internal"], max_tokens=6144,
                         transport=httpx.MockTransport(handler))
    out = await llm.review("sys", "user")
    assert out[0]["title"] == "t"
    assert budgets == [6144, 3072, 1536]


def test_qwen3_refuses_a_prompt_that_leaves_no_room():
    llm = Qwen3ApiClient("http://llm.internal:8085", "chat", "k", ["llm.internal"], context_tokens=8192)
    with pytest.raises(LLMPromptTooLong):
        llm.output_budget("sys", "x" * 24000)


async def test_openrouter_client_denies_data_collection_and_tracks_cost():
    seen = {}

    def handler(request: httpx.Request):
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "provider": "Parasail", "usage": {"cost": 0.0012},
            "choices": [{"message": {"content": "```json\n" + json.dumps({"findings": [FINDING]}) + "\n```"}}]})

    llm = OpenRouterClient("qwen/qwen3-coder-next", "or-test", ["openrouter.ai"],
                           transport=httpx.MockTransport(handler))
    out = await llm.review("sys", "user")
    assert out[0]["title"] == "t"
    assert seen["auth"] == "Bearer or-test"
    assert seen["body"]["provider"] == {"data_collection": "deny"}
    assert seen["body"]["model"] == "qwen/qwen3-coder-next"
    assert llm.providers_seen == {"Parasail"} and llm.cost_usd == pytest.approx(0.0012)


def test_openrouter_is_refused_unless_allowed():
    with pytest.raises(LLMHostNotAllowed):
        OpenRouterClient("qwen/qwen3-14b", "k", ["localhost", "ollama"])


def test_qwen3_client_refuses_unlisted_host():
    with pytest.raises(LLMHostNotAllowed):
        Qwen3ApiClient("http://203.0.113.9:8085", "chat", "k", ["localhost"])


def test_llm_refuses_external_host():
    with pytest.raises(LLMHostNotAllowed):
        OllamaClient("https://api.example-cloud.com", "m", ["localhost", "ollama"])


async def test_llm_parses_findings_and_sends_schema():
    seen = {}

    def handler(request: httpx.Request):
        seen.update(json.loads(request.content))
        content = json.dumps({"findings": [{"path": "a.php", "line": 1, "severity": "minor",
                                            "category": "quality", "title": "t", "explanation": "e"}]})
        return httpx.Response(200, json={"message": {"content": content}})

    llm = OllamaClient("http://ollama:11434", "qwen", ["ollama"], transport=httpx.MockTransport(handler))
    out = await llm.review("sys", "user")
    assert out[0]["title"] == "t"
    assert seen["stream"] is False and seen["format"]["required"] == ["findings"]


async def test_github_review_falls_back_without_inline_on_422():
    calls = []

    def handler(request: httpx.Request):
        body = json.loads(request.content)
        calls.append(body)
        if body["comments"]:
            return httpx.Response(422, json={"message": "Unprocessable"})
        return httpx.Response(200, json={"id": 1})

    gh = GitHubClient("tok", "https://api.github.com", use_checks=True, transport=httpx.MockTransport(handler))
    await gh.create_review("o/r", 1, "sha", "body", [{"path": "a", "line": 1, "side": "RIGHT", "body": "x"}],
                           "fallback")
    await gh.aclose()
    assert len(calls) == 2
    assert calls[0]["event"] == "COMMENT"
    assert calls[1]["body"] == "fallback" and calls[1]["comments"] == []


async def test_status_mode_maps_a_verifier_to_failure():
    calls = []

    def handler(request: httpx.Request):
        calls.append((request.url.path, json.loads(request.content)))
        return httpx.Response(201, json={})

    gh = GitHubClient("tok", "https://api.github.com", use_checks=False, transport=httpx.MockTransport(handler))
    await gh.finish_status("o/r", "abc", "ctx", None, "A_VERIFIER", "À vérifier", "s")
    await gh.aclose()
    assert calls[0][0] == "/repos/o/r/statuses/abc" and calls[0][1]["state"] == "failure"


async def test_status_description_drops_4_byte_emoji_refused_by_github():
    calls = []

    def handler(request: httpx.Request):
        calls.append(json.loads(request.content))
        return httpx.Response(201, json={})

    gh = GitHubClient("tok", "https://api.github.com", use_checks=False, transport=httpx.MockTransport(handler))
    await gh.finish_status("o/r", "abc", "ctx", None, "BLOQUANTE", "🔴 Bloquante — 2 remarque(s)", "s")
    await gh.finish_status("o/r", "abc", "ctx", None, "ANALYSE_INCOMPLETE", "⚪ Analyse incomplète — " + "x" * 200, "s")
    await gh.aclose()
    assert calls[0]["description"] == "Bloquante — 2 remarque(s)"
    assert all(ord(ch) <= 0xFFFF for ch in calls[0]["description"])
    assert calls[1]["description"].startswith("⚪ Analyse incomplète") and len(calls[1]["description"]) == 140


async def test_revoked_installation_token_is_refreshed_once():
    seen = []

    def handler(request: httpx.Request):
        seen.append(request.headers["authorization"])
        ok = request.headers["authorization"] == "Bearer neuf"
        return httpx.Response(200 if ok else 401, json={"head": {"sha": "x"}} if ok else {})

    async def refresh():
        return "neuf"

    gh = GitHubClient("ancien", "https://api.github.com", use_checks=True,
                      transport=httpx.MockTransport(handler), refresh_token=refresh)
    assert (await gh.get_pr("o/r", 1))["head"]["sha"] == "x"
    with pytest.raises(httpx.HTTPStatusError):  # une seule tentative de renouvellement
        gh._http.headers["Authorization"] = "Bearer ancien"
        await gh.get_pr("o/r", 1)
    await gh.aclose()
    assert seen == ["Bearer ancien", "Bearer neuf", "Bearer ancien"]
