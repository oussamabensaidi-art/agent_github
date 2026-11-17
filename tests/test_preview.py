"""Aperçu avant / après : choix des pages, activation, nœud ui_preview, résumé GitHub."""
import base64
import json

from agent.preview import split_page
from agent.review import preview_rows
from agent.runner import run_review
from preview.pages import choose_pages, fill, parse_routes, ui_files
from store import MemoryStore
from tests.test_graph import JOB, FakeGitHub, make

CONTROLLER = """<?php
namespace App\\Controller;

use App\\Form\\ContractType;

#[Route('/contrats')]
final class ContractController extends AbstractController
{
    #[Route('', name: 'contract_index', methods: ['GET'])]
    public function index(): Response
    {
        return $this->render('contract/index.html.twig');
    }

    #[Route('/nouveau', name: 'contract_new', methods: ['GET', 'POST'])]
    public function new(Request $request): Response
    {
        $form = $this->createForm(ContractType::class);
        return $this->render('contract/form.html.twig', ['form' => $form]);
    }

    #[Route('/{id<\\d+>}', name: 'contract_show', methods: ['GET'])]
    public function show(Contract $contract): Response
    {
        return $this->render('contract/show.html.twig');
    }

    #[Route('/{id<\\d+>}/resilier', name: 'contract_terminate', methods: ['POST'])]
    public function terminate(Contract $contract): Response
    {
        return $this->redirectToRoute('contract_show');
    }
}
"""

ROUTER = {
    "contract_index": {"path": "/contrats", "method": "GET",
                       "defaults": {"_controller": "App\\Controller\\ContractController::index"}},
    "contract_new": {"path": "/contrats/nouveau", "method": "GET|POST",
                     "defaults": {"_controller": "App\\Controller\\ContractController::new"}},
    "contract_show": {"path": "/contrats/{id}", "method": "GET",
                      "defaults": {"_controller": "App\\Controller\\ContractController::show"}},
    "contract_terminate": {"path": "/contrats/{id}/resilier", "method": "POST",
                           "defaults": {"_controller": "App\\Controller\\ContractController::terminate"}},
    "app_logout": {"path": "/deconnexion", "method": "GET",
                   "defaults": {"_controller": "App\\Controller\\SecurityController::logout"}},
}
CFG = {"global_pages": ["/contrats"], "params": {"id": "7"}, "max_pages": 4}


def app_tree(tmp_path):
    (tmp_path / "src/Controller").mkdir(parents=True)
    (tmp_path / "src/Form").mkdir(parents=True)
    (tmp_path / "templates/contract").mkdir(parents=True)
    (tmp_path / "src/Controller/ContractController.php").write_text(CONTROLLER, encoding="utf-8")
    (tmp_path / "src/Form/ContractType.php").write_text(
        "<?php\nnamespace App\\Form;\n\nclass ContractType extends AbstractType {}\n", encoding="utf-8")
    t = tmp_path / "templates"
    (t / "base.html.twig").write_text("<html>{% block body %}{% endblock %}</html>", encoding="utf-8")
    for name in ("index", "show", "form"):
        (t / f"contract/{name}.html.twig").write_text(
            "{% extends 'base.html.twig' %}{% import 'contract/_macros.html.twig' as m %}" if name != "form"
            else "{% extends 'base.html.twig' %}", encoding="utf-8")
    (t / "contract/_macros.html.twig").write_text("{% macro badge(s) %}{{ s }}{% endmacro %}", encoding="utf-8")
    return tmp_path, parse_routes(ROUTER)


def paths(pages):
    return [p.path for p in pages]


def test_only_interface_files_count():
    changed = ["src/Service/PremiumCalculator.php", "templates/contract/show.html.twig", "public/css/app.css",
               "composer.json", "src/Controller/ContractController.php", "tests/AppTest.php"]
    assert ui_files(changed) == ["templates/contract/show.html.twig", "public/css/app.css",
                                 "src/Controller/ContractController.php"]
    assert ui_files(["src/Service/PremiumCalculator.php", "composer.lock"]) == []
    assert ui_files(["web/a.css"], ["web/**"]) == ["web/a.css"]


def test_route_params_are_filled():
    assert fill("/contrats/{id}/modifier", {"id": "7"}) == "/contrats/7/modifier"
    assert fill("/a/{slug<[a-z]+>}/{page?1}", {}) == "/a/1/1"


def test_template_change_maps_to_the_page_that_renders_it(tmp_path):
    root, routes = app_tree(tmp_path)
    pages = choose_pages(root, {"templates/contract/show.html.twig": [3]}, routes, CFG)
    assert [(p.path, p.route) for p in pages] == [("/contrats/7", "contract_show")]
    assert pages[0].reason == "templates/contract/show.html.twig modifié"


