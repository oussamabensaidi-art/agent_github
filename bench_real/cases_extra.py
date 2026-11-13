"""Cas supplémentaires du banc (suite « extra ») : 9 défauts + 4 PR propres.

Avec les 12 cas de base et les 5 cas « static », le banc compte 30 PR.
Même format que cases.py.
"""
from textwrap import dedent

R1, R2, R3 = "test-agent-revue/project_test_1", "test-agent-revue/project_test_2", "test-agent-revue/project_test_3"
CTRL = "src/Controller/ContractController.php"
REPO = "src/Repository/ContractRepository.php"
CALC = "src/Service/PremiumCalculator.php"
ACCESS_KW = ["droit", "gestionnaire", "isgranted", "autoris", "accès", "acces", "permission", "rôle", "role",
             "role_user", "contrôle d'accès", "authentif"]
NEW_ROUTE = """    #[Route('/nouveau', name: 'contract_new', methods: ['GET', 'POST'])]"""
PERSIST = """            $this->em->persist($contract);
            $this->em->flush();
            $this->addFlash('success', sprintf('Contrat %s créé.', $contract->getReference()));"""
DEFECT = ["A_VERIFIER", "BLOQUANTE"]
CLEAN = ["CONTROLES_SATISFAITS", "A_VERIFIER"]


def case(id_, repo, kind, title, body, changes, verdicts, find=()):
    return {"id": id_, "repo": repo, "kind": kind, "suite": "extra", "title": title, "body": body,
            "changes": changes, "expect": {"verdicts": verdicts, "find": list(find)}}


