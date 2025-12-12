import logging
import os
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import List, Mapping, MutableMapping, Optional
from dotenv import dotenv_values, load_dotenv

def _detect_env_file_from_argv() -> str | None:
    args = sys.argv or []
    for idx, arg in enumerate(args):
        if arg in {"--env-file", "--env_file", "-e"} and idx + 1 < len(args):
            return args[idx + 1]
        if arg.startswith("--env-file=") or arg.startswith("--env_file="):
            return arg.split("=", 1)[1]
    return None


DEFAULT_ENV_FILE = os.getenv("ENV_FILE") or _detect_env_file_from_argv()

load_dotenv(DEFAULT_ENV_FILE if DEFAULT_ENV_FILE else None)

def _get_env(key: str, default: str = "", env: Mapping[str, str | None] | None = None) -> str:
    if env is not None and key in env:
        value = env.get(key)
        return value if value is not None else default

    v = os.getenv(key)
    return v if v is not None else default

def _split_csv(s: str) -> List[str]:
    # Support both western comma and full-width Chinese comma to avoid silent
    # misconfiguration when users copy/paste gift names from Chinese sources.
    normalized = (s or "").replace("，", ",")
    return [x.strip() for x in normalized.split(",") if x.strip()]


def _split_csv_ints(s: str) -> List[int]:
    values: List[int] = []
    for item in _split_csv(s):
        try:
            values.append(int(item))
        except ValueError:
            continue
    return values


def _split_lines(s: str) -> List[str]:
    normalized = (s or "").replace("\\n", "\n")
    return [line.strip() for line in normalized.splitlines() if line.strip()]

@dataclass(frozen=True)
class Settings:
    room_id: int
    target_gifts: List[str]
    target_gift_ids: List[int]
    target_min_num: int
    log_level: int

    bot_sessdata: str
    bot_bili_jct: str
    bot_buvid3: str

    db_path: str

    thank_global_cooldown_sec: int
    thank_per_user_cooldown_sec: int
    thank_per_user_daily_limit: int
    thank_mode: str
    thank_value_threshold: int
    thank_guard: bool
    thank_message_single: str
    thank_message_summary: str
    thank_message_guard: str

    announce_enabled: bool
    announce_interval_sec: int
    announce_messages: List[str]
    announce_skip_offline: bool
    announce_mode: str
    announce_danmaku_threshold: int

    bili_client: str


def resolve_env_file(env_file: str | None) -> str | None:
    if env_file:
        return env_file
    if DEFAULT_ENV_FILE:
        return DEFAULT_ENV_FILE
    default_env = Path(".env")
    return str(default_env) if default_env.exists() else None


