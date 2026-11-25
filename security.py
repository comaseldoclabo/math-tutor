"""Authentification (session signée), rôles, CSRF, limitation de débit et contrôle d'accès aux élèves."""
import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import ParentChild, User


class NeedLogin(Exception):
    pass


# ---------------------------------------------------------------- mots de passe (scrypt, stdlib)
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    h = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${h.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, h_hex = stored.split("$")
        h = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(h.hex(), h_hex)
    except (ValueError, TypeError):
        return False


def make_code(prefix: str) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sans caractères ambigus (O/0, I/1)
    return f"{prefix}-" + "".join(secrets.choice(alphabet) for _ in range(6))


# ---------------------------------------------------------------- utilisateur courant
def get_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    uid = request.session.get("uid")
    if not uid:
        return None
    user = db.get(User, uid)
    if not user or not user.is_active:
        request.session.clear()
        return None
    return user


def require_user(user: User | None = Depends(get_user)) -> User:
    if not user:
        raise NeedLogin()
    return user


def require_role(*roles: str):
    def dep(user: User = Depends(require_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "Accès refusé")
        return user

    return dep


def require_manager(user: User = Depends(require_user)) -> User:
    if not user.can_manage:
        raise HTTPException(403, "Accès refusé")
    return user


# ---------------------------------------------------------------- CSRF
def csrf_token(request: Request) -> str:
    tok = request.session.get("csrf")
    if not tok:
        tok = secrets.token_urlsafe(24)
        request.session["csrf"] = tok
    return tok


async def csrf_protect(request: Request) -> None:
    if request.method not in ("POST", "PUT", "PATCH", "DELETE") or request.url.path.startswith("/webhooks/"):
        return
    sent = request.headers.get("x-csrf-token")
    if not sent:
        form = await request.form()
        sent = form.get("csrf")
    expected = request.session.get("csrf")
    if not expected or not sent or not hmac.compare_digest(str(sent), expected):
        raise HTTPException(403, "Jeton CSRF invalide : rechargez la page.")


# ---------------------------------------------------------------- limitation de débit (mémoire, 1 worker)
_hits: dict[str, deque] = defaultdict(deque)


def rate_limited(key: str, limit: int, window: int) -> bool:
    now = time.monotonic()
    q = _hits[key]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        return True
    q.append(now)
    return False


# ---------------------------------------------------------------- contrôle d'accès aux données d'un élève
def can_view_student(db: Session, viewer: User, student: User) -> bool:
    if student.role != "student":
        return False
    if viewer.id == student.id:
        return True
    if viewer.is_staff and viewer.workspace_id and viewer.workspace_id == student.workspace_id:
        return True
    if viewer.role == "parent":
        return db.get(ParentChild, (viewer.id, student.id)) is not None
    return False


def children_of(db: Session, parent: User) -> list[User]:
    ids = db.scalars(select(ParentChild.child_id).where(ParentChild.parent_id == parent.id)).all()
    return list(db.scalars(select(User).where(User.id.in_(ids)))) if ids else []
