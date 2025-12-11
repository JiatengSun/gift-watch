from __future__ import annotations

from pathlib import Path
from typing import Dict, Mapping

from dotenv import dotenv_values

from config.settings import resolve_env_file


def _resolve_env_path(env_file: str | None) -> Path:
    resolved = resolve_env_file(env_file)
    if resolved:
        return Path(resolved)
    fallback = Path(".env")
    return fallback


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
