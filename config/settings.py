import os
from dataclasses import dataclass
from typing import List
from dotenv import load_dotenv

load_dotenv()

def _get_env(key: str, default: str = "") -> str:
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

    bot_sessdata: str
    bot_bili_jct: str
    bot_buvid3: str

    db_path: str

    thank_global_cooldown_sec: int
    thank_per_user_cooldown_sec: int
    thank_per_user_daily: bool

    bili_client: str

def get_settings() -> Settings:
    room_id = int(_get_env("BILI_ROOM_ID", "1852633038"))
    target_gifts = _split_csv(_get_env("TARGET_GIFTS", "人气票"))
    target_gift_ids = _split_csv_ints(_get_env("TARGET_GIFT_IDS", ""))
    target_min_num = int(_get_env("TARGET_MIN_NUM", "50"))

    return Settings(
        room_id=room_id,
        target_gifts=target_gifts,
        target_gift_ids=target_gift_ids,
        target_min_num=target_min_num,

        bot_sessdata=_get_env("BOT_SESSDATA", ""),
        bot_bili_jct=_get_env("BOT_BILI_JCT", ""),
        bot_buvid3=_get_env("BOT_BUVID3", ""),

        db_path=_get_env("DB_PATH", "gifts.db"),

        thank_global_cooldown_sec=int(_get_env("THANK_GLOBAL_COOLDOWN_SEC", "10")),
        thank_per_user_cooldown_sec=int(_get_env("THANK_PER_USER_COOLDOWN_SEC", "60")),
        thank_per_user_daily=_get_env("THANK_PER_USER_DAILY", "1") == "1",

        bili_client=_get_env("BILI_CLIENT", "aiohttp"),
    )
