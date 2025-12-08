from __future__ import annotations

from bilibili_api import Credential, select_client

from config.settings import Settings

def setup_request_client(settings: Settings) -> None:
    # 直播监听需要 WebSocket，默认建议 aiohttp
    client = (settings.bili_client or "aiohttp").lower().strip()
    try:
        select_client(client)
    except Exception:
        # 回退让库自行选择
        pass

def get_bot_credential(settings: Settings) -> Credential:
    return Credential(
        sessdata=settings.bot_sessdata,
        bili_jct=settings.bot_bili_jct,
        buvid3=settings.bot_buvid3
    )
