from __future__ import annotations

import os

import uvicorn


def _reload_enabled() -> bool:
    value = os.getenv("UVICORN_RELOAD", "1").strip().lower()
    return value in {"1", "true", "yes", "y"}


def _server_port() -> int:
    value = os.getenv("UVICORN_PORT") or os.getenv("PORT")
    return int(value) if value else 3333


if __name__ == "__main__":
    uvicorn.run(
        "web.app:app",
        host="0.0.0.0",
        port=_server_port(),
        reload=_reload_enabled(),
    )
