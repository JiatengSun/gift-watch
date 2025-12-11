from __future__ import annotations

from typing import Mapping, Optional

from bilibili_api import live, Credential

class DanmakuSender:
    def __init__(
        self,
        room_id: int,
        credential: Credential,
        *,
        thank_message_single: str,
        thank_message_summary: str,
        thank_message_guard: str,
    ):
        self.room_id = room_id
        self.credential = credential
        self._room: Optional[live.LiveRoom] = None
        self._thank_message_single = thank_message_single
        self._thank_message_summary = thank_message_summary
        self._thank_message_guard = thank_message_guard

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

    async def _send(self, message: str) -> None:
        if not message:
            return
        room = self._get_room()
        await room.send_danmaku(live.Danmaku(message))

    async def send_thanks(self, uname: str, gift_name: str, num: int = 1) -> None:
        msg = self._render(self._thank_message_single, uname=uname, gift_name=gift_name, num=num)
        await self._send(msg)

    async def send_guard_thanks(self, uname: str, guard_name: str) -> None:
        msg = self._render(self._thank_message_guard, uname=uname, guard_name=guard_name)
        await self._send(msg)

    async def send_summary_thanks(self, uname: str, gifts: Mapping[str, int]) -> None:
        parts = [f"{name} x{count}" for name, count in gifts.items()]
        gift_text = "，".join(parts) if parts else "礼物"
        msg = self._render(self._thank_message_summary, uname=uname, gifts=gift_text)
        await self._send(msg)

    async def send_custom_message(self, message: str) -> None:
        await self._send(message)
