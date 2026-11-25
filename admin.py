from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Country, Payment, Plan, User, Workspace, now
from ..security import require_manager
from ..services import payments
from ..templating import flash, render

router = APIRouter()


@router.get("/admin")
def admin_home(request: Request, db: Session = Depends(get_db), user: User = Depends(require_manager)):
    ws = db.get(Workspace, user.workspace_id)
    members = db.scalars(select(User).where(User.workspace_id == ws.id).order_by(User.role, User.name)).all()
    plans = db.scalars(select(Plan).order_by(Plan.position)).all()
    country = db.get(Country, user.country_code or ws.country_code) if (user.country_code or ws.country_code) else None
    currency = country.currency if country else "USD"
    pays = db.scalars(select(Payment).where(Payment.workspace_id == ws.id).order_by(Payment.id.desc()).limit(20)).all()
    n_students = db.scalar(select(func.count(User.id)).where(User.workspace_id == ws.id, User.role == "student"))
    valid = ws.plan_until is None or ws.plan_until > now()
    return render(request, "admin.html", user, ws=ws, members=members, plans=plans, currency=currency, pays=pays,
                  n_students=n_students, current_plan=db.get(Plan, ws.plan_code if valid else "free"), valid=valid)


@router.post("/admin/checkout")
def checkout(request: Request, plan_code: str = Form(...), db: Session = Depends(get_db),
             user: User = Depends(require_manager)):
    ws = db.get(Workspace, user.workspace_id)
    plan = db.get(Plan, plan_code)
    country = db.get(Country, user.country_code or ws.country_code) if (user.country_code or ws.country_code) else None
    if not plan:
        raise HTTPException(404, "Plan introuvable")
    try:
        url = payments.start_checkout(db, user, ws, plan, country.currency if country else "USD")
    except payments.PaymentError as exc:
        flash(request, str(exc), "err")
        return RedirectResponse("/admin", status_code=303)
    if url:
        return RedirectResponse(url, status_code=303)
    flash(request, f"Plan « {plan.name} » activé (mode démo, aucun débit réel).")
    return RedirectResponse("/admin", status_code=303)


@router.post("/admin/members/{member_id}/toggle")
def toggle_member(member_id: int, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require_manager)):
    m = db.get(User, member_id)
    if not m or m.workspace_id != user.workspace_id or m.id == user.id:
        raise HTTPException(404, "Introuvable")
    m.is_active = not m.is_active
    db.commit()
    flash(request, "Compte " + ("réactivé." if m.is_active else "désactivé."))
    return RedirectResponse("/admin", status_code=303)


@router.post("/webhooks/flutterwave")
async def flutterwave_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    ok = payments.handle_flutterwave_webhook(db, request.headers.get("verif-hash"), body)
    return JSONResponse({"ok": ok}, status_code=200 if ok else 400)
