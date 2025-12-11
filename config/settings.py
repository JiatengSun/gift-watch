import logging
import os
from dataclasses import dataclass
from typing import List, Mapping, MutableMapping
from dotenv import dotenv_values, load_dotenv

load_dotenv()

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
    thank_per_user_daily: bool
    thank_guard: bool

    bili_client: str


def get_settings(env_file: str | None = None) -> Settings:
    env: MutableMapping[str, str | None] | None = None
    if env_file:
        env = dotenv_values(env_file)

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
        thank_per_user_daily=_get_env("THANK_PER_USER_DAILY", "1", env) == "1",
        thank_guard=_get_env("THANK_GUARD", "0", env) == "1",

        bili_client=_get_env("BILI_CLIENT", "aiohttp", env),
    )