EXTRA_CASES: list[dict] = [
    case("X1-redirection-ouverte", R1, "defect", "Résiliation : retour à la page d'origine",
         "Après une résiliation, on revient à la page d'où l'on venait (paramètre `retour`).",
         [("edit", CTRL, """            $this->addFlash('success', sprintf('Contrat %s résilié.', $contract->getReference()));
        }

        return $this->redirectToRoute('contract_show', ['id' => $contract->getId()]);""",
           """            $this->addFlash('success', sprintf('Contrat %s résilié.', $contract->getReference()));
        }

        return $this->redirect($request->query->getString('retour', '/contrats'));""")],
         DEFECT, [{"label": "redirection ouverte (URL fournie par l'utilisateur)", "path": CTRL, "min": "major",
                   "kw": ["redirect", "redirection", "ouverte", "open", "url", "phishing", "hameçon"]}]),

    case("X2-csrf-retire", R2, "defect", "Résiliation : simplification du contrôleur",
         "Retire une vérification redondante dans l'action de résiliation.",
         [("edit", CTRL, """        if (!$this->isCsrfTokenValid('terminate'.$contract->getId(), $request->getPayload()->getString('_token'))) {
            throw $this->createAccessDeniedException('Jeton CSRF invalide.');
        }

""", "")],
         DEFECT, [{"label": "vérification CSRF supprimée", "path": CTRL, "min": "major",
                   "kw": ["csrf", "jeton", "token"]}]),

    case("X3-droit-abaisse", R3, "defect", "Modification d'un contrat : harmonisation des droits",
         "Harmonise l'attribut de droits de l'action de modification.",
         [("edit", CTRL, """    #[Route('/{id<\\d+>}/modifier', name: 'contract_edit', methods: ['GET', 'POST'])]
    #[IsGranted('ROLE_GESTIONNAIRE')]""", """    #[Route('/{id<\\d+>}/modifier', name: 'contract_edit', methods: ['GET', 'POST'])]
    #[IsGranted('ROLE_USER')]""")],
         DEFECT, [{"label": "modification ouverte aux lecteurs (ROLE_USER)", "path": CTRL, "min": "major",
                   "kw": ACCESS_KW}]),

    case("X4-donnees-dans-les-logs", R1, "defect", "Création de contrat : trace de diagnostic",
         "Ajoute une trace pour diagnostiquer les créations de contrat.",
         [("edit", CTRL, PERSIST, """            error_log(sprintf('Contrat créé pour %s (SIREN %s, CA %d €)', $contract->getClientName(),
                $contract->getSiren(), $contract->getAnnualRevenue()));
""" + PERSIST)],
         DEFECT, [{"label": "données du client écrites dans les logs", "path": CTRL, "min": "minor",
                   "kw": ["log", "journal", "données", "donnees", "personnel", "siren", "error_log", "sensible"]}]),

    case("X5-exception-avalee", R2, "defect", "Création de contrat : ne plus afficher d'erreur technique",
         "Évite la page d'erreur si l'enregistrement échoue.",
         [("edit", CTRL, PERSIST, """            try {
                $this->em->persist($contract);
                $this->em->flush();
            } catch (\\Exception $e) {
            }
            $this->addFlash('success', sprintf('Contrat %s créé.', $contract->getReference()));""")],
         DEFECT, [{"label": "exception avalée (catch vide), succès affiché à tort", "path": CTRL, "min": "major",
                   "kw": ["catch", "exception", "aval", "silenc", "vide", "ignor", "erreur"]}]),

    case("X6-comparaison-hmac", R3, "defect", "Vérification de la signature des webhooks du CRM",
         "Ajoute un service qui vérifie la signature HMAC des webhooks entrants.",
         [("new", "src/Service/WebhookVerifier.php", dedent("""\
            <?php

            declare(strict_types=1);

            namespace App\\Service;

            final class WebhookVerifier
            {
                public function __construct(private readonly string $secret)
                {
                }

                public function isValid(string $payload, string $signature): bool
                {
                    return hash_hmac('sha256', $payload, $this->secret) == $signature;
                }
            }
            """))],
         DEFECT, [{"label": "signature comparée avec == au lieu de hash_equals()", "path": "src/Service/WebhookVerifier.php",
                   "min": "major", "kw": ["hash_equals", "timing", "temporel", "==", "comparaison", "temps constant"]}]),

    case("X7-unserialize", R1, "defect", "Import de contrats par lot",
         "Point d'entrée d'import par lot pour les gestionnaires.",
         [("edit", CTRL, NEW_ROUTE, """    #[Route('/import', name: 'contract_import', methods: ['POST'])]
    #[IsGranted('ROLE_GESTIONNAIRE')]
    public function import(Request $request): Response
    {
        $rows = unserialize($request->getContent());

        return $this->json(['lignes' => is_array($rows) ? count($rows) : 0]);
    }

""" + NEW_ROUTE)],
         DEFECT, [{"label": "unserialize() sur le corps de la requête", "path": CTRL, "min": "major",
                   "kw": ["unserialize", "désérialis", "deserialis", "injection d'objet", "object injection"]}]),

    case("X8-logique-sans-test", R2, "defect", "Remboursement au prorata",
         "Calcule le remboursement au prorata des jours restants lors d'une résiliation.",
         [("edit", CALC, """    public function totalCents(int $premiumCents): int""",
           """    /** Remboursement au prorata des jours restants en cas de résiliation. */
    public function refundCents(int $premiumCents, int $daysRemaining): int
    {
        if ($daysRemaining <= 0) {
            return 0;
        }

        return intdiv($premiumCents * min($daysRemaining, 365), 365);
    }

    public function totalCents(int $premiumCents): int""")],
         DEFECT, [{"label": "nouvelle logique métier sans test", "path": CALC, "min": "major", "kw": ["test"]}]),

    case("X9-dql-concatene", R3, "defect", "Recherche : simplification de la requête",
         "Simplifie la construction de la requête de recherche.",
         [("edit", REPO, """            $qb->andWhere('LOWER(c.clientName) LIKE :q OR LOWER(c.reference) LIKE :q OR c.siren LIKE :q')
                ->setParameter('q', '%'.mb_strtolower($query).'%');""",
           """            $qb->andWhere("LOWER(c.clientName) LIKE '%".mb_strtolower($query)."%' OR c.siren LIKE '%".$query."%'");""")],
         DEFECT, [{"label": "DQL construite par concaténation (injection)", "path": REPO, "min": "major",
                   "kw": ["injection", "concat", "paramètre", "parametre", "dql", "sql", "lié"]}]),

    # ------------------------------------------------------------------ propres
    case("K1-doc-readme", R1, "clean", "README : précisions sur les comptes de test",
         "Documentation uniquement.",
         [("edit", "README.md", """## Tests
""", """Les deux comptes sont déclarés en mémoire : aucune inscription n'est possible.

## Tests
""")], CLEAN),

    case("K2-couleur-css", R2, "clean", "Interface : bleu principal légèrement plus foncé",
         "Meilleur contraste des boutons principaux.",
         [("edit", "public/css/app.css", """  --primary: #1f4fd1;""", """  --primary: #1b46bd;""")], CLEAN),

    case("K3-constantes-arrondi", R3, "clean", "Calcul de taxe : constantes nommées",
         "Remplace deux nombres magiques par des constantes. Aucun changement de comportement, tests existants inchangés.",
         [("edit", CALC, """    public const TAX_BASIS_POINTS = 900;""", """    public const TAX_BASIS_POINTS = 900;
    private const BASIS_POINTS = 10_000;
    private const HALF_BASIS_POINT = 5_000;"""),
          ("edit", CALC, """        return intdiv($premiumCents * self::TAX_BASIS_POINTS + 5_000, 10_000);""",
           """        return intdiv($premiumCents * self::TAX_BASIS_POINTS + self::HALF_BASIS_POINT, self::BASIS_POINTS);""")],
         CLEAN),

    case("K4-test-supplementaire", R1, "clean", "Tests : cas « multirisque au minimum »",
         "Ajoute un cas de test sur la prime minimale du produit multirisque.",
         [("edit", "tests/Unit/PremiumCalculatorTest.php",
           """        yield 'flotte juste sous le minimum' => [Product::FlotteAuto, 74_999, 90_000];""",
           """        yield 'flotte juste sous le minimum' => [Product::FlotteAuto, 74_999, 90_000];
        yield 'multirisque au minimum' => [Product::Multirisque, 1_000, 25_000];""")], CLEAN),
]
