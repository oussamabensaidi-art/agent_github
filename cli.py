"""Lancer une revue à la main, sans webhook (tests, pilote, calibrage des modèles).

    python cli.py owner/repo 42              # analyse + affichage, rien de publié
    python cli.py owner/repo 42 --publish    # publie aussi sur la PR

Mode token uniquement (GITHUB_AUTH_MODE=token + GITHUB_TOKEN), ou
--installation-id en mode app.
"""
import argparse
import asyncio
import json
import sys

from agent.runner import build_services, github_client_for, run_review
from config import settings


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("repo")
    p.add_argument("pr", type=int)
    p.add_argument("--publish", action="store_true")
    p.add_argument("--installation-id", type=int)
    args = p.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # console Windows (cp1252) : emojis du verdict

    settings.DRY_RUN = not args.publish
    github = await github_client_for(settings, args.installation_id)
    try:
        pr = await github.get_pr(args.repo, args.pr)
        job = {"delivery_id": "cli", "repo": args.repo, "pr_number": args.pr,
               "head_sha": pr["head"]["sha"], "installation_id": args.installation_id}
        result = await run_review(job, build_services(settings, github))
    finally:
        await github.aclose()

    if result.get("error"):
        print("ERREUR :", result["error"])
        return
    if result.get("stale"):
        print("PR modifiée pendant l'analyse : relancer.")
        return
    print(result["summary"])
    print("\n--- remarques ---")
    print(json.dumps([f.to_dict() for f in result["findings"]], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
