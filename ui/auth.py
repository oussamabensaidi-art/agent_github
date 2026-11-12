"""Authentification de l'interface de suivi.

Comptes déclarés dans UI_USERS ("login:role:empreinte", séparés par des virgules),
role = admin | lecteur. Empreinte scrypt (bibliothèque standard) :

    python -m ui.auth              # demande le mot de passe, affiche l'empreinte
    python -m ui.auth --generate   # génère un mot de passe aléatoire et son empreinte

Sessions côté serveur (Redis), cookie HttpOnly SameSite=Strict. Toute requête
qui modifie quelque chose exige l'en-tête X-Requested-With (anti-CSRF).
"""
import hashlib
import hmac
import json
import secrets
import sys

from fastapi import HTTPException, Request

COOKIE = "prreview_session"
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "calipso-ui"
ROLES = {"admin", "lecteur"}
_N, _R, _P = 2 ** 14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt.{_N}.{_R}.{_P}.{salt.hex()}.{digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, n, r, p, salt, digest = encoded.split(".")
        if algo != "scrypt":
            return False
        got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p),
                             dklen=len(bytes.fromhex(digest)))
        return hmac.compare_digest(got.hex(), digest)
    except (ValueError, TypeError):
        return False


# Empreinte factice : même coût de calcul quand le login est inconnu (pas d'énumération par le temps).
_DUMMY = hash_password(secrets.token_hex(8))


def parse_users(raw: str) -> dict[str, tuple[str, str]]:
    users = {}
    for item in (raw or "").split(","):
        item = item.strip()
        if not item:
            continue
        login, role, encoded = item.split(":", 2)
        if role not in ROLES:
            raise ValueError(f"rôle inconnu pour {login} : {role}")
        users[login] = (role, encoded)
    return users


class Sessions:
    def __init__(self, redis, ttl: int):
        self.redis, self.ttl = redis, ttl

    async def create(self, login: str, role: str) -> str:
        token = secrets.token_urlsafe(32)
        await self.redis.set(f"prreview:session:{token}", json.dumps({"login": login, "role": role}), ex=self.ttl)
        return token

    async def get(self, token: str | None) -> dict | None:
        if not token:
            return None
        raw = await self.redis.get(f"prreview:session:{token}")
        return json.loads(raw) if raw else None

    async def delete(self, token: str | None) -> None:
        if token:
            await self.redis.delete(f"prreview:session:{token}")

    async def too_many_failures(self, login: str) -> bool:
        return int(await self.redis.get(f"prreview:login-fail:{login}") or 0) >= 5

    async def record_failure(self, login: str) -> None:
        key = f"prreview:login-fail:{login}"
        await self.redis.incr(key)
        await self.redis.expire(key, 300)


async def current_user(request: Request) -> dict:
    user = await request.app.state.sessions.get(request.cookies.get(COOKIE))
    if not user:
        raise HTTPException(401, "authentification requise")
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise HTTPException(403, "en-tête anti-CSRF manquant")
    return user


async def admin_user(request: Request) -> dict:
    user = await current_user(request)
    if user["role"] != "admin":
        raise HTTPException(403, "réservé aux administrateurs")
    return user


def dummy_verify(password: str) -> None:
    verify_password(password, _DUMMY)


if __name__ == "__main__":
    if "--generate" in sys.argv:
        pwd = secrets.token_urlsafe(12)
        print(f"mot de passe : {pwd}\nempreinte   : {hash_password(pwd)}")
    else:
        import getpass
        print(hash_password(getpass.getpass("Mot de passe : ")))
