from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Mapping

from dotenv import dotenv_values

DEFAULT_ENV_PATH = Path(os.getenv("ENV_FILE") or ".env")


def _resolve_env_path(env_file: str | None) -> Path:
    return Path(env_file) if env_file else DEFAULT_ENV_PATH


def load_env(env_file: str | None = None) -> Dict[str, str]:
    path = _resolve_env_path(env_file)
    if not path.exists():
        return {}
    raw = dotenv_values(path)
    return {k: v for k, v in raw.items() if v is not None}


def save_env(updates: Mapping[str, str], env_file: str | None = None) -> Path:
    path = _resolve_env_path(env_file)
    env = load_env(env_file)
    env.update({k: str(v) for k, v in updates.items()})

    lines = [f"{key}={value}" for key, value in env.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