def test_included_template_maps_to_every_page_that_imports_it(tmp_path):
    root, routes = app_tree(tmp_path)
    pages = choose_pages(root, {"templates/contract/_macros.html.twig": [1]}, routes, CFG)
    assert sorted(paths(pages)) == ["/contrats", "/contrats/7"]


def test_layout_css_and_unrendered_files_use_the_general_pages(tmp_path):
    root, routes = app_tree(tmp_path)
    assert paths(choose_pages(root, {"templates/base.html.twig": [1]}, routes, CFG)) == ["/contrats"]
    assert paths(choose_pages(root, {"public/css/app.css": None}, routes, CFG)) == ["/contrats"]


def test_a_blank_added_line_before_the_next_action_does_not_pull_it_in(tmp_path):
    root, routes = app_tree(tmp_path)
    lines = CONTROLLER.splitlines()
    blank_before_show = lines.index("    #[Route('/{id<\\d+>}', name: 'contract_show', methods: ['GET'])]")  # ligne vide au-dessus
    assert lines[blank_before_show - 1] == ""
    assert choose_pages(root, {"src/Controller/ContractController.php": [blank_before_show]}, routes, CFG) == []


def test_controller_change_only_pictures_the_get_actions_it_touches(tmp_path):
    root, routes = app_tree(tmp_path)
    show_line = CONTROLLER.splitlines().index("        return $this->render('contract/show.html.twig');") + 1
    term_line = CONTROLLER.splitlines().index("        return $this->redirectToRoute('contract_show');") + 1
    path = "src/Controller/ContractController.php"
    assert paths(choose_pages(root, {path: [show_line]}, routes, CFG)) == ["/contrats/7"]
    # Action POST seulement (résiliation) : rien de visible à photographier — y compris
    # ses attributs #[Route], qui précèdent la fonction (ils n'appartiennent pas à show()).
    attr_line = CONTROLLER.splitlines().index(
        "    #[Route('/{id<\\d+>}/resilier', name: 'contract_terminate', methods: ['POST'])]") + 1
    assert choose_pages(root, {path: [term_line]}, routes, CFG) == []
    assert choose_pages(root, {path: list(range(attr_line - 1, term_line + 2))}, routes, CFG) == []
    # Diff inconnu : toutes les pages GET du contrôleur, jamais la déconnexion.
    assert sorted(paths(choose_pages(root, {path: None}, routes, CFG))) == \
        ["/contrats", "/contrats/7", "/contrats/nouveau"]


def test_form_change_maps_to_the_actions_that_build_it(tmp_path):
    root, routes = app_tree(tmp_path)
    assert paths(choose_pages(root, {"src/Form/ContractType.php": [4]}, routes, CFG)) == ["/contrats/nouveau"]


def test_pages_are_capped_and_deduplicated(tmp_path):
    root, routes = app_tree(tmp_path)
    changed = {"templates/contract/show.html.twig": [1], "templates/contract/_macros.html.twig": [1],
               "src/Controller/ContractController.php": None}
    pages = choose_pages(root, changed, routes, {**CFG, "max_pages": 2})
    assert len(pages) == 2 and len(set(paths(pages))) == 2


PNG = base64.b64encode(b"\x89PNG fake").decode()


def test_split_page_keeps_images_out_of_events():
    meta, images = split_page({"path": "/contrats/7", "route": "contract_show", "reason": "x modifié",
                               "diff_pct": 3.5, "diff_png": PNG,
                               "before": {"status": 200, "final_path": "/contrats/7", "png": PNG, "error": ""},
                               "after": {"status": 200, "final_path": "/contrats/7", "png": PNG, "error": ""}})
    assert sorted(images) == ["after", "before", "diff"] and images["before"].startswith(b"\x89PNG")
    assert "png" not in json.dumps(meta).replace("images", "") and meta["after"]["image"] is True


def test_summary_section_lists_pages_without_images():
    preview = {"status": "ok", "pages": [
        {"path": "/contrats/7", "reason": "show modifié", "diff_pct": 4.2,
         "before": {"image": True, "status": 200}, "after": {"image": True, "status": 200}},
        {"path": "/contrats/nouveau", "reason": "form modifié", "diff_pct": None,
         "before": {"image": False}, "after": {"image": True, "status": 200}},
        {"path": "/contrats", "reason": "css modifié", "diff_pct": 0.0,
         "before": {"image": True}, "after": {"image": False, "error": "Timeout"}},
    ]}
    text = "\n".join(preview_rows(preview, "http://ui/runs/1"))
    assert "### Aperçu avant / après" in text and "4.2 % de la page a changé" in text
    assert "nouvelle page (absente avant)" in text and "page non affichée avec la PR" in text
    assert "voir dans l'interface](http://ui/runs/1)" in text
    assert preview_rows({"status": "off", "pages": []}) == []
    assert "aucun fichier d'interface modifié" in "\n".join(
        preview_rows({"status": "skipped", "message": "aucun fichier d'interface modifié", "pages": []}))


