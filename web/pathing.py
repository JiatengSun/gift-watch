from __future__ import annotations

import os


def get_base_path() -> str:
    raw = (os.getenv("PORTAL_BASE_PATH") or "/gift-watch").strip()
    if not raw:
        return ""
    if not raw.startswith("/"):
        raw = f"/{raw}"
    return raw.rstrip("/")


def with_base_path(path: str) -> str:
    base = get_base_path()
    normalized = path if path.startswith("/") else f"/{path}"
    if not base:
        return normalized
    if normalized == "/":
        return f"{base}/"
    return f"{base}{normalized}"
