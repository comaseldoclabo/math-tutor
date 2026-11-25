from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import (Attempt, Chapter, ChatMessage, Country, Document, Exercise, Level, Notification, User)
from ..security import get_user, require_user
from ..services import tutor as tutor_service
from ..templating import render

router = APIRouter()


@router.get("/")
def landing(request: Request, user: User | None = Depends(get_user)):
    if user:
        return RedirectResponse("/dashboard", status_code=303)
    return render(request, "landing.html")


@router.get("/lang/{code}")
def set_lang(code: str, request: Request, db: Session = Depends(get_db), user: User | None = Depends(get_user)):
    if code in settings.SUPPORTED_LANGS:
        request.session["lang"] = code
        if user:
            user.lang = code
            db.commit()
    back = request.headers.get("referer") or "/"
    return RedirectResponse(back if back.startswith(settings.BASE_URL) or back.startswith("/") else "/", status_code=303)


@router.get("/dashboard")
def dashboard(user: User = Depends(require_user)):
    target = {"student": "/student", "parent": "/parent", "tutor": "/tutor", "admin": "/tutor"}[user.role]
    return RedirectResponse(target, status_code=303)


@router.get("/curriculum")
def curriculum(request: Request, country: str | None = None, db: Session = Depends(get_db),
               user: User = Depends(require_user)):
    countries = db.scalars(select(Country).order_by(Country.name)).all()
    code = country or user.country_code or (countries[0].code if countries else None)
    levels = db.scalars(select(Level).where(Level.country_code == code).order_by(Level.position)).all()
    chapters = db.scalars(select(Chapter).where(Chapter.level_id.in_([l.id for l in levels]))
                          .order_by(Chapter.position)).all() if levels else []
    by_level: dict[int, list] = {}
    for c in chapters:
        by_level.setdefault(c.level_id, []).append(c)
    current = next((c for c in countries if c.code == code), None)
    return render(request, "curriculum.html", user, countries=countries, current=current,
                  levels=levels, by_level=by_level)


@router.get("/chapters/{chapter_id}")
def chapter(chapter_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    ch = db.get(Chapter, chapter_id)
    if not ch:
        raise HTTPException(404, "Chapitre introuvable")
    level = db.get(Level, ch.level_id)
    exercises = db.scalars(select(Exercise).where(
        Exercise.chapter_id == ch.id,
        (Exercise.workspace_id.is_(None)) | (Exercise.workspace_id == user.workspace_id)).order_by(Exercise.id)).all()
    solved = set()
    if user.role == "student":
        solved = set(db.scalars(select(Attempt.exercise_id).where(
            Attempt.student_id == user.id, Attempt.correct.is_(True))))
    docs = db.scalars(select(Document).where(
        Document.chapter_id == ch.id,
        (Document.workspace_id.is_(None)) | (Document.workspace_id == user.workspace_id))).all()
    return render(request, "chapter.html", user, chapter=ch, level=level, exercises=exercises, solved=solved, docs=docs)


@router.get("/documents/{doc_id}")
def document(doc_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    doc = db.get(Document, doc_id)
    if not doc or (doc.workspace_id and doc.workspace_id != user.workspace_id):
        raise HTTPException(404, "Document introuvable")
    return render(request, "document.html", user, doc=doc)


@router.get("/chat")
def chat(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    history = db.scalars(select(ChatMessage).where(ChatMessage.user_id == user.id)
                         .order_by(ChatMessage.id.desc()).limit(30)).all()[::-1]
    plan = tutor_service.active_plan(db, user)
    used = tutor_service.questions_today(db, user)
    import json
    return render(request, "chat.html", user, history=history, quota=plan.ai_daily_quota, used=used,
                  ai_on=bool(settings.ANTHROPIC_API_KEY), loads=json.loads)


@router.get("/notifications")
def notifications(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    items = db.scalars(select(Notification).where(Notification.user_id == user.id)
                       .order_by(Notification.id.desc()).limit(100)).all()
    return render(request, "notifications.html", user, items=items)


@router.post("/notifications/read")
def notifications_read(db: Session = Depends(get_db), user: User = Depends(require_user)):
    db.execute(update(Notification).where(Notification.user_id == user.id, Notification.is_read.is_(False))
               .values(is_read=True))
    db.commit()
    return RedirectResponse("/notifications", status_code=303)


@router.get("/offline")
def offline(request: Request):
    return render(request, "offline.html")
