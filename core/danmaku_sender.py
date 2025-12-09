from __future__ import annotations

from typing import Optional

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
        msg = f"谢谢 {uname} 送的 {gift_name} x{num}！"
        # send_danmaku 需要 Danmaku 对象而非纯文本
        await room.send_danmaku(live.Danmaku(msg))
