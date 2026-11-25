"""Notifications : in-app (base + temps réel SSE) et WhatsApp (API Cloud de Meta, optionnel)."""
import logging
import threading

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Notification, ParentChild, User
from . import events

log = logging.getLogger("notifier")


def _send_whatsapp(phone: str, text: str) -> None:
    if not (settings.WHATSAPP_TOKEN and settings.WHATSAPP_PHONE_ID and phone):
        return
    try:
        # NB : hors fenêtre de 24 h, Meta impose des messages « template » approuvés.
        httpx.post(
            f"https://graph.facebook.com/v20.0/{settings.WHATSAPP_PHONE_ID}/messages",
            headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"},
            json={"messaging_product": "whatsapp", "to": phone.lstrip("+"), "type": "text",
                  "text": {"body": text[:1000]}},
            timeout=10,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("WhatsApp indisponible : %s", exc)


def notify(db: Session, user_ids: list[int], kind: str, title: str, body: str = "", url: str = "") -> None:
    ids = sorted(set(user_ids))
    if not ids:
        return
    users = db.scalars(select(User).where(User.id.in_(ids))).all()
    for u in users:
        db.add(Notification(user_id=u.id, kind=kind, title=title[:200], body=body, url=url))
    db.commit()
    for u in users:
        events.publish(u.id, {"type": "notification", "kind": kind, "title": title, "body": body, "url": url})
        if u.whatsapp_opt_in and u.phone:
            threading.Thread(target=_send_whatsapp, args=(u.phone, f"{title}\n{body}"), daemon=True).start()


def recipients_for_student(db: Session, student: User) -> tuple[list[int], list[int]]:
    """(ids des tuteurs de l'espace, ids des parents liés)."""
    tutors: list[int] = []
    if student.workspace_id:
        tutors = list(db.scalars(select(User.id).where(
            User.workspace_id == student.workspace_id, User.role.in_(("tutor", "admin")), User.is_active.is_(True))))
    parents = list(db.scalars(select(ParentChild.parent_id).where(ParentChild.child_id == student.id)))
    return tutors, parents


def live_activity(db: Session, student: User, payload: dict) -> None:
    """Flux « activité en direct » (non stocké) pour les tuteurs et parents connectés."""
    tutors, parents = recipients_for_student(db, student)
    for uid in tutors + parents:
        events.publish(uid, {"type": "activity", "student": student.name, "student_id": student.id, **payload})
