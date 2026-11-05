import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

import main
from config import settings

SECRET = "test-secret"


class FakeQueue:
    def __init__(self):
        self.jobs, self.seen = [], set()

    async def ping(self):
        return True

    async def enqueue(self, job):
        key = (job["delivery_id"], job["head_sha"])
        if key in self.seen:
            return False
        self.seen.add(key)
        self.jobs.append(job)
        return True


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "GITHUB_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(main, "queue", FakeQueue())
    return TestClient(main.app)


def payload(action="opened", draft=False, state="open"):
    return {
        "action": action,
        "repository": {"full_name": "calipso/app"},
        "installation": {"id": 7},
        "pull_request": {"number": 5, "draft": draft, "state": state, "head": {"sha": "a" * 40}},
    }


def post(client, body: dict, event="pull_request", delivery="d1", secret=SECRET):
    raw = json.dumps(body).encode()
    sig = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post("/webhook/github", content=raw, headers={
        "X-GitHub-Event": event, "X-GitHub-Delivery": delivery, "X-Hub-Signature-256": sig,
        "Content-Type": "application/json",
    })


def test_rejects_bad_signature(client):
    assert post(client, payload(), secret="wrong").status_code == 401


def test_rejects_missing_secret_config(client, monkeypatch):
    monkeypatch.setattr(settings, "GITHUB_WEBHOOK_SECRET", "")
    assert post(client, payload(), secret="").status_code == 401


def test_queues_opened_pr(client):
    r = post(client, payload())
    assert r.status_code == 202 and r.json()["status"] == "queued"
    job = main.queue.jobs[0]
    assert job == {"delivery_id": "d1", "repo": "calipso/app", "pr_number": 5,
                   "head_sha": "a" * 40, "installation_id": 7, "action": "opened"}


def test_duplicate_delivery(client):
    post(client, payload())
    assert post(client, payload()).json()["status"] == "duplicate"


@pytest.mark.parametrize("body,event", [
    (payload(action="closed"), "pull_request"),
    (payload(action="labeled"), "pull_request"),
    (payload(draft=True), "pull_request"),
    (payload(state="closed"), "pull_request"),
    ({"zen": "x"}, "push"),
])
def test_ignored_events(client, body, event):
    assert post(client, body, event=event).json()["status"] == "ignored"


def test_ping(client):
    assert post(client, {"zen": "hi"}, event="ping").json()["status"] == "pong"
