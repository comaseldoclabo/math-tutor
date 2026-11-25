from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Country, Level, Notification, Plan, User, Workspace, now
from ..security import require_role
from ..services import progress as prog
from ..services import tutor as tutor_service
from ..templating import flash, render

router = APIRouter()


@router.get("/student")
def home(request: Request, db: Session = Depends(get_db), user: User = Depends(require_role("student"))):
    progress = prog.student_progress(db, user)
    ws = db.get(Workspace, user.workspace_id) if user.workspace_id else None
    plan = tutor_service.active_plan(db, user)
    tutors = db.scalars(select(User).where(User.workspace_id == user.workspace_id, User.role.in_(("tutor", "admin")))
                        ).all() if user.workspace_id else []
    recent = db.scalars(select(Notification).where(Notification.user_id == user.id)
                        .order_by(Notification.id.desc()).limit(5)).all()
    countries = db.scalars(select(Country).order_by(Country.name)).all()
    levels = db.scalars(select(Level).where(Level.country_code == user.country_code).order_by(Level.position)).all() \
        if user.country_code else []
    return render(request, "student_home.html", user, progress=progress, overall=prog.overall(progress),
                  activity=prog.daily_activity(db, user.id), workspace=ws, tutors=tutors, recent=recent,
                  quota=plan.ai_daily_quota, used=tutor_service.questions_today(db, user),
                  level=db.get(Level, user.level_id) if user.level_id else None,
                  countries=countries, levels=levels)


@router.post("/student/join")
def join(request: Request, code: str = Form(...), db: Session = Depends(get_db),
         user: User = Depends(require_role("student"))):
    ws = db.scalar(select(Workspace).where(Workspace.join_code == code.strip().upper()))
    if not ws:
        flash(request, "Code d'invitation inconnu.", "err")
        return RedirectResponse("/student", status_code=303)
    plan = db.get(Plan, ws.plan_code)
    n = db.scalar(select(func.count(User.id)).where(User.workspace_id == ws.id, User.role == "student"))
    if plan and n >= plan.max_students and (ws.plan_until is None or ws.plan_until > now()):
        flash(request, "Cet espace a atteint sa limite d'élèves.", "err")
    else:
        user.workspace_id = ws.id
        db.commit()
        flash(request, f"Vous avez rejoint « {ws.name} ».")
    return RedirectResponse("/student", status_code=303)


@router.post("/student/profile")
def profile(request: Request, country_code: str = Form(""), level_id: str = Form(""),
            phone: str = Form(""), db: Session = Depends(get_db), user: User = Depends(require_role("student"))):
    country = db.get(Country, country_code) if country_code else None
    level = db.get(Level, int(level_id)) if level_id.isdigit() else None
    user.country_code = country.code if country else None
    user.level_id = level.id if level and country and level.country_code == country.code else None
    user.phone = phone.strip()[:30]
    db.commit()
    flash(request, "Profil mis à jour.")
    return RedirectResponse("/student", status_code=303)
