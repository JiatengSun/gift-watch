from __future__ import annotations

from typing import Mapping, Optional

from bilibili_api import live, Credential

class DanmakuSender:
    def __init__(self, room_id: int, credential: Credential):
        self.room_id = room_id
        self.credential = credential
        self._room: Optional[live.LiveRoom] = None

    def _get_room(self) -> live.LiveRoom:
        if self._room is None:
            # 使用 display_id 更友好
            self._room = live.LiveRoom(room_display_id=self.room_id, credential=self.credential)
        return self._room

    async def send_thanks(self, uname: str, gift_name: str, num: int = 1) -> None:
        room = self._get_room()
        msg = f"谢谢 {uname} 送的 {gift_name} x{num}！太帅了！"
        # send_danmaku 需要 Danmaku 对象而非纯文本
        await room.send_danmaku(live.Danmaku(msg))

    async def send_guard_thanks(self, uname: str, guard_name: str) -> None:
        room = self._get_room()
        msg = f"感谢{uname}的{guard_name}！！你最帅了！"
        await room.send_danmaku(live.Danmaku(msg))

    async def send_summary_thanks(self, uname: str, gifts: Mapping[str, int]) -> None:
        room = self._get_room()
        parts = [f"{name} x{count}" for name, count in gifts.items()]
        gift_text = "，".join(parts) if parts else "礼物"
        msg = f"谢谢 {uname} 送的 {gift_text}！太帅了！"
        await room.send_danmaku(live.Danmaku(msg))
