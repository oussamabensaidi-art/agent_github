"""Cas du banc « vrai GitHub » : chaque cas = une branche + une PR sur un dépôt de test.

Les dépôts test-agent-revue/project_test_{1,2,3} partent tous de la même base
(application Symfony « Portefeuille démo », données fictives).

Modifications :
  ("edit", chemin, ancien, nouveau)   remplacement exact, une seule occurrence
  ("new", chemin, contenu)            nouveau fichier
Attendus (vérité terrain, ce qu'un relecteur humain signalerait) :
  verdicts : verdicts acceptables
  find     : remarques attendues ; trouvée si une remarque retenue sur ce fichier,
             de gravité >= min, contient un des mots-clés (titre + explication),
             ou provient de la source indiquée (secret-scan).
"""
from pathlib import Path
from textwrap import dedent

R1, R2, R3 = "test-agent-revue/project_test_1", "test-agent-revue/project_test_2", "test-agent-revue/project_test_3"

CTRL = "src/Controller/ContractController.php"
REPO = "src/Repository/ContractRepository.php"
CALC = "src/Service/PremiumCalculator.php"
SHOW = "templates/contract/show.html.twig"
INDEX = "templates/contract/index.html.twig"
FTEST = "tests/Functional/ContractControllerTest.php"

ACCESS_KW = ["droit", "gestionnaire", "isgranted", "autoris", "accès", "acces", "permission", "rôle", "role",
             "csrf", "contrôle d'accès", "authentif"]