class PreviewGitHub(FakeGitHub):
    def __init__(self, files, config):
        super().__init__(files=files)
        self.config, self.tarballs = config, []

    async def get_pr(self, repo, number):
        return {**await super().get_pr(repo, number), "base": {"ref": "main", "sha": "b" * 40}}

    async def get_file(self, repo, path, ref, max_bytes=200_000):
        self.read = (path, ref)
        return self.config

    async def download_tarball(self, repo, sha, max_bytes):
        self.tarballs.append(sha)
        return b"tar-" + sha.encode()


class FakePreviewer:
    def __init__(self):
        self.calls = []

    async def preview(self, base, head, changed, cfg):
        self.calls.append((base, head, changed, cfg))
        return {"status": "ok", "message": "", "pages": [
            {"path": "/contrats/7", "route": "contract_show", "reason": "templates/contract/show.html.twig modifié",
             "diff_pct": 2.5, "diff_png": PNG,
             "before": {"status": 200, "final_path": "/contrats/7", "png": PNG, "error": ""},
             "after": {"status": 200, "final_path": "/contrats/7", "png": PNG, "error": ""}}]}


TWIG = {"filename": "templates/contract/show.html.twig", "status": "modified",
        "patch": "@@ -1,1 +1,2 @@\n a\n+<button>Supprimer</button>", "additions": 1, "deletions": 0}


def preview_services(tmp_path, files, config='{"global_pages": ["/contrats"]}', repos="calipso/app"):
    gh = PreviewGitHub(files, config)
    s = make(tmp_path, github=gh, PREVIEW_ENABLED=True, PREVIEW_REPOS=repos)
    s.previewer, s.events = FakePreviewer(), MemoryStore()
    return s, gh


async def test_ui_change_is_previewed_on_base_and_head_and_stored(tmp_path):
    s, gh = preview_services(tmp_path, [TWIG])
    result = await run_review({**JOB, "run_id": "r1"}, s)
    assert gh.read == (".github/pr-preview.json", "main")           # configuration lue sur la BASE
    assert gh.tarballs == ["b" * 40, JOB["head_sha"]]
    assert sorted(k[2] for k in s.events.previews) == ["after", "before", "diff"]
    pages = [e["data"] for e in s.events.events if e["type"] == "preview_page"]
    assert pages[0]["path"] == "/contrats/7" and pages[0]["idx"] == 0 and "png" not in json.dumps(pages)
    assert result["preview"]["status"] == "ok"
    assert "2.5 % de la page a changé" in gh.reviews[0]["body"]
    assert result["verdict"] == "CONTROLES_SATISFAITS"   # l'aperçu ne change jamais le verdict


async def test_no_preview_without_interface_change_or_for_other_repos(tmp_path):
    s, gh = preview_services(tmp_path, None)   # fichiers par défaut : src/Repo.php, composer.lock
    result = await run_review(JOB, s)
    assert s.previewer.calls == [] and result["preview"]["status"] == "skipped"
    assert "aucun fichier d'interface modifié" in result["preview"]["message"]

    s, gh = preview_services(tmp_path, [TWIG], repos="calipso/autre")
    result = await run_review(JOB, s)
    assert s.previewer.calls == [] and result["preview"]["status"] == "off"
    assert "Aperçu avant" not in gh.reviews[0]["body"]


async def test_missing_config_or_broken_previewer_never_fails_the_review(tmp_path):
    s, _ = preview_services(tmp_path, [TWIG], config=None)
    result = await run_review(JOB, s)
    assert result["preview"]["status"] == "skipped" and "pr-preview.json" in result["preview"]["message"]

    class Broken(FakePreviewer):
        async def preview(self, *a):
            raise ConnectionError("preview injoignable")

    s, _ = preview_services(tmp_path, [TWIG])
    s.previewer = Broken()
    result = await run_review(JOB, s)
    assert result["preview"]["status"] == "error" and result["verdict"] == "CONTROLES_SATISFAITS"
    assert not result.get("incomplete_reasons")


# ------------------------------------------------------------------ ce qui a changé, suggestions

from preview.changes import describe, text_changes  # noqa: E402

OK = {"status": 200, "png": b"x"}


