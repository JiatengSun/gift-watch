from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse

from config.settings import get_settings, resolve_env_file
from db.sqlite import init_db
from web.access_routes import router as access_router
from web.auth import get_current_session
from web.routes import router
from web.manager_routes import router as manager_router
from services.gift_price_cache import ensure_gift_price_cache

app = FastAPI(title="gift-watch")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

@app.on_event("startup")
def _startup():
    settings = get_settings(resolve_env_file(None))
    ensure_gift_price_cache(settings)
    init_db(settings)

app.include_router(router)
app.include_router(manager_router)
app.include_router(access_router)


@app.get("/")
def home(request: Request):
    session = get_current_session(request)
    if not session:
        return RedirectResponse("/access", status_code=302)
    return RedirectResponse("/manager" if session.role == "manager" else "/app", status_code=302)


@app.get("/app")
def app_page(request: Request):
    session = get_current_session(request)
    if not session:
        return RedirectResponse("/access", status_code=302)
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/manager")
def manager_page(request: Request):
    session = get_current_session(request)
    if not session or session.role != "manager":
        return RedirectResponse("/access", status_code=302)
    return FileResponse(STATIC_DIR / "manager.html")
