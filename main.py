from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from starlette.exceptions import HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .config import BASE_DIR, settings
from .db import Base, SessionLocal, engine
from .routers import admin, api, auth, pages, parent, student, tutor
from .security import NeedLogin, csrf_protect, get_user
from .templating import render
from . import seed


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)  # en production avec évolutions de schéma : utiliser Alembic
    with SessionLocal() as db:
        seed.run(db)
    yield


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan, dependencies=[Depends(csrf_protect)],
              docs_url=None if settings.ENV == "production" else "/docs", redoc_url=None)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY, same_site="lax",
                   https_only=settings.ENV == "production", max_age=60 * 60 * 24 * 14)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

for module in (pages, auth, api, student, parent, tutor, admin):
    app.include_router(module.router)


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    return FileResponse(BASE_DIR / "static" / "sw.js", media_type="application/javascript",
                        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return FileResponse(BASE_DIR / "static" / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"ok": True}


@app.exception_handler(NeedLogin)
async def need_login(request: Request, exc: NeedLogin):
    if request.url.path.startswith("/api/"):
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "login_required"}, status_code=401)
    return RedirectResponse(f"/login?next={request.url.path}", status_code=303)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    if request.url.path.startswith("/api/"):
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
    from .db import SessionLocal as _S
    with _S() as db:
        user = None
        try:
            user = get_user(request, db)
        except Exception:  # noqa: BLE001
            pass
        return render(request, "error.html", user=user, status_code=exc.status_code,
                      code=exc.status_code, message=str(exc.detail))
