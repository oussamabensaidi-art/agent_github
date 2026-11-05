"""Alerte email quand une PR est bloquante.

Le mail ne contient que des métadonnées (dépôt, PR, titres des remarques) :
jamais d'extrait de code ni de secret.
"""
import asyncio
import smtplib
from email.message import EmailMessage

from agent.review import SEVERITY_LABEL, Finding


def build_alert(sender: str, recipients: list[str], repo: str, number: int, title: str,
                author: str, url: str, findings: list[Finding]) -> EmailMessage:
    blocking = [f for f in findings if f.severity == "critical"]
    msg = EmailMessage()
    msg["Subject"] = f"[PR bloquante] {repo}#{number} — {title[:120]}"
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    lines = [
        f"La revue automatique a jugé la PR {repo}#{number} bloquante.",
        "",
        f"Titre  : {title}",
        f"Auteur : {author}",
        f"Lien   : {url}",
        "",
        f"{len(blocking)} remarque(s) bloquante(s) :",
    ]
    for f in blocking:
        where = f"{f.path}" + (f":{f.line}" if f.line else "")
        lines.append(f"  - [{SEVERITY_LABEL[f.severity]}] {where} — {f.title}")
    lines += ["", "Le détail est dans les commentaires de la PR. La fusion reste une décision humaine."]
    msg.set_content("\n".join(lines))
    return msg


class Mailer:
    def __init__(self, host: str, port: int, user: str, password: str, starttls: bool):
        self.host, self.port, self.user, self.password, self.starttls = host, port, user, password, starttls

    @property
    def configured(self) -> bool:
        return bool(self.host)

    def _send(self, msg: EmailMessage) -> None:
        with smtplib.SMTP(self.host, self.port, timeout=20) as s:
            if self.starttls:
                s.starttls()
            if self.user:
                s.login(self.user, self.password)
            s.send_message(msg)

    async def send(self, msg: EmailMessage) -> None:
        await asyncio.to_thread(self._send, msg)
