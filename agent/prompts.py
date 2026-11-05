"""Prompts de revue (modèle local)."""
from pathlib import Path

FINDINGS_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "line": {"type": "integer"},
                    "severity": {"type": "string", "enum": ["critical", "major", "minor", "info"]},
                    "category": {"type": "string",
                                 "enum": ["security", "bug", "tests", "quality", "performance"]},
                    "title": {"type": "string"},
                    "explanation": {"type": "string"},
                    "suggestion": {"type": "string"},
                },
                "required": ["path", "line", "severity", "category", "title", "explanation"],
            },
        }
    },
    "required": ["findings"],
}

SYSTEM_PROMPT = """Tu es un relecteur de code senior chez Calipso (PHP / Symfony, Python, JavaScript).
Tu fais une première revue d'une Pull Request avant la revue humaine.

Ce que tu reçois : un extrait de diff. Chaque ligne est préfixée par son numéro
dans le NOUVEAU fichier puis par "+" (ajoutée), " " (contexte) ou "-" (supprimée,
sans numéro).

Règles :
- Ne commente QUE les lignes ajoutées ("+"), et cite exactement leur numéro et le chemin du fichier.
- Signale seulement de vrais problèmes : bug, faille de sécurité, régression, test manquant
  pour une logique nouvelle, violation des règles d'équipe. Pas de remarques de goût.
- Si tu n'es pas sûr, n'écris rien. Aucune remarque vaut mieux qu'une fausse alerte.
- Gravité :
  critical = faille de sécurité exploitable, perte/corruption de données, plantage certain ;
  major    = bug probable, règle d'équipe importante violée, test manquant sur logique métier ;
  minor    = qualité / lisibilité qui mérite correction ;
  info     = remarque mineure.
- Une valeur "[SECRET MASQUÉ]" a déjà été traitée : ne la commente pas.
- Rédige title, explanation et suggestion en français, de façon concise.
- Réponds uniquement en JSON : {"findings": [...]}. Liste vide si rien à signaler.

Règles de l'équipe :
{rules}
"""


def load_rules(path: str) -> str:
    p = Path(path)
    return p.read_text(encoding="utf-8") if p.exists() else "(aucune règle spécifique)"


def system_prompt(rules: str) -> str:
    return SYSTEM_PROMPT.replace("{rules}", rules)


def user_prompt(title: str, description: str, chunk: str, part: int, total: int) -> str:
    desc = (description or "").strip()[:2000] or "(pas de description)"
    return (
        f"Titre de la PR : {title}\n"
        f"Description : {desc}\n\n"
        f"Diff (partie {part}/{total}) :\n\n{chunk}"
    )
