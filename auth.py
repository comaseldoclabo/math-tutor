import re

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Country, Level, ParentChild, Plan, User, Workspace, now
from ..security import get_user, hash_password, make_code, rate_limited, verify_password
from ..templating import flash, render

router = APIRouter()
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _form_ctx(db: Session) -> dict:
    countries = db.scalars(select(Country).order_by(Country.name)).all()
    levels = db.scalars(select(Level).order_by(Level.position)).all()
    by_country: dict[str, list] = {}
    for l in levels:
        by_country.setdefault(l.country_code, []).append({"id": l.id, "name": l.name})
    return {"countries": countries, "levels_by_country": by_country}


@router.get("/login")
def login_page(request: Request, next: str = "/dashboard", user: User | None = Depends(get_user)):
    if user:
        return RedirectResponse("/dashboard", status_code=303)
    return render(request, "login.html", next=next)


@router.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), next: str = Form("/dashboard"),
          db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "?"
    if rate_limited(f"login:{ip}", 10, 300):
        flash(request, "Trop de tentatives. Réessayez dans quelques minutes.", "err")
        return RedirectResponse("/login", status_code=303)
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if not user or not user.is_active or not verify_password(password, user.pw_hash):
        flash(request, "Email ou mot de passe incorrect.", "err")
        return RedirectResponse("/login", status_code=303)
    request.session.clear()
    request.session["uid"] = user.id
    request.session["lang"] = user.lang
    return RedirectResponse(next if next.startswith("/") and not next.startswith("//") else "/dashboard", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)


@router.get("/register")
def register_page(request: Request, db: Session = Depends(get_db), user: User | None = Depends(get_user)):
    if user:
        return RedirectResponse("/dashboard", status_code=303)
    return render(request, "register.html", **_form_ctx(db))


@router.post("/register")
def register(request: Request, db: Session = Depends(get_db),
             role: str = Form(...), name: str = Form(...), email: str = Form(...), password: str = Form(...),
             country_code: str = Form(""), level_id: str = Form(""), code: str = Form(""),
             workspace_name: str = Form(""), phone: str = Form(""), whatsapp: str = Form("")):
    def fail(msg: str):
        flash(request, msg, "err")
        return render(request, "register.html", status_code=400, **_form_ctx(db))

    email = email.strip().lower()
    name, code = name.strip()[:120], code.strip().upper()
    if role not in ("student", "parent", "tutor", "admin"):
        return fail("Rôle invalide.")
    if not name or not EMAIL_RE.match(email):
        return fail("Nom ou email invalide.")
    if len(password) < 8:
        return fail("Le mot de passe doit contenir au moins 8 caractères.")
    if db.scalar(select(User.id).where(User.email == email)):
        return fail("Un compte existe déjà avec cet email.")
    country = db.get(Country, country_code) if country_code else None
    level = db.get(Level, int(level_id)) if level_id.isdigit() else None
    if level and country and level.country_code != country.code:
        level = None

    user = User(email=email, name=name, pw_hash=hash_password(password), role=role,
                country_code=country.code if country else None, level_id=level.id if level else None,
                lang=country.lang if country and country.lang in ("fr", "en") else request.session.get("lang", "fr"),
                phone=phone.strip()[:30], whatsapp_opt_in=bool(whatsapp and phone.strip()))
    if role == "student":
        user.link_code = make_code("E")
        if code:
            ws = db.scalar(select(Workspace).where(Workspace.join_code == code))
            if not ws:
                return fail("Code d'invitation inconnu.")
            plan = db.get(Plan, ws.plan_code)
            n = db.scalar(select(func.count(User.id)).where(User.workspace_id == ws.id, User.role == "student"))
            if plan and n >= plan.max_students and (ws.plan_until is None or ws.plan_until > now()):
                return fail("Cet espace a atteint sa limite d'élèves. Contactez votre tuteur.")
            user.workspace_id = ws.id
    elif role in ("tutor", "admin"):
        if code:
            ws = db.scalar(select(Workspace).where(Workspace.tutor_code == code))
            if not ws:
                return fail("Code tuteur inconnu.")
            user.workspace_id = ws.id
        else:
            ws = Workspace(name=(workspace_name.strip() or f"Espace de {name}")[:120],
                           kind="school" if role == "admin" else "tutor",
                           join_code=make_code("ELV"), tutor_code=make_code("TUT"),
                           country_code=country.code if country else None)
            db.add(ws)
            db.flush()
            user.workspace_id, user.is_owner = ws.id, True
    db.add(user)
    db.flush()
    if role == "parent" and code:
        child = db.scalar(select(User).where(User.link_code == code, User.role == "student"))
        if not child:
            db.rollback()
            return fail("Code enfant inconnu.")
        db.add(ParentChild(parent_id=user.id, child_id=child.id))
    db.commit()
    request.session.clear()
    request.session["uid"] = user.id
    request.session["lang"] = user.lang
    return RedirectResponse("/dashboard", status_code=303)
