"""Journal d'audit : une ligne JSON par analyse (exigence "chaque analyse est journalisée").

Ne contient aucun code ni secret : métadonnées, compteurs, verdict, et l'hôte
du modèle (preuve que le code n'est pas sorti de l'infra).
"""
import json
import os
from datetime import datetime, timezone


class AuditLog:
    def __init__(self, path: str):
        self.path = path

    def write(self, record: dict) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        line = {"ts": datetime.now(timezone.utc).isoformat(), **record}
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")