CASES: list[dict] = [
    # ------------------------------------------------------------------ défauts
    {
        "id": "D1-sql-injection", "repo": R1, "kind": "defect",
        "title": "Autocomplétion des références de contrat",
        "body": "Ajoute un point d'entrée JSON pour l'autocomplétion des références (champ de recherche).",
        "changes": [
            ("edit", REPO, """    /** Prochaine référence de l'année : CTR-2026-0001, CTR-2026-0002… */""",
             """    /**
     * Autocomplétion : contrats dont la référence commence par $prefix.
     *
     * @return list<array{id: int, reference: string, client_name: string}>
     */
    public function findByReferencePrefix(string $prefix): array
    {
        $sql = "SELECT id, reference, client_name FROM contract WHERE reference LIKE '".$prefix."%' ORDER BY reference LIMIT 10";

        return $this->getEntityManager()->getConnection()->executeQuery($sql)->fetchAllAssociative();
    }

    /** Prochaine référence de l'année : CTR-2026-0001, CTR-2026-0002… */"""),
            ("edit", CTRL, """    #[Route('/nouveau', name: 'contract_new', methods: ['GET', 'POST'])]""",
             """    #[Route('/autocompletion', name: 'contract_autocomplete', methods: ['GET'])]
    public function autocomplete(Request $request): Response
    {
        return $this->json($this->contracts->findByReferencePrefix($request->query->getString('ref')));
    }

    #[Route('/nouveau', name: 'contract_new', methods: ['GET', 'POST'])]"""),
        ],
        "expect": {"verdicts": ["A_VERIFIER", "BLOQUANTE"],
                   "find": [{"label": "injection SQL (concaténation)", "path": REPO, "min": "major",
                             "kw": ["sql", "injection", "concat", "paramètre", "parametre", "prepared", "préparée"]}]},
    },
    {
        "id": "D2-acces-suppression", "repo": R1, "kind": "defect",
        "title": "Suppression d'un contrat depuis sa fiche",
        "body": "Ajoute un bouton « Supprimer » sur la fiche contrat.",
        "changes": [
            ("edit", CTRL, """    #[Route('/{id<\\d+>}/resilier', name: 'contract_terminate', methods: ['POST'])]""",
             """    #[Route('/{id<\\d+>}/supprimer', name: 'contract_delete', methods: ['POST'])]
    public function delete(Contract $contract): Response
    {
        $reference = $contract->getReference();
        $this->em->remove($contract);
        $this->em->flush();
        $this->addFlash('success', sprintf('Contrat %s supprimé.', $reference));

        return $this->redirectToRoute('contract_index');
    }

    #[Route('/{id<\\d+>}/resilier', name: 'contract_terminate', methods: ['POST'])]"""),
            ("edit", SHOW, """                    <button type="submit" class="btn btn-danger">Résilier</button>
                </form>""", """                    <button type="submit" class="btn btn-danger">Résilier</button>
                </form>
                <form method="post" action="{{ path('contract_delete', {id: contract.id}) }}">
                    <button type="submit" class="btn btn-danger">Supprimer</button>
                </form>"""),
        ],
        "expect": {"verdicts": ["A_VERIFIER", "BLOQUANTE"],
                   "find": [{"label": "route de suppression sans contrôle de droits", "path": CTRL, "min": "major",
                             "kw": ACCESS_KW}]},
    },
    {
        "id": "D3-dump-oublie", "repo": R2, "kind": "defect",
        "title": "Création de contrat : message de confirmation détaillé",
        "body": "Le message de confirmation indique maintenant la prime calculée.",
        "changes": [
            ("edit", CTRL, """            $this->em->persist($contract);
            $this->em->flush();
            $this->addFlash('success', sprintf('Contrat %s créé.', $contract->getReference()));""",
             """            dump($contract);
            $this->em->persist($contract);
            $this->em->flush();
            $this->addFlash('success', sprintf('Contrat %s créé, prime HT %s €.', $contract->getReference(),
                number_format($contract->getPremiumCents() / 100, 2, ',', ' ')));"""),
        ],
        "expect": {"verdicts": ["A_VERIFIER", "BLOQUANTE"],
                   "find": [{"label": "dump() oublié", "path": CTRL, "min": "major", "kw": ["dump", "débogage", "debug"]}]},
    },
    {
        "id": "D4-secret-en-dur", "repo": R2, "kind": "defect",
        "title": "Notification du CRM à la création d'un contrat",
        "body": "Envoie la référence du nouveau contrat au CRM.",
        "changes": [
            ("new", "src/Service/CrmNotifier.php", dedent("""\
                <?php

                declare(strict_types=1);

                namespace App\\Service;

                use App\\Entity\\Contract;
                use Symfony\\Contracts\\HttpClient\\HttpClientInterface;

                final class CrmNotifier
                {
                    private const CRM_URL = 'https://crm.exemple.invalid/api/contrats';
                    private const CRM_API_KEY = 'crm_live_9f8a7c6d5e4b3a2f1e0d4c5b';

                    public function __construct(private readonly HttpClientInterface $http)
                    {
                    }

                    public function contractCreated(Contract $contract): void
                    {
                        $this->http->request('POST', self::CRM_URL, [
                            'headers' => ['X-Api-Key' => self::CRM_API_KEY],
                            'json' => ['reference' => $contract->getReference()],
                            'timeout' => 5,
                        ]);
                    }
                }
                """)),
        ],
        "expect": {"verdicts": ["BLOQUANTE"],
                   "find": [{"label": "clé d'API en dur (détection déterministe)", "path": "src/Service/CrmNotifier.php",
                             "min": "critical", "source": "secret-scan"}]},
    },
    {
        "id": "D5-montant-flottant", "repo": R3, "kind": "defect",
        "title": "Calcul de prime : simplification",
        "body": "Simplifie le calcul de la prime en utilisant directement le taux décimal.",
        "changes": [
            ("edit", CALC, """        // CA en centimes × taux en points de base / 10 000, arrondi au centime le plus proche.
        $computed = intdiv($annualRevenueEuros * 100 * $product->rateBasisPoints() + 5_000, 10_000);""",
             """        $rate = $product->rateBasisPoints() / 10000; // ex. 0.018 pour 1,8 %
        $computed = (int) ($annualRevenueEuros * $rate * 100);"""),
        ],
        "expect": {"verdicts": ["A_VERIFIER", "BLOQUANTE"],
                   "find": [{"label": "flottant + troncature au lieu d'arrondi", "path": CALC, "min": "minor",
                             "kw": ["float", "flottant", "arrondi", "troncat", "round", "précision", "precision",
                                    "centime", "(int)", "cast", "décimal", "decimal"]}]},
    },
    {
        "id": "D6-reference-dupliquee", "repo": R3, "kind": "defect",
        "title": "Références de contrat : lecture du dernier numéro",
        "body": "Nettoie la lecture du dernier numéro de référence.",
        "changes": [
            ("edit", REPO, """        $next = $last ? ((int) substr($last, strlen($prefix))) + 1 : 1;""",
             """        $next = $last ? (int) substr($last, strlen($prefix)) : 1;"""),
        ],
        "expect": {"verdicts": ["A_VERIFIER", "BLOQUANTE"],
                   "find": [{"label": "référence suivante non incrémentée (doublon)", "path": REPO, "min": "minor",
                             "kw": ["+1", "+ 1", "doublon", "duplicate", "dupliqu", "unique", "incrément", "increment",
                                    "même référence", "meme reference", "suivant", "collision"]}]},
    },
    {
        "id": "D7-xss-raw", "repo": R1, "kind": "defect",
        "title": "Fiche contrat : autoriser la mise en forme du nom du client",
        "body": "Certains clients ont des noms avec mise en forme (gras) saisie par les gestionnaires.",
        "changes": [
            ("edit", SHOW, """            <h1>{{ contract.clientName }}</h1>""", """            <h1>{{ contract.clientName|raw }}</h1>"""),
        ],
        "expect": {"verdicts": ["A_VERIFIER", "BLOQUANTE"],
                   "find": [{"label": "|raw sur une donnée saisie (XSS)", "path": SHOW, "min": "major",
                             "kw": ["raw", "xss", "échapp", "echapp", "injection", "html", "script"]}]},
    },
    {
        "id": "D8-secret-description", "repo": R3, "kind": "defect",
        "title": "Fiche contrat : libellé de la date d'effet",
        "body": "Libellé plus clair.\n\nPour tester en recette avec le CRM : password = \"Rct-2026!crm#9f8a7c\"",
        "changes": [
            ("edit", SHOW, """<p class="muted">{{ contract.product.label }} · effet au {{ contract.startDate|date('d/m/Y') }}</p>""",
             """<p class="muted">{{ contract.product.label }} · date d’effet : {{ contract.startDate|date('d/m/Y') }}</p>"""),
        ],
        "expect": {"verdicts": ["BLOQUANTE"],
                   "find": [{"label": "mot de passe dans la description de la PR", "path": "(titre / description de la PR)",
                             "min": "critical", "source": "secret-scan"}]},
    },
    # ------------------------------------------------------------------ propres
    {
        "id": "C1-export-csv", "repo": R2, "kind": "clean",
        "title": "Export CSV du portefeuille (gestionnaires)",
        "body": "Ajoute un export CSV des contrats, réservé aux gestionnaires, avec tests.",
        "changes": [
            ("edit", CTRL, """use Symfony\\Component\\HttpFoundation\\Response;""",
             """use Symfony\\Component\\HttpFoundation\\Response;
use Symfony\\Component\\HttpFoundation\\StreamedResponse;"""),
            ("edit", CTRL, """    #[Route('/nouveau', name: 'contract_new', methods: ['GET', 'POST'])]""",
             """    #[Route('/export.csv', name: 'contract_export', methods: ['GET'])]
    #[IsGranted('ROLE_GESTIONNAIRE')]
    public function export(): StreamedResponse
    {
        $contracts = $this->contracts->findBy([], ['reference' => 'ASC']);
        $response = new StreamedResponse(static function () use ($contracts): void {
            $out = fopen('php://output', 'w');
            fputcsv($out, ['reference', 'client', 'produit', 'prime_ht_centimes', 'statut'], ';', '"', '');
            foreach ($contracts as $c) {
                fputcsv($out, [$c->getReference(), $c->getClientName(), $c->getProduct()?->value,
                    $c->getPremiumCents(), $c->getStatus()->value], ';', '"', '');
            }
            fclose($out);
        });
        $response->headers->set('Content-Type', 'text/csv; charset=UTF-8');
        $response->headers->set('Content-Disposition', 'attachment; filename="contrats.csv"');

        return $response;
    }

    #[Route('/nouveau', name: 'contract_new', methods: ['GET', 'POST'])]"""),
            ("edit", FTEST, """    public function testSearchIsNotInjectable(): void""",
             """    public function testExportIsReservedToManagers(): void
    {
        $this->loginAs('lecteur');
        $this->client->request('GET', '/contrats/export.csv');
        self::assertResponseStatusCodeSame(403);

        $this->loginAs('gestionnaire');
        $this->client->request('GET', '/contrats/export.csv');
        self::assertResponseIsSuccessful();
        self::assertResponseHeaderSame('Content-Type', 'text/csv; charset=UTF-8');
        $lines = array_filter(explode("\\n", $this->client->getInternalResponse()->getContent()));
        self::assertCount(25, $lines);
        self::assertStringStartsWith('reference;client;', $lines[0]);
    }

    public function testSearchIsNotInjectable(): void"""),
        ],
        "expect": {"verdicts": ["CONTROLES_SATISFAITS", "A_VERIFIER"], "find": []},
    },
    {
        "id": "C2-liste-pluriel", "repo": R3, "kind": "clean",
        "title": "Liste des contrats : accord du compteur",
        "body": "Accorde « contrat(s) affiché(s) » au singulier et au pluriel.",
        "changes": [
            ("edit", INDEX, """    <p class="muted small">{{ contracts|length }} contrat(s) affiché(s).</p>""",
             """    {% set n = contracts|length %}
    <p class="muted small">{{ n }} contrat{{ n > 1 ? 's' }} affiché{{ n > 1 ? 's' }}.</p>"""),
        ],
        "expect": {"verdicts": ["CONTROLES_SATISFAITS", "A_VERIFIER"], "find": []},
    },
    {
        "id": "C3-filtre-twig-money", "repo": R1, "kind": "clean",
        "title": "Montants : filtre Twig `money` testé",
        "body": "Remplace le formatage des montants du macro par un filtre Twig testé unitairement.",
        "changes": [
            ("new", "src/Twig/MoneyExtension.php", dedent("""\
                <?php

                declare(strict_types=1);

                namespace App\\Twig;

                use Twig\\Extension\\AbstractExtension;
                use Twig\\TwigFilter;

                /** Formate un montant en centimes : 123456 → « 1 234,56 € ». */
                final class MoneyExtension extends AbstractExtension
                {
                    public function getFilters(): array
                    {
                        return [new TwigFilter('money', $this->format(...))];
                    }

                    public function format(int $cents): string
                    {
                        $sign = $cents < 0 ? '-' : '';
                        $cents = abs($cents);

                        return sprintf('%s%s,%02d €', $sign, number_format(intdiv($cents, 100), 0, ',', ' '), $cents % 100);
                    }
                }
                """)),
            ("new", "tests/Unit/MoneyExtensionTest.php", dedent("""\
                <?php

                declare(strict_types=1);

                namespace App\\Tests\\Unit;

                use App\\Twig\\MoneyExtension;
                use PHPUnit\\Framework\\TestCase;

                final class MoneyExtensionTest extends TestCase
                {
                    public function testFormat(): void
                    {
                        $ext = new MoneyExtension();
                        self::assertSame('0,00 €', $ext->format(0));
                        self::assertSame('0,05 €', $ext->format(5));
                        self::assertSame('1 234,56 €', $ext->format(123456));
                        self::assertSame('-12,30 €', $ext->format(-1230));
                    }
                }
                """)),
            ("edit", "templates/contract/_macros.html.twig",
             """{% macro money(cents) %}{{ (cents / 100)|number_format(2, ',', ' ') }} €{% endmacro %}""",
             """{% macro money(cents) %}{{ cents|money }}{% endmacro %}"""),
        ],
        "expect": {"verdicts": ["CONTROLES_SATISFAITS", "A_VERIFIER"], "find": []},
    },
    # ------------------------------------------------------------------ limite
    {
        "id": "E1-gros-fichier", "repo": R2, "kind": "edge",
        "title": "Jeu de données de recette 2025",
        "body": "Ajoute l'export du portefeuille 2025 utilisé pour les tests de charge.",
        "changes": [
            ("new", "tests/fixtures/portefeuille_2025.csv",
             "reference;client;produit;prime_ht_centimes;statut\n" + "".join(
                 f"CTR-2025-{i:05d};Client fictif {i};{['decennale', 'rc_pro', 'multirisque', 'flotte_auto'][i % 4]};"
                 f"{45000 + (i * 7919) % 900000};{'actif' if i % 9 else 'resilie'}\n" for i in range(1, 6001))),
        ],
        "expect": {"verdicts": ["ANALYSE_INCOMPLETE"], "find": []},
    },
]

