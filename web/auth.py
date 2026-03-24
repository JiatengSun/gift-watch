from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from fastapi import HTTPException, Request, Response

COOKIE_NAME = "gift_watch_portal"
COOKIE_MAX_AGE_SEC = 60 * 60 * 12
PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class PortalSession:
    role: Literal["viewer", "manager"]
    env_file: str | None = None


def _secret_key() -> str:
    return (
        os.getenv("ACCESS_COOKIE_SECRET", "").strip()
        or os.getenv("MANAGER_PORTAL_PASSWORD", "").strip()
        or "gift-watch-dev-secret"
    )


def _sign(payload: str) -> str:
    return hmac.new(_secret_key().encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _encode_payload(data: dict) -> str:
    raw = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_payload(token: str) -> dict | None:
    try:
        padded = token + "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _is_https_request(request: Request) -> bool:
    forwarded = request.headers.get("x-forwarded-proto", "")
    if forwarded:
        return forwarded.split(",")[0].strip().lower() == "https"
    return request.url.scheme == "https"


def create_session_token(session: PortalSession) -> str:
    payload = {
        "role": session.role,
        "env_file": session.env_file,
        "exp": int(time.time()) + COOKIE_MAX_AGE_SEC,
    }
    encoded = _encode_payload(payload)
    return f"{encoded}.{_sign(encoded)}"


def parse_session_token(token: str | None) -> PortalSession | None:
    if not token or "." not in token:
        return None
    encoded, signature = token.rsplit(".", 1)
    if not hmac.compare_digest(_sign(encoded), signature):
        return None

    payload = _decode_payload(encoded)
    if not payload:
        return None

    try:
        exp = int(payload.get("exp") or 0)
    except Exception:
        return None
    if exp <= int(time.time()):
        return None

    role = str(payload.get("role") or "").strip().lower()
    env_file = payload.get("env_file")
    if role == "manager":
        return PortalSession(role="manager", env_file=None)
    if role == "viewer" and isinstance(env_file, str) and env_file.strip():
        return PortalSession(role="viewer", env_file=env_file.strip())
    return None


def attach_session_cookie(response: Response, request: Request, session: PortalSession) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=create_session_token(session),
        max_age=COOKIE_MAX_AGE_SEC,
        httponly=True,
        samesite="lax",
        secure=_is_https_request(request),
        path="/",
    )


def clear_session_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(
        key=COOKIE_NAME,
        httponly=True,
        samesite="lax",
        secure=_is_https_request(request),
        path="/",
    )


def get_current_session(request: Request) -> PortalSession | None:
    token = request.cookies.get(COOKIE_NAME)
    return parse_session_token(token)


def require_manager_session(request: Request) -> PortalSession:
    session = get_current_session(request)
    if not session or session.role != "manager":
        raise HTTPException(status_code=401, detail="需要管理员访问权限")
    return session


def require_portal_session(request: Request) -> PortalSession:
    session = get_current_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="请先输入访问密码")
    return session


def resolve_allowed_env(request: Request, env_file: str | None) -> str | None:
    session = require_portal_session(request)
    if session.role == "manager":
        return env_file
    return session.env_file


def scan_viewer_passwords() -> dict[str, str]:
    mapping: dict[str, str] = {}
    duplicates: set[str] = set()
    for path in sorted(PROJECT_ROOT.glob(".env-*")):
        if not path.is_file():
            continue
        payload = dotenv_values(path)
        password = str(payload.get("PORTAL_PASSWORD") or "").strip()
        if not password:
            continue
        if password in mapping:
            duplicates.add(password)
            continue
        mapping[password] = path.name
    if duplicates:
        dup = next(iter(sorted(duplicates)))
        raise HTTPException(status_code=500, detail=f"检测到重复 PORTAL_PASSWORD，请修改后重试：{dup}")
    return mapping


def resolve_password_session(password: str) -> PortalSession | None:
    cleaned = (password or "").strip()
    if not cleaned:
        return None

    admin_password = os.getenv("MANAGER_PORTAL_PASSWORD", "").strip()
    if admin_password and hmac.compare_digest(cleaned, admin_password):
        return PortalSession(role="manager", env_file=None)

    env_file = scan_viewer_passwords().get(cleaned)
    if env_file:
        return PortalSession(role="viewer", env_file=env_file)
    return None
