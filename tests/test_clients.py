import json

import httpx
import pytest

from agent.github import GitHubClient
from agent.llm import LLMHostNotAllowed, OllamaClient


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


async def test_status_mode_maps_neutral_to_success():
    calls = []

    def handler(request: httpx.Request):
        calls.append((request.url.path, json.loads(request.content)))
        return httpx.Response(201, json={})

    gh = GitHubClient("tok", "https://api.github.com", use_checks=False, transport=httpx.MockTransport(handler))
    await gh.finish_status("o/r", "abc", "ctx", None, "neutral", "À vérifier", "s")
    await gh.aclose()
    assert calls[0][0] == "/repos/o/r/statuses/abc" and calls[0][1]["state"] == "success"
