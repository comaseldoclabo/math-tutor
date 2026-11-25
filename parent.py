from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ParentChild, User
from ..security import children_of, require_role
from ..services import progress as prog
from ..templating import flash, render

router = APIRouter()


@router.get("/parent")
def home(request: Request, db: Session = Depends(get_db), user: User = Depends(require_role("parent"))):
    cards = []
    for child in children_of(db, user):
        progress = prog.student_progress(db, child)
        cards.append({"child": child, "overall": prog.overall(progress), "activity": prog.daily_activity(db, child.id),
                      "last": prog.last_activity(db, child.id),
                      "struggling": [p for p in progress if p["status"] == "struggling"]})
    return render(request, "parent_home.html", user, cards=cards)


@router.post("/parent/link")
def link(request: Request, code: str = Form(...), db: Session = Depends(get_db),
         user: User = Depends(require_role("parent"))):
    child = db.scalar(select(User).where(User.link_code == code.strip().upper(), User.role == "student"))
    if not child:
        flash(request, "Code enfant inconnu.", "err")
    elif db.get(ParentChild, (user.id, child.id)):
        flash(request, "Cet enfant est déjà lié.", "err")
    else:
        db.add(ParentChild(parent_id=user.id, child_id=child.id))
        db.commit()
        flash(request, f"{child.name} est maintenant lié à votre compte.")
    return RedirectResponse("/parent", status_code=303)
