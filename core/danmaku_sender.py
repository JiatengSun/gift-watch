from __future__ import annotations

from typing import Mapping, Optional
import asyncio
import logging
import time

from bilibili_api import live, Credential
from bilibili_api.exceptions import ResponseCodeException

from core.danmaku_queue import DanmakuQueue, QueueMessage

class DanmakuSender:
    def __init__(
        self,
        room_id: int,
        credential: Credential,
        *,
        thank_message_single: str,
        thank_message_summary: str,
        thank_message_guard: str,
        max_length: int,
        queue_db_path: str | None = None,
        queue_interval_sec: int = 3,
    ):
        self.room_id = room_id
        self.credential = credential
        self._room: Optional[live.LiveRoom] = None
        self._thank_message_single = thank_message_single
        self._thank_message_summary = thank_message_summary
        self._thank_message_guard = thank_message_guard
        self.max_length = max(0, max_length)
        self.logger = logging.getLogger(__name__)
        self._queue: DanmakuQueue | None = None
        self._queue_task: asyncio.Task | None = None
        self._queue_lock = asyncio.Lock()
        if queue_db_path:
            self._queue = DanmakuQueue(queue_db_path, interval_sec=max(1, queue_interval_sec))
            self.logger.info(
                "使用持久化弹幕队列发送，数据库=%s，间隔=%ss",
                queue_db_path,
                queue_interval_sec,
            )

    def _get_room(self) -> live.LiveRoom:
        if self._room is None:
            # 使用 display_id 更友好
            self._room = live.LiveRoom(room_display_id=self.room_id, credential=self.credential)
        return self._room

    def _render(self, template: str, **kwargs: object) -> str:
        try:
            return template.format(**kwargs)
        except Exception:
            return template

    def _trim(self, message: str) -> tuple[str, bool]:
        if self.max_length and len(message) > self.max_length:
            return message[: self.max_length], True
        return message, False

    async def _enqueue_or_send(self, message: str) -> None:
        if not message:
            return
        trimmed, _ = self._trim(message.strip())
        if not trimmed:
            return

        if self._queue:
            await asyncio.to_thread(self._queue.enqueue, trimmed)
            await self._ensure_queue_worker()
            return

        await self._send_direct(trimmed)

    async def _send_direct(self, message: str) -> None:
        room = self._get_room()
        try:
            await room.send_danmaku(live.Danmaku(message))
        except ResponseCodeException as exc:
            if exc.code == 1003212:
                fallback_limit = max(1, (self.max_length or len(message)) - 1)
                fallback = message[:fallback_limit]
                if len(fallback) < len(message):
                    self.logger.warning(
                        "弹幕超长已截断 length=%s->%s content=%s", len(message), len(fallback), message
                    )
                    await room.send_danmaku(live.Danmaku(fallback))
                    return
            raise

    async def _ensure_queue_worker(self) -> None:
        if not self._queue:
            return
        async with self._queue_lock:
            if self._queue_task and not self._queue_task.done():
                return
            self._queue_task = asyncio.create_task(self._queue_loop())

    async def _queue_loop(self) -> None:
        assert self._queue is not None
        while True:
            msg: QueueMessage | None = await asyncio.to_thread(self._queue.claim_next)
            if msg is None:
                delay = await asyncio.to_thread(self._queue.next_available_delay)
                await asyncio.sleep(delay if delay is not None else 1.0)
                continue

            now = time.time()
            if msg.not_before > now:
                await asyncio.sleep(msg.not_before - now)

            try:
                await self._send_direct(msg.message)
            except ResponseCodeException as exc:
                if exc.code == 10030:
                    self.logger.warning("弹幕发送过快，%ss 后重试", self._queue.interval_sec)
                    await asyncio.to_thread(
                        self._queue.reschedule,
                        msg.id,
                        error=str(exc),
                    )
                    await asyncio.sleep(self._queue.interval_sec)
                    continue
                await asyncio.to_thread(self._queue.mark_failed, msg.id, str(exc))
                self.logger.exception("弹幕发送失败，已标记为失败")
                continue
            except Exception as exc:  # pragma: no cover - 防御性重试
                await asyncio.to_thread(self._queue.reschedule, msg.id, error=str(exc))
                self.logger.exception("弹幕发送异常，已重新入队")
                continue

            await asyncio.to_thread(self._queue.mark_sent, msg.id)

    async def send_thanks(self, uname: str, gift_name: str, num: int = 1) -> None:
        msg = self._render(self._thank_message_single, uname=uname, gift_name=gift_name, num=num)
        await self._enqueue_or_send(msg)

    async def send_guard_thanks(self, uname: str, guard_name: str) -> None:
        msg = self._render(self._thank_message_guard, uname=uname, guard_name=guard_name)
        await self._enqueue_or_send(msg)

    async def send_summary_thanks(self, uname: str, gifts: Mapping[str, int]) -> None:
        parts = [f"{name} x{count}" for name, count in gifts.items()]
        gift_text = "，".join(parts) if parts else "礼物"
        msg = self._render(self._thank_message_summary, uname=uname, gifts=gift_text)
        await self._enqueue_or_send(msg)

    async def send_custom_message(self, message: str) -> None:
        await self._enqueue_or_send(message)

    def reconfigure(
        self,
        *,
        room_id: int | None = None,
        credential: Credential | None = None,
        thank_message_single: str | None = None,
        thank_message_summary: str | None = None,
        thank_message_guard: str | None = None,
        max_length: int | None = None,
        queue_db_path: str | None = None,
        queue_interval_sec: int | None = None,
    ) -> None:
        if room_id is not None and room_id != self.room_id:
            self.room_id = room_id
            self._room = None
        if credential is not None and credential is not self.credential:
            self.credential = credential
            self._room = None
        if thank_message_single is not None:
            self._thank_message_single = thank_message_single
        if thank_message_summary is not None:
            self._thank_message_summary = thank_message_summary
        if thank_message_guard is not None:
            self._thank_message_guard = thank_message_guard
        if max_length is not None:
            self.max_length = max(0, max_length)
        if queue_db_path is not None:
            if queue_db_path:
                self._queue = DanmakuQueue(queue_db_path, interval_sec=max(1, queue_interval_sec or 3))
            else:
                if self._queue_task:
                    self._queue_task.cancel()
                self._queue = None
        elif queue_interval_sec is not None and self._queue is not None:
            self._queue.interval_sec = max(1, queue_interval_sec)
