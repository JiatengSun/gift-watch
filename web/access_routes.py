from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from web.auth import (
    TICKET_PARAM,
    create_session_token,
    get_current_session,
    resolve_password_session,
)
from web.pathing import with_base_path

router = APIRouter()

STATIC_DIR = Path(__file__).resolve().parent / "static"


class LoginPayload(BaseModel):
    password: str = Field(..., min_length=1, description="访问密码")


def _destination_for_role(role: str) -> str:
    return with_base_path("/manager" if role == "manager" else "/app")


@router.get("/access")
def access_page():
    return FileResponse(STATIC_DIR / "access.html")


@router.get("/api/access/session")
def access_session(request: Request):
    session = get_current_session(request)
    if not session:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "role": session.role,
        "destination": _destination_for_role(session.role),
        "env_file": session.env_file,
    }


@router.post("/api/access/login")
def access_login(
    request: Request,
    payload: LoginPayload = Body(...),
):
    session = resolve_password_session(payload.password)
    if not session:
        return JSONResponse(
            content={"ok": False, "detail": "密码错误或未配置访问权限"},
            status_code=401,
        )

    ticket = create_session_token(session)
    destination_path = with_base_path("/manager" if session.role == "manager" else "/app")
    return {
        "ok": True,
        "role": session.role,
        "ticket": ticket,
        "destination": f"{destination_path}?{TICKET_PARAM}={ticket}",
    }


@router.post("/api/access/logout")
def access_logout():
    return {"ok": True}
