from __future__ import annotations

import argparse
import asyncio
import logging

from config.settings import get_settings
from core.bili_client import setup_request_client
from db.sqlite import init_db
from services.collector_service import CollectorService
from services.bot_service import build_pipeline
from services.announcement_service import AnnouncementService

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="gift-watch collector bot")
    parser.add_argument(
        "--env-file",
        dest="env_file",
        help="可选 .env 文件路径，用于在多实例场景下区分配置",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    settings = get_settings(args.env_file)
    logging.basicConfig(
        level=settings.log_level,
        format="[%(asctime)s][%(levelname)s] %(message)s",
    )
    logging.getLogger("bilibili_api").setLevel(settings.log_level)
    logging.getLogger("websockets").setLevel(settings.log_level)
    if settings.room_id <= 0:
        raise SystemExit("BILI_ROOM_ID 未配置或不正确。")

    setup_request_client(settings)
    init_db(settings)

    pipeline = build_pipeline(settings)
    collector = CollectorService(settings)
    await collector.log_room_status()
    collector.bind_all_handler(pipeline.handle_event)

    announcement_task = None
    if settings.announce_enabled and pipeline.sender is not None:
        scheduler = AnnouncementService(settings, pipeline.sender)
        announcement_task = scheduler.start()

    print(f"[gift-watch] Listening room {settings.room_id} ...")
    tasks = [asyncio.create_task(collector.run())]
    if announcement_task:
        tasks.append(announcement_task)

    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
