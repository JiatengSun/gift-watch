from __future__ import annotations

import os

import uvicorn


def _reload_enabled() -> bool:
    value = os.getenv("UVICORN_RELOAD", "1").strip().lower()
    return value in {"1", "true", "yes", "y"}


if __name__ == "__main__":
    uvicorn.run(
        "web.app:app",
        host="0.0.0.0",
        port=3333,
        reload=_reload_enabled(),
    )
