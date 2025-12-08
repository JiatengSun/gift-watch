import os
from dataclasses import dataclass
from typing import List
from dotenv import load_dotenv

load_dotenv()

def _get_env(key: str, default: str = "") -> str:
    v = os.getenv(key)
    return v if v is not None else default

def _split_csv(s: str) -> List[str]:
    return [x.strip() for x in s.split(",") if x.strip()]

@dataclass(frozen=True)
class Settings:
    room_id: int
    target_gifts: List[str]

    bot_sessdata: str
    bot_bili_jct: str
    bot_buvid3: str

    db_path: str

    thank_global_cooldown_sec: int
    thank_per_user_cooldown_sec: int

    bili_client: str

def get_settings() -> Settings:
    room_id = int(_get_env("BILI_ROOM_ID", "0"))
    target_gifts = _split_csv(_get_env("TARGET_GIFTS", ""))

    return Settings(
        room_id=room_id,
        target_gifts=target_gifts,

        bot_sessdata=_get_env("BOT_SESSDATA", ""),
        bot_bili_jct=_get_env("BOT_BILI_JCT", ""),
        bot_buvid3=_get_env("BOT_BUVID3", ""),

        db_path=_get_env("DB_PATH", "gifts.db"),

        thank_global_cooldown_sec=int(_get_env("THANK_GLOBAL_COOLDOWN_SEC", "10")),
        thank_per_user_cooldown_sec=int(_get_env("THANK_PER_USER_COOLDOWN_SEC", "60")),

        bili_client=_get_env("BILI_CLIENT", "aiohttp"),
    )
