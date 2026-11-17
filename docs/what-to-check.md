# What to check in the interface (test of 16 Nov 2026)

Open http://localhost:8020/ui and sign in. The **Live** page lists the 9 test PRs on the left.
Click each one. At the top you see the **verdict** and **why**, then **remarks** on the left,
and **"What was checked"** on the right.

| Project | PR | What the change does | Expected verdict | What you should see |
|---|---|---|---|---|
| project_test_1 | #63 | Delete button for a contract | 🟠 À vérifier | AI security: "no right check on delete" and "no CSRF token" |
| project_test_1 | #65 | JSON export of totals | 🟠 À vérifier | PHPStan: "undefined method annualTotalCents()" |
| project_test_1 | #64 | Money formatting filter + test | 🟢 Contrôles satisfaits | No remarks, every check green |
| project_test_2 | #58 | CRM notification with a hard-coded API key | 🔴 Bloquante | "Secrets: 1 found"; the key is shown as `[SECRET MASQUÉ]`, never in clear |
| project_test_2 | #59 | Premium capping (min/max swapped) | 🔴 Bloquante | "CI du dépôt: en échec" (the repo's own tests fail) |
| project_test_2 | #57 | Button colour (CSS only) | 🟢 Contrôles satisfaits | No remarks; PHPStan and style "non applicable" |
| project_test_3 | #51 | Adds a vulnerable Guzzle version | 🔴 Bloquante | composer audit: "guzzlehttp/guzzle (14 security advisories)" |
| project_test_3 | #52 | Premium computed with floats | 🔴 Bloquante | AI: "float precision"; CI fails too |
| project_test_3 | #53 | Singular/plural label | 🟢 Contrôles satisfaits | No remarks |

## For each PR, check three things

1. **The verdict and its sentence make sense** for what the PR does.
2. **Each remark is true.** Click **Pertinente** if it is right, **Fausse alerte** if it is wrong.
   These clicks build the relevance rate on the **Statistiques** page.
3. **"What was checked"** is complete: files read, secrets, AI security, AI code & Symfony,
   gitleaks, composer audit, PHPStan, PHP-CS-Fixer, the repo's CI, GitHub, and email (for blocking PRs).

## Before / after screenshots (new, 17 Nov)

When a PR touches **interface files** (Twig templates, CSS/JS, controllers, forms), the agent itself
starts the app twice — on `main` ("Avant") and with the PR ("Après") — signs in with the test account,
and screenshots the pages those files affect. Only pages where something **actually changed** are shown,
with a sentence saying what changed (text added/removed, colour/layout, error, new page). Unchanged pages
are just listed. Then the AI reads the code change + those changes and suggests **what to check by hand**.

| PR | What "Ce qui change" should say | AI suggests (example) |
|---|---|---|
| project_test_1 #63 | `/contrats/1`: text added `+ Supprimer` | click "Supprimer" and check the contract is deleted |
| project_test_1 #64 | no pictures: "rien de visible n'a changé" on both pages | — |
| project_test_1 #65 | `/contrats/totaux.json`: error 500 "undefined method annualTotalCents" | open the JSON page; check the method exists |
| project_test_2 #57 | colour/layout change, no text change (buttons, links) | check the header colour, small screen |
| project_test_3 #53 | `− 24 contrat(s) affiché(s).` `+ 24 contrats affichés.` | check "1 contrat affiché" with one contract, and with 0 |
| #58, #59, #51, #52 | no panel: those PRs don't touch the interface | — |

**Don't expect too much from it.** It opens only a few pages, as one test user, with fake data. The
comparison can miss things, and the AI suggestions can be wrong or miss the real risk (on #63 it does not
think of checking that a *lecteur* can't delete). It is a reading aid, never a test, and never changes the verdict.

Click an image to enlarge it (Échap to close); **Différences** boxes the changed zones in red.

## Good to know

- 🔴 **Bloquante** only comes from automatic checks (secret, vulnerable dependency, failing CI).
  The AI alone gives 🟠 **À vérifier**: its remarks are advice (pilot mode).
- **Détails techniques** at the bottom is folded: graph, timeline, timings, model. Open it only if needed.
- Alert emails for the 4 blocking PRs are at http://localhost:8025 (test inbox).
- On GitHub, each PR has a **calipso-pr-review** check and a review comment from the bot.
