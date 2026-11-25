import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import SessionLocal, get_db
from ..models import Attempt, Exercise, Notification, User
from ..security import rate_limited, require_role, require_user
from ..services import events, mathengine, notifier
from ..services import progress as prog
from ..services import tutor as tutor_service

router = APIRouter(prefix="/api")


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class AttemptIn(BaseModel):
    exercise_id: int
    answer: str = Field(min_length=1, max_length=200)


class TextIn(BaseModel):
    text: str = Field(min_length=1, max_length=300)


@router.post("/chat")
def chat(body: ChatIn, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if rate_limited(f"chat:{user.id}", 20, 60):
        raise HTTPException(429, "Trop de messages, patientez un instant.")
    reply = tutor_service.ask(db, user, body.message)
    plan = tutor_service.active_plan(db, user)
    return {"content": reply.content, "sources": reply.sources, "verified": reply.verified, "mode": reply.mode,
            "blocked": reply.blocked, "used": tutor_service.questions_today(db, user), "quota": plan.ai_daily_quota}


@router.post("/attempts")
def attempt(body: AttemptIn, db: Session = Depends(get_db), user: User = Depends(require_role("student"))):
    if rate_limited(f"attempt:{user.id}", 60, 60):
        raise HTTPException(429, "Trop de tentatives, patientez un instant.")
    ex = db.get(Exercise, body.exercise_id)
    if not ex or (ex.workspace_id and ex.workspace_id != user.workspace_id):
        raise HTTPException(404, "Exercice introuvable")
    try:
        correct = mathengine.check_answer(body.answer, ex.answer)
    except mathengine.MathError as exc:
        # réponse illisible : on ne la compte pas comme une erreur
        return JSONResponse({"ok": False, "error": "unreadable", "message": f"Réponse illisible ({exc})."}, status_code=422)

    already_solved = bool(db.scalar(select(func.count(Attempt.id)).where(
        Attempt.student_id == user.id, Attempt.exercise_id == ex.id, Attempt.correct.is_(True))))
    db.add(Attempt(student_id=user.id, exercise_id=ex.id, answer=body.answer.strip(), correct=correct))
    db.commit()

    notifier.live_activity(db, user, {"event": "attempt", "correct": correct, "text": ex.statement[:90]})
    if not correct:
        prog.check_struggle(db, user, ex)
    elif not already_solved:
        row = next((p for p in prog.student_progress(db, user) if p["chapter"].id == ex.chapter_id), None)
        if row and row["total"] and row["solved"] == row["total"]:
            tutors, parents = notifier.recipients_for_student(db, user)
            notifier.notify(db, tutors + parents, "success", f"{user.name} a terminé un chapitre",
                            row["chapter"].title, f"/students/{user.id}")
    return {"ok": True, "correct": correct, "hint": "" if correct else ex.hint}


@router.post("/math/analyze")
def analyze(body: TextIn, user: User = Depends(require_user)):
    return {"result": mathengine.analyze_message(body.text)}


@router.get("/unread")
def unread(db: Session = Depends(get_db), user: User = Depends(require_user)):
    n = db.scalar(select(func.count(Notification.id)).where(
        Notification.user_id == user.id, Notification.is_read.is_(False)))
    return {"unread": n or 0}


@router.get("/events")
async def stream(request: Request):
    """Flux temps réel (SSE). Pas de dépendance DB : la connexion reste ouverte longtemps."""
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "login_required"}, status_code=401)
    item = events.subscribe(uid)

    async def gen():
        try:
            yield "retry: 5000\n\n"
            while not await request.is_disconnected():
                try:
                    payload = await asyncio.wait_for(item[1].get(), timeout=15)
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            events.unsubscribe(uid, item)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
