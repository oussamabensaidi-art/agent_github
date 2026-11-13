"""Nouveau push sur une PR déjà relue (pas de commentaires en double, anciennes synthèses
repliées) et clôture différée d'un check quand l'interrupteur est coupé en pleine analyse."""
from agent.review import MARKER, SUPERSEDED_MARK
from agent.runner import run_review
from store import MemoryStore
from tests.test_graph import JOB, SHA, FakeGitHub, FakeLLM, make
from worker import flush_deferred

SQL = {"path": "src/Repo.php", "line": 3, "severity": "major", "category": "security",
       "title": "Injection SQL", "explanation": "Concaténation de $_GET"}
OLD_SHA = "a" * 40


async def first_review(tmp_path):
    """Première analyse : renvoie le commentaire en ligne tel qu'il a été publié."""
    s = make(tmp_path, llm=FakeLLM([SQL]))
    await run_review(JOB, s)
    return s.github.reviews[0]["comments"][0]


def previous(gh, comment, line=3, body=None):
    gh.existing_reviews = [{"id": 11, "commit_id": OLD_SHA, "body": f"{MARKER}\n## Revue automatique — …"},
                           {"id": 12, "commit_id": OLD_SHA, "body": "LGTM (revue humaine)"}]
    gh.existing_comments = [{"pull_request_review_id": 11, "path": comment["path"], "line": line,
                             "body": body or comment["body"] + "\r\n"}]


async def test_second_push_does_not_repeat_comments_and_folds_old_review(tmp_path):
    comment = await first_review(tmp_path)
    gh = FakeGitHub()
    previous(gh, comment)
    s = make(tmp_path, github=gh, llm=FakeLLM([SQL]))
    result = await run_review({**JOB, "delivery_id": "d2"}, s)
    assert result["published"] and gh.reviews[0]["comments"] == []
    assert "déjà commentée(s)" in gh.reviews[0]["body"]
    # Seule la revue de l'agent est repliée, jamais une revue humaine.
    assert [rid for rid, _ in gh.updated_reviews] == [11]
    assert SUPERSEDED_MARK in gh.updated_reviews[0][1] and OLD_SHA[:7] in gh.updated_reviews[0][1]


async def test_outdated_or_changed_comment_is_posted_again(tmp_path):
    comment = await first_review(tmp_path)
    gh = FakeGitHub()
    previous(gh, comment, line=None)               # GitHub : commentaire devenu obsolète
    s = make(tmp_path, github=gh, llm=FakeLLM([SQL]))
    await run_review({**JOB, "delivery_id": "d3"}, s)
    assert len(gh.reviews[0]["comments"]) == 1 and "déjà commentée" not in gh.reviews[0]["body"]


async def test_already_folded_or_same_commit_reviews_are_left_alone(tmp_path):
    gh = FakeGitHub()
    gh.existing_reviews = [{"id": 1, "commit_id": OLD_SHA, "body": f"{MARKER}\n{SUPERSEDED_MARK}\nancienne"},
                           {"id": 2, "commit_id": SHA, "body": f"{MARKER}\nmême commit"}]
    s = make(tmp_path, github=gh, llm=FakeLLM([SQL]))
    await run_review(JOB, s)
    assert gh.updated_reviews == [] and len(gh.reviews[0]["comments"]) == 1


async def test_unreadable_previous_reviews_do_not_block_publication(tmp_path):
    class Broken(FakeGitHub):
        async def list_reviews(self, repo, number):
            raise RuntimeError("API en panne")

    gh = Broken()
    s = make(tmp_path, github=gh, llm=FakeLLM([SQL]))
    result = await run_review(JOB, s)
    assert result["published"] and len(gh.reviews[0]["comments"]) == 1


class FlipStore(MemoryStore):
    """Publication active au début de l'analyse, coupée juste après la création du check."""

    def __init__(self):
        super().__init__(True)
        self.reads = 0
        self.flip = True

    async def publishing_enabled(self) -> bool:
        self.reads += 1
        return (not self.flip or self.reads <= 2) and self.default_publishing


async def test_check_left_in_progress_is_closed_once_publishing_resumes(tmp_path):
    gh = FakeGitHub()
    s = make(tmp_path, github=gh, llm=FakeLLM([SQL]))
    store = s.controls = s.events = FlipStore()
    result = await run_review(JOB, s)
    # Coupure en pleine analyse : check créé, rien d'autre écrit, clôture mise de côté.
    assert gh.statuses == [("start", None)] and gh.reviews == [] and result["publish_skipped"] == "kill_switch"
    assert len(store.deferred) == 1 and store.deferred[0]["check_id"] == 123

    async def client_for(installation_id):
        return gh

    # Toujours coupé : rien ne part.
    assert await flush_deferred(store, client_for) == 0 and gh.statuses == [("start", None)]
    # Réactivé : le check est clos avec le verdict, une seule fois.
    store.flip = False
    assert await flush_deferred(store, client_for) == 1
    assert gh.statuses[-1][0] == "A_VERIFIER" and "Publication coupée pendant cette analyse" in gh.last_summary
    assert await flush_deferred(store, client_for) == 0