def test_text_changes_lists_added_and_removed_lines():
    added, removed = text_changes("Contrats\n24 contrats affichés\nFiltrer", "Contrats\n24 contrat(s) affiché(s)\nFiltrer\nSupprimer")
    assert added == ["24 contrat(s) affiché(s)", "Supprimer"] and removed == ["24 contrats affichés"]


def test_describe_says_what_changed_in_plain_words():
    same = describe({**OK, "text": "A"}, {**OK, "text": "A"}, 0.0, [], 800)
    assert same["changed"] is False and same["kind"] == "none"
    text = describe({**OK, "text": "Modifier"}, {**OK, "text": "Modifier\nSupprimer"}, 0.6, [(900, 150, 1000, 200)], 800)
    assert text["kind"] == "content" and text["text_added"] == ["Supprimer"] and "1 ligne(s) de texte ajoutée(s)" in text["summary"]
    visual = describe({**OK, "text": "A"}, {**OK, "text": "A"}, 0.5, [(0, 10, 100, 50), (100, 500, 300, 560)], 800)
    assert visual["kind"] == "visual" and "sans changement de texte" in visual["summary"]
    assert visual["where"] == ["en-tête", "milieu de page"]
    err = describe({"status": 404, "png": b"x", "text": ""},
                   {"status": 500, "png": b"x", "text": "Symfony Exception\nAttempted to call an undefined method named \"x\""},
                   None, [], 0)
    assert err["kind"] == "error" and "erreur 500" in err["summary"] and "undefined method" in err["summary"]
    new = describe({"status": 404, "png": b"x"}, OK, None, [], 0)
    assert new["kind"] == "new"


class ChangedPreviewer(FakePreviewer):
    async def preview(self, base, head, changed, cfg):
        self.calls.append(1)
        return {"status": "ok", "message": "", "unchanged": [{"path": "/contrats", "reason": "x modifié"}], "pages": [
            {"path": "/contrats/7", "route": "contract_show", "reason": "templates/contract/show.html.twig modifié",
             "diff_pct": 0.6, "diff_png": PNG,
             "change": {"kind": "content", "summary": "Texte modifié : 1 ligne(s) de texte ajoutée(s).",
                        "text_added": ["Supprimer"], "text_removed": [], "zones": 1, "where": ["haut de page"]},
             "before": {"status": 200, "final_path": "/contrats/7", "png": PNG, "error": ""},
             "after": {"status": 200, "final_path": "/contrats/7", "png": PNG, "error": ""}}]}


class SuggestLLM:
    model, host = "fake-model", "localhost"

    def __init__(self):
        self.systems, self.users = [], []

    async def review(self, system, user):
        self.systems.append(system)
        self.users.append(user)
        if "À LA MAIN" in system:
            return [{"path": "/contrats/7", "line": 0, "severity": "info", "category": "tests",
                     "title": "Cliquer sur « Supprimer » en tant que lecteur : le bouton ne doit pas apparaître",
                     "explanation": "Nouveau bouton ajouté"},
                    {"path": "/page-inventee", "line": 0, "severity": "info", "category": "tests",
                     "title": "Vérifier la page inventée", "explanation": "x"}]
        return []


async def test_changed_pages_get_ai_suggestions_with_a_caveat(tmp_path):
    s, gh = preview_services(tmp_path, [TWIG])
    s.previewer, s.llm = ChangedPreviewer(), SuggestLLM()
    result = await run_review({**JOB, "run_id": "r2"}, s)
    pv = result["preview"]
    assert pv["unchanged"] == [{"path": "/contrats", "reason": "x modifié"}]
    assert pv["suggestions"][0]["page"] == "/contrats/7" and pv["suggestions"][1]["page"] == ""  # page inventée écartée
    prompt = next(u for sys_, u in zip(s.llm.systems, s.llm.users) if "À LA MAIN" in sys_)
    assert "Texte ajouté : Supprimer" in prompt and "show.html.twig" in prompt
    body = gh.reviews[0]["body"]
    assert "peut se tromper" in body and "aucun effet sur le verdict" in body
    assert "« Supprimer »" in body and "Ouvertes, rien de visible n'a changé : `/contrats`" in body
    assert "- [ ] Cliquer sur « Supprimer »" in body
    assert result["verdict"] == "CONTROLES_SATISFAITS"


async def test_failed_suggestions_keep_the_preview(tmp_path):
    class Down(SuggestLLM):
        async def review(self, system, user):
            if "À LA MAIN" in system:
                raise TimeoutError("lent")
            return []

    s, _ = preview_services(tmp_path, [TWIG])
    s.previewer, s.llm = ChangedPreviewer(), Down()
    result = await run_review(JOB, s)
    assert result["preview"]["status"] == "ok" and result["preview"]["suggestions"] == []
    assert result["preview"]["suggest_error"]
