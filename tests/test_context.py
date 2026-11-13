"""Contexte hors diff : règles du dépôt (branche de base) et en-têtes des fichiers modifiés."""
from agent.context import clean_repo_rules, context_for_chunk, file_header
from agent.runner import run_review
from tests.test_graph import JOB, SHA, FakeGitHub, FakeLLM, make

CONTROLLER = """<?php

declare(strict_types=1);

namespace App\\Controller;

use Symfony\\Component\\Routing\\Attribute\\Route;
use Symfony\\Component\\Security\\Http\\Attribute\\IsGranted;

/**
 * Contrats.
 */
#[Route('/contrats')]
#[IsGranted('ROLE_USER')]
final class ContractController extends AbstractController
{
    private const KEY = 'AKIAZXCVBNMASDFGHJKL';

    public function index(): Response {}
}
"""


def test_file_header_stops_at_the_class_and_drops_comments():
    header = file_header(CONTROLLER)
    assert header.splitlines()[-1].startswith("final class ContractController")
    assert "#[IsGranted('ROLE_USER')]" in header and "namespace App\\Controller;" in header
    assert "Contrats." not in header and "<?php" not in header and "public function" not in header
    assert "AKIA" not in header                      # le corps de la classe n'est jamais repris


def test_file_header_is_empty_without_a_class_and_keeps_the_end_when_too_long():
    assert file_header("<?php\nreturn ['a' => 1];\n") == ""
    many = "<?php\n" + "".join(f"use App\\Service\\S{i};\n" for i in range(60)) + "#[IsGranted('X')]\nclass A\n{\n}\n"
    header = file_header(many, max_chars=300)
    assert header.startswith("…") and header.endswith("class A") and "#[IsGranted('X')]" in header


def test_context_for_chunk_respects_the_budget_and_repo_rules_are_masked():
    headers = {"a.php": "class A", "b.php": "class B" * 100}
    out = context_for_chunk(["a.php", "c.twig", "b.php"], headers, max_chars=200)
    assert "a.php" in out and "b.php" not in out
    rules = clean_repo_rules("Règle 1\npassword = 'Sup3rS3cret!99'\n" + "x" * 5000, 100)
    assert "Sup3rS3cret" not in rules and rules.endswith("(tronqué)")


class ContextGitHub(FakeGitHub):
    def __init__(self, repo_rules=None, fail=False, **kw):
        super().__init__(**kw)
        self.repo_rules, self.fail, self.asked = repo_rules, fail, []

    async def get_pr(self, repo, number):
        return {**await super().get_pr(repo, number), "base": {"ref": "main"}}

    async def get_file(self, repo, path, ref, max_bytes=200_000):
        self.asked.append((path, ref))
        if self.fail:
            raise RuntimeError("API en panne")
        if path == ".github/pr-review.md":
            return self.repo_rules
        return CONTROLLER.replace("ContractController", "Repo") if path == "src/Repo.php" else None


async def test_model_receives_repo_rules_from_base_and_class_header(tmp_path):
    gh = ContextGitHub(repo_rules="- Les montants sont en centimes.")
    llm = FakeLLM()
    s = make(tmp_path, github=gh, llm=llm)

    class Spy(FakeLLM):
        async def review(self, system, user):
            self.system = system
            return await super().review(system, user)

    s.llm = llm = Spy()
    result = await run_review(JOB, s)
    assert result["verdict"] == "CONTROLES_SATISFAITS"
    # Règles lues sur la branche de base, fichiers au commit de la PR ; pas le lock file exclu.
    assert (".github/pr-review.md", "main") in gh.asked and ("src/Repo.php", SHA) in gh.asked
    assert all(path != "composer.lock" for path, _ in gh.asked)
    assert "Règles propres à ce dépôt" in llm.system and "centimes" in llm.system
    prompt = llm.prompts[0]
    assert "#[IsGranted('ROLE_USER')]" in prompt and "ne le commente jamais" in prompt
    assert prompt.index("#[IsGranted('ROLE_USER')]") < prompt.index("Diff (partie 1/1)")


async def test_context_failure_never_blocks_the_review(tmp_path):
    llm = FakeLLM()
    s = make(tmp_path, github=ContextGitHub(fail=True), llm=llm)
    result = await run_review(JOB, s)
    assert result["verdict"] == "CONTROLES_SATISFAITS" and "Contexte (code EXISTANT" not in llm.prompts[0]


async def test_context_can_be_disabled(tmp_path):
    gh = ContextGitHub(repo_rules="x")
    s = make(tmp_path, github=gh, CONTEXT_ENABLED=False)
    await run_review(JOB, s)
    assert gh.asked == []
