from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config.settings import get_settings, resolve_env_file
from db.sqlite import init_db
from web.routes import router

app = FastAPI(title="gift-watch")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

@app.on_event("startup")
def _startup():
    settings = get_settings(resolve_env_file(None))
    init_db(settings)

app.include_router(router)

# Mount the static frontend with HTML fallback so "/" and any client-side
# routes serve the index page instead of a 404 (e.g., when proxied by nginx).
app.mount(
    "/",
    StaticFiles(directory=STATIC_DIR, html=True),
    name="static",
)
