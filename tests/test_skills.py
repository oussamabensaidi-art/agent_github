"""Relecteurs spécialisés et compétences (skills/)."""
from agent.context import file_header
from agent.review import Finding, validate_findings_detailed
from agent.runner import run_review
from agent.skills import load_skills, parse_skill, plan
from tests.test_graph import JOB, FakeGitHub, FakeLLM, make

SKILLS = load_skills("skills")


def by_name(name):
    return next(s for s in SKILLS if s.name == name)


def test_repository_skills_load_with_their_reviewer():
    names = {s.name: s.reviewer for s in SKILLS}
    assert names == {"securite": "securite", "symfony": "code", "doctrine": "code", "twig": "code", "tests": "code"}
    assert by_name("securite").matches("src/Controller/A.php") and by_name("securite").matches("templates/a.html.twig")
    assert by_name("doctrine").matches("src/Repository/ContractRepository.php")
    assert not by_name("doctrine").matches("src/Controller/A.php")


def test_bad_skill_files_are_ignored():
    assert parse_skill("pas d'en-tête", "x") is None
    assert parse_skill("---\nname: x\nreviewer: inconnu\n---\ntexte", "x") is None


def test_plan_picks_reviewers_and_only_applicable_skills():
    php = plan(["src/Repository/ContractRepository.php"], SKILLS, ["securite", "code"])
    assert [(r.name, sorted(s.name for s in sk)) for r, sk in php] == [
        ("securite", ["securite"]), ("code", ["doctrine", "symfony", "tests"])]
    # Une feuille de style : pas de relecture sécurité, le relecteur code passe quand même.
    css = plan(["public/css/app.css"], SKILLS, ["securite", "code"])
    assert [(r.name, sk) for r, sk in css] == [("code", [])]
    assert plan(["a.php"], SKILLS, []) == []


class SpyLLM(FakeLLM):
    def __init__(self, by_role):
        super().__init__()
        self.by_role, self.systems = by_role, []

    async def review(self, system, user):
        self.systems.append(system)
        self.prompts.append(user)
        role = "securite" if "relecteur SÉCURITÉ" in system else "code"
        return self.by_role.get(role, [])


SQL = {"path": "src/Repo.php", "line": 3, "severity": "critical", "category": "security",
       "title": "Injection SQL", "explanation": "Concaténation de $_GET"}


async def test_each_chunk_gets_one_pass_per_reviewer_with_its_skills(tmp_path):
    same_line_lower = {**SQL, "severity": "major", "title": "Requête non paramétrée"}
    llm = SpyLLM({"securite": [SQL], "code": [same_line_lower]})
    s = make(tmp_path, llm=llm, REVIEWERS="securite,code")
    result = await run_review(JOB, s)
    assert len(llm.systems) == 2 and result["chunks_total"] == 2
    sec = next(p for p in llm.systems if "relecteur SÉCURITÉ" in p)
    code = next(p for p in llm.systems if "relecteur CODE" in p)
    assert "Compétence : securite" in sec and "Compétence : symfony" not in sec
    assert "Compétence : symfony" in code and "Compétence : securite" not in code
    # Même ligne, même catégorie, deux relecteurs : on garde la plus grave.
    kept = [f for f in result["findings"] if f.source == "llm"]
    assert [(f.title, f.reviewer) for f in kept] == [("Injection SQL", "securite")]


async def test_a_failed_reviewer_pass_makes_the_analysis_incomplete(tmp_path):
    class HalfDown(SpyLLM):
        async def review(self, system, user):
            if "relecteur SÉCURITÉ" in system:
                raise TimeoutError("modèle trop lent")
            return await super().review(system, user)

    s = make(tmp_path, llm=HalfDown({}), REVIEWERS="securite,code")
    result = await run_review(JOB, s)
    assert result["verdict"] == "ANALYSE_INCOMPLETE" and result["chunks_failed"] == 1
    assert "passage(s) de relecture" in " ".join(result["incomplete_reasons"])


async def test_single_reviewer_mode_is_unchanged(tmp_path):
    llm = SpyLLM({"code": [SQL]})
    s = make(tmp_path, llm=llm, REVIEWERS="")
    result = await run_review(JOB, s)
    assert len(llm.systems) == 1 and "Ton rôle" not in llm.systems[0] and result["findings"][0].reviewer == ""


def test_same_reviewer_same_line_keeps_distinct_issues():
    a = Finding("a.php", 1, "major", "security", "Faille A", source="llm", reviewer="securite")
    b = Finding("a.php", 1, "critical", "security", "Faille B", source="llm", reviewer="securite")
    kept, _ = validate_findings_detailed([a, b], {"a.php": {1}}, "minor")
    assert len(kept) == 2


def test_header_includes_constructor_signature_so_injected_services_are_visible():
    src = """<?php
namespace App\\Controller;

#[IsGranted('ROLE_USER')]
final class C extends AbstractController
{
    public function __construct(
        private readonly ContractRepository $contracts,
        private readonly PremiumCalculator $calculator,
    ) {
    }

    public function index(): Response { return $this->secretStuff(); }
}
"""
    header = file_header(src)
    assert "private readonly ContractRepository $contracts," in header
    assert "secretStuff" not in header
