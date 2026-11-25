from datetime import datetime

from .models import now as _now

from fastapi import Request
from fastapi.templating import Jinja2Templates

from .config import BASE_DIR, settings
from .i18n import get_lang, make_t
from .security import csrf_token

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _dt(v: datetime | None, fmt: str = "%d/%m/%Y %H:%M") -> str:
    return v.strftime(fmt) if v else "—"


def _ago(v: datetime | None) -> str:
    if not v:
        return "—"
    delta = _now() - v
    s = int(delta.total_seconds())
    if s < 60:
        return "à l'instant"
    if s < 3600:
        return f"{s // 60} min"
    if s < 86400:
        return f"{s // 3600} h"
    return f"{s // 86400} j"


templates.env.filters["dt"] = _dt
templates.env.filters["ago"] = _ago


def flash(request: Request, message: str, kind: str = "ok") -> None:
    request.session.setdefault("flash", [])
    request.session["flash"] = request.session["flash"] + [[kind, message]]


def render(request: Request, name: str, user=None, status_code: int = 200, **ctx):
    lang = get_lang(request, user)
    ctx.update(
        user=user, t=make_t(lang), lang=lang, rtl=lang in settings.RTL_LANGS,
        csrf_token=csrf_token(request), app_name=settings.APP_NAME,
        langs=settings.SUPPORTED_LANGS, flashes=request.session.pop("flash", []),
    )
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)
