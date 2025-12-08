from __future__ import annotations

import asyncio
import logging

from config.settings import get_settings
from core.bili_client import setup_request_client
from db.sqlite import init_db
from services.collector_service import CollectorService
from services.bot_service import build_pipeline

async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s][%(levelname)s] %(message)s",
    )
    settings = get_settings()
    if settings.room_id <= 0:
        raise SystemExit("BILI_ROOM_ID 未配置或不正确。")

    setup_request_client(settings)
    init_db(settings)

    pipeline = build_pipeline(settings)
    collector = CollectorService(settings)
    collector.bind_all_handler(pipeline.handle_event)

    print(f"[gift-watch] Listening room {settings.room_id} ...")
    await collector.run()

if __name__ == "__main__":
    asyncio.run(main())