# ---------------------------------------------------------------------- suite « static »
# Contrôles déterministes (conteneur checker + CI du dépôt) : python run_bench.py ... --suite static
FIXTURES = Path(__file__).resolve().parent / "fixtures"
CI_PATH = "(intégration continue)"

STATIC_CASES: list[dict] = [
    {
        "id": "S1-phpstan-methode", "repo": R1, "kind": "defect", "suite": "static",
        "title": "Export JSON des totaux annuels",
        "body": "Ajoute un point d'entrée JSON avec le total annuel de chaque contrat.",
        "changes": [
            ("edit", CTRL, """    #[Route('/nouveau', name: 'contract_new', methods: ['GET', 'POST'])]""",
             """    #[Route('/totaux.json', name: 'contract_totals', methods: ['GET'])]
    public function totals(): Response
    {
        $totals = [];
        foreach ($this->contracts->findAll() as $contract) {
            $totals[$contract->getReference()] = $this->calculator->annualTotalCents($contract);
        }

        return $this->json($totals);
    }

    #[Route('/nouveau', name: 'contract_new', methods: ['GET', 'POST'])]"""),
        ],
        "expect": {"verdicts": ["A_VERIFIER", "BLOQUANTE"],
                   "find": [{"label": "méthode inexistante (PHPStan)", "path": CTRL, "min": "major",
                             "source": "phpstan"}]},
    },
    {
        "id": "S2-ci-en-echec", "repo": R2, "kind": "defect", "suite": "static",
        "title": "Calcul de prime : plafonnement",
        "body": "La prime ne dépasse plus le montant de référence du produit.",
        "changes": [
            ("edit", CALC, """        return max($computed, $product->minimumPremiumCents());""",
             """        return min($computed, $product->minimumPremiumCents());"""),
        ],
        "expect": {"verdicts": ["BLOQUANTE"],
                   "find": [{"label": "tests en échec dans la CI", "path": CI_PATH, "min": "critical", "source": "ci"}]},
    },
    {
        "id": "S3-dependance-vulnerable", "repo": R3, "kind": "defect", "suite": "static",
        "title": "Ajout du client HTTP Guzzle",
        "body": "Ajoute guzzlehttp/guzzle pour les futurs appels au CRM.",
        "changes": [
            ("new", "composer.json", (FIXTURES / "s3" / "composer.json").read_text(encoding="utf-8")),
            ("new", "composer.lock", (FIXTURES / "s3" / "composer.lock").read_text(encoding="utf-8")),
        ],
        "expect": {"verdicts": ["BLOQUANTE"],
                   "find": [{"label": "dépendance vulnérable (composer audit)", "path": "composer.lock",
                             "min": "critical", "source": "composer-audit"}]},
    },
    {
        "id": "S4-style", "repo": R1, "kind": "defect", "suite": "static",
        "title": "Prime mensuelle",
        "body": "Ajoute le calcul de la prime mensuelle.",
        "changes": [
            ("edit", CALC, """    public function taxCents(int $premiumCents): int""",
             """    public function monthlyCents( int $premiumCents ) : int {
        return intdiv( $premiumCents , 12 );
    }

    public function taxCents(int $premiumCents): int"""),
        ],
        "expect": {"verdicts": ["CONTROLES_SATISFAITS", "A_VERIFIER"],
                   "find": [{"label": "style non conforme (PHP-CS-Fixer)", "path": CALC, "min": "minor",
                             "source": "php-cs-fixer"}]},
    },
    {
        "id": "S5-propre-php", "repo": R2, "kind": "clean", "suite": "static",
        "title": "Montants : filtre Twig `money` testé",
        "body": "Remplace le formatage des montants du macro par un filtre Twig testé unitairement.",
        "changes": next(c["changes"] for c in CASES if c["id"] == "C3-filtre-twig-money"),
        "expect": {"verdicts": ["CONTROLES_SATISFAITS", "A_VERIFIER"], "find": []},
    },
]

ALL_CASES = CASES + STATIC_CASES
