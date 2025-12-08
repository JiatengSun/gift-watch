from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config.settings import get_settings
from db.sqlite import init_db
from web.routes import router

app = FastAPI(title="gift-watch")

@app.on_event("startup")
def _startup():
    settings = get_settings()
    init_db(settings)

app.include_router(router)

app.mount("/", StaticFiles(directory="web/static", html=True), name="static")