def get_settings(env_file: str | None = None) -> Settings:
    env: MutableMapping[str, str | None] | None = None
    resolved_env = resolve_env_file(env_file)
    if resolved_env:
        env = dotenv_values(resolved_env)

    room_id = int(_get_env("BILI_ROOM_ID", "1852633038", env))
    target_gifts = _split_csv(_get_env("TARGET_GIFTS", "人气票", env))
    target_gift_ids = _split_csv_ints(_get_env("TARGET_GIFT_IDS", "", env))
    target_min_num = int(_get_env("TARGET_MIN_NUM", "50", env))

    def _get_log_level() -> int:
        level_name = _get_env("LOG_LEVEL", "INFO", env).strip().upper()
        # Prefer explicit numeric levels when provided (e.g. 10, 20).
        if level_name.isdigit():
            return int(level_name)

        level = getattr(logging, level_name, logging.INFO)
        if isinstance(level, int):
            return level
        return logging.INFO

    thank_mode = _get_env("THANK_MODE", "count", env).strip().lower() or "count"
    if thank_mode not in {"count", "value"}:
        thank_mode = "count"

    thank_value_threshold = max(int(_get_env("THANK_VALUE_THRESHOLD", "0", env)), 0)

    daily_limit_raw = _get_env("THANK_PER_USER_DAILY_LIMIT", "", env).strip()
    thank_per_user_daily_limit = int(daily_limit_raw) if daily_limit_raw else None
    if thank_per_user_daily_limit is None:
        legacy_daily = _get_env("THANK_PER_USER_DAILY", "", env)
        thank_per_user_daily_limit = 1 if legacy_daily == "1" else 0
    thank_per_user_daily_limit = max(thank_per_user_daily_limit, 0)

    thank_message_single = _get_env(
        "THANK_MESSAGE_SINGLE", "谢谢 {uname} 送的 {gift_name} x{num}！太帅了！", env
    )
    thank_message_summary = _get_env(
        "THANK_MESSAGE_SUMMARY", "谢谢 {uname} 送的 {gifts}！太帅了！", env
    )
    thank_message_guard = _get_env(
        "THANK_MESSAGE_GUARD", "感谢{uname}的{guard_name}！！你最帅了！", env
    )

    announce_enabled = _get_env("ANNOUNCE_ENABLED", "0", env) == "1"
    announce_interval_sec = max(int(_get_env("ANNOUNCE_INTERVAL_SEC", "300", env)), 30)
    announce_messages = _split_lines(_get_env("ANNOUNCE_MESSAGE", "主播报时：感谢陪伴~", env))
    announce_skip_offline = _get_env("ANNOUNCE_SKIP_OFFLINE", "1", env) == "1"
    announce_mode = _get_env("ANNOUNCE_MODE", "interval", env)
    announce_mode = announce_mode if announce_mode in {"interval", "message_count"} else "interval"
    announce_danmaku_threshold = max(int(_get_env("ANNOUNCE_DANMAKU_THRESHOLD", "5", env)), 1)

    return Settings(
        room_id=room_id,
        target_gifts=target_gifts,
        target_gift_ids=target_gift_ids,
        target_min_num=target_min_num,
        log_level=_get_log_level(),

        bot_sessdata=_get_env("BOT_SESSDATA", "", env),
        bot_bili_jct=_get_env("BOT_BILI_JCT", "", env),
        bot_buvid3=_get_env("BOT_BUVID3", "", env),

        db_path=_get_env("DB_PATH", "gifts.db", env),

        thank_global_cooldown_sec=int(_get_env("THANK_GLOBAL_COOLDOWN_SEC", "10", env)),
        thank_per_user_cooldown_sec=int(_get_env("THANK_PER_USER_COOLDOWN_SEC", "60", env)),
        thank_per_user_daily_limit=thank_per_user_daily_limit,
        thank_mode=thank_mode,
        thank_value_threshold=thank_value_threshold,
        thank_guard=_get_env("THANK_GUARD", "0", env) == "1",
        thank_message_single=thank_message_single,
        thank_message_summary=thank_message_summary,
        thank_message_guard=thank_message_guard,

        announce_enabled=announce_enabled,
        announce_interval_sec=announce_interval_sec,
        announce_messages=announce_messages,
        announce_skip_offline=announce_skip_offline,
        announce_mode=announce_mode,
        announce_danmaku_threshold=announce_danmaku_threshold,

        bili_client=_get_env("BILI_CLIENT", "aiohttp", env),
    )


class SettingsReloader:
    """Reload settings when the env file changes on disk."""

    def __init__(self, env_file: str | None = None):
        self.env_file = resolve_env_file(env_file)
        self._cached = get_settings(self.env_file)
        self._last_mtime = self._get_mtime()

    def _get_mtime(self) -> Optional[float]:
        if not self.env_file:
            return None
        path = Path(self.env_file)
        try:
            return path.stat().st_mtime
        except FileNotFoundError:
            return None

    def current(self) -> Settings:
        return self._cached

    def reload_if_changed(self) -> Settings:
        mtime = self._get_mtime()
        if self._last_mtime is not None and mtime is not None and mtime <= self._last_mtime:
            return self._cached

        if mtime != self._last_mtime:
            self._cached = get_settings(self.env_file)
            self._last_mtime = mtime

        return self._cached
