"""PR de test du banc e2e. Chaque PR vise un chemin précis du graphe."""

REPO = "calipso/e2e-app"
# Secret factice au format AWS : il ne doit JAMAIS ressortir (modèle, commentaires, mail, audit).
FAKE_AWS_KEY = "AKIA" + "QWERTYUIOPASDFGH"


def added_file(path: str, content: str, status: str = "added") -> dict:
    lines = content.rstrip("\n").split("\n")
    patch = f"@@ -0,0 +1,{len(lines)} @@\n" + "\n".join("+" + l for l in lines)
    return {"filename": path, "status": status, "patch": patch,
            "additions": len(lines), "deletions": 0, "changes": len(lines)}


VULNERABLE_CONTROLLER = f"""<?php

namespace App\\Controller;

use Doctrine\\DBAL\\Connection;
use Symfony\\Component\\HttpFoundation\\JsonResponse;
use Symfony\\Component\\HttpFoundation\\Request;
use Symfony\\Component\\Routing\\Attribute\\Route;

class ContractController
{{
    private const S3_KEY = '{FAKE_AWS_KEY}';

    public function __construct(private Connection $db) {{}}

    #[Route('/contracts/delete', methods: ['POST'])]
    public function delete(Request $request): JsonResponse
    {{
        $id = $request->get('id');
        $this->db->executeStatement("DELETE FROM contract WHERE id = " . $id);
        dump($id);

        return new JsonResponse(['ok' => true]);
    }}
}}
"""

CLEAN_SERVICE = """<?php

declare(strict_types=1);

namespace App\\Service;

final class PremiumCalculator
{
    public function monthly(float $annual): float
    {
        return round($annual / 12, 2);
    }
}
"""

CLEAN_TEST = """<?php

declare(strict_types=1);

namespace App\\Tests\\Service;

use App\\Service\\PremiumCalculator;
use PHPUnit\\Framework\\TestCase;

final class PremiumCalculatorTest extends TestCase
{
    public function testMonthlyIsRoundedToCents(): void
    {
        self::assertSame(83.33, (new PremiumCalculator())->monthly(1000.0));
    }
}
"""

HUGE_FILE = "<?php\n\nreturn [\n" + "\n".join(f"    'code_{i}' => 'Libellé {i}'," for i in range(2000)) + "\n];\n"

LOCK_CHANGE = {"filename": "composer.lock", "status": "modified",
               "patch": '@@ -10,1 +10,1 @@\n-    "content-hash": "aaa",\n+    "content-hash": "bbb",',
               "additions": 1, "deletions": 1, "changes": 2}


def _pr(number: int, title: str, sha: str, files: list[dict], body: str = "") -> dict:
    return {"number": number, "title": title, "body": body, "sha": sha, "files": files}


PRS = {
    101: _pr(101, "Suppression d'un contrat", "1" * 40,
             [added_file("src/Controller/ContractController.php", VULNERABLE_CONTROLLER), LOCK_CHANGE],
             "Ajoute une route pour supprimer un contrat."),
    102: _pr(102, "Calcul de la prime mensuelle", "2" * 40,
             [added_file("src/Service/PremiumCalculator.php", CLEAN_SERVICE),
              added_file("tests/Service/PremiumCalculatorTest.php", CLEAN_TEST)]),
    103: _pr(103, "Import du référentiel de codes", "3" * 40,
             [added_file("config/codes.php", HUGE_FILE),
              added_file("src/Service/PremiumCalculator.php", CLEAN_SERVICE)]),
    # 104 : le webhook annonce un ancien commit ; la PR a avancé depuis → job obsolète.
    104: _pr(104, "PR déjà repoussée", "4" * 40, [added_file("src/A.php", CLEAN_SERVICE)]),
}

# Ce que chaque scénario doit produire, indépendamment du modèle (verdict v2, mode pilote) :
#   verdicts = conclusions de check acceptables ; alert = True/False imposé, None = dépend du modèle.
# En mode pilote, l'IA ne peut jamais rendre une PR « bloquante » (failure) :
#   102 : success ou neutral, ou action_required si un lot échoue (petit modèle) ;
#   103 : fichier trop gros → toujours « analyse incomplète » (action_required), jamais success.
# La pertinence des remarques du modèle est rapportée, pas assertée.
EXPECTED = {
    101: {"verdicts": {"failure"}, "alert": True},                                   # secret → bloquante
    102: {"verdicts": {"success", "neutral", "action_required"}, "alert": False},
    103: {"verdicts": {"action_required"}, "alert": False},
    104: {"verdicts": {None}, "alert": False},                                       # obsolète → rien publié
}

# Attendu d'un bon relecteur sur #101, pour juger le modèle (rapport seulement).
REFERENCE_101 = {
    20: "injection SQL (concaténation de $id)",
    21: "dump() oublié",
    17: "route de suppression sans contrôle d'accès",
}

WEBHOOK_SHA = {104: "f" * 40}
