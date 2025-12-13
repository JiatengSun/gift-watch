from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional, Any

import fcntl

import aiohttp
from bilibili_api import live

from config.settings import Settings, get_settings
from core.danmaku_sender import DanmakuSender


class AnnouncementService:
    """Periodically send danmaku to keep the room warm."""

    def __init__(self, env_file: str | None, settings: Settings, sender: DanmakuSender):
        self.env_file = env_file
        self.settings = settings
        self.sender = sender
        self.logger = logging.getLogger(__name__)
        self._task: Optional[asyncio.Task] = None
        self._message_index: int = 0
        self._last_messages: list[str] | None = None
        self._credential = getattr(sender, "credential", None)
        self._danmaku: Optional[live.LiveDanmaku] = None
        self._danmaku_task: Optional[asyncio.Task] = None
        self._danmaku_count: int = 0
        self._send_lock = asyncio.Lock()
        self._self_uid = getattr(getattr(sender, "credential", None), "dedeuserid", None)
        self._last_log_state: tuple[Any, ...] | None = None
        lock_name = f"gift-watch-announce-{settings.room_id}"
        if env_file:
            safe_env = Path(env_file).name.replace(os.sep, "_")
            lock_name += f"-{safe_env}"
        self._lock_path = Path(tempfile.gettempdir()) / f"{lock_name}.lock"
        self._lock_fd: Optional[int] = None

    async def _is_live(self, settings: Settings) -> bool:
        if not settings.announce_skip_offline:
            return True

        url = f"https://api.live.bilibili.com/room/v1/Room/room_init?id={settings.room_id}"
        headers = {
            # B 站接口如果没有常见浏览器 UA 会返回 412，补充请求头提升成功率。
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/127.0.0.0 Safari/537.36"
            ),
            "Referer": "https://live.bilibili.com/",
        }
        timeout = aiohttp.ClientTimeout(total=5)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers) as resp:
                    resp.raise_for_status()
                    payload = await resp.json()
        except Exception as exc:
            self.logger.debug("定时弹幕检查直播状态失败", exc_info=exc)
            return False

        if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
            return False
        return payload["data"].get("live_status") == 1

    async def _handle_danmaku_event(self, event: dict[str, Any]) -> None:
        if self._danmaku_task is None or self._danmaku_task.done():
            return

        settings = get_settings(self.env_file)
        if settings.announce_mode != "message_count" or not settings.announce_enabled:
            return

        uid = self._extract_uid(event)
        if uid and self._self_uid and str(uid) == str(self._self_uid):
            return

        self._danmaku_count += 1
        threshold = max(settings.announce_danmaku_threshold, 1)
        if self._danmaku_count < threshold:
            self.logger.debug(
                "弹幕触发计数：%s/%s（忽略自己发送的弹幕）", self._danmaku_count, threshold
            )
            return

        self._danmaku_count = 0
        self.logger.debug("弹幕触发计数达到阈值 %s，准备发送定时弹幕", threshold)
        await self._send_next_message(settings)

    def _acquire_lock(self) -> bool:
        if self._lock_fd is not None:
            return True

        try:
            fd = os.open(self._lock_path, os.O_RDWR | os.O_CREAT, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._lock_fd = fd
            return True
        except BlockingIOError:
            try:
                os.close(fd)
            except Exception:
                pass
            return False
        except Exception:
            return False

    def _release_lock(self) -> None:
        if self._lock_fd is None:
            return
        try:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            os.close(self._lock_fd)
        finally:
            self._lock_fd = None

    def _extract_uid(self, event: dict[str, Any]) -> Optional[int]:
        info = event.get("info") or event.get("data") or {}
        if isinstance(info, dict):
            info = info.get("info") or info
        if isinstance(info, (list, tuple)) and len(info) >= 3:
            uid_info = info[2]
            if isinstance(uid_info, (list, tuple)) and uid_info:
                try:
                    return int(uid_info[0])
                except Exception:
                    return None
        return None

    async def _send_next_message(self, settings: Settings) -> None:
        messages = [msg.strip() for msg in settings.announce_messages if msg.strip()]
        if not settings.announce_enabled or not messages:
            return

        async with self._send_lock:
            try:
                if not await self._is_live(settings):
                    self.logger.debug("房间未开播，跳过弹幕触发的定时弹幕")
                    return
                message = messages[self._message_index % len(messages)]
                self._message_index = (self._message_index + 1) % len(messages)
                await self.sender.send_custom_message(message)
            except Exception:
                self.logger.exception("发送定时弹幕失败")

    async def _ensure_danmaku_listener(self, settings: Settings) -> None:
        if self._danmaku_task and not self._danmaku_task.done():
            return

        self._danmaku_count = 0
        self._danmaku = live.LiveDanmaku(settings.room_id, credential=self._credential)

        bound = False
        try:
            @self._danmaku.on("DANMU_MSG")
            async def _wrapped(event: dict[str, Any]):
                await self._handle_danmaku_event(event)

            bound = True
        except Exception:
            pass

        if not bound:
            try:
                self._danmaku.add_event_listener("DANMU_MSG", self._handle_danmaku_event)
                bound = True
            except Exception as exc:  # pragma: no cover - 兼容老版本 bilibili-api
                self.logger.debug("弹幕监听绑定失败", exc_info=exc)

        if not bound:
            self.logger.warning("无法绑定 DANMU_MSG 事件，弹幕触发模式不可用")
            self._danmaku = None
            return

        async def _runner() -> None:
            try:
                await self._danmaku.connect()
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger.exception("监听弹幕消息时出错")
            finally:
                self._danmaku = None

        self._danmaku_task = asyncio.create_task(_runner())

    async def _stop_danmaku_listener(self) -> None:
        if self._danmaku_task:
            self._danmaku_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._danmaku_task
        self._danmaku_task = None
        self._danmaku = None
        self._danmaku_count = 0

    async def _loop(self) -> None:
        # Reload settings on every iteration so config changes apply without restart.
        try:
            while True:
                try:
                    if not self._acquire_lock():
                        signature = ("locked",)
                        if signature != self._last_log_state:
                            self.logger.warning(
                                "检测到其他定时弹幕实例正在运行，当前实例暂停发送 (lock=%s)",
                                self._lock_path,
                            )
                            self._last_log_state = signature
                        await asyncio.sleep(10)
                        continue

                    settings = get_settings(self.env_file)
                    interval = max(settings.announce_interval_sec, 30)
                    messages = [msg.strip() for msg in settings.announce_messages if msg.strip()]
                    if messages != self._last_messages:
                        self._message_index = 0
                        self._last_messages = list(messages)

                    if not settings.announce_enabled or not messages:
                        signature = ("disabled", settings.announce_enabled, bool(messages))
                        if signature != self._last_log_state:
                            self.logger.debug("定时弹幕未启用或内容为空，等待配置更新后再检查")
                            self._last_log_state = signature
                        await self._stop_danmaku_listener()
                        await asyncio.sleep(interval)
                        continue

                    if settings.announce_mode == "message_count":
                        await self._ensure_danmaku_listener(settings)
                        signature = (
                            "message_count",
                            max(settings.announce_danmaku_threshold, 1),
                            settings.announce_skip_offline,
                        )
                        if signature != self._last_log_state:
                            self.logger.debug(
                                "定时弹幕检查: 弹幕触发模式，阈值 %s 条，开播时发送=%s",
                                signature[1],
                                signature[2],
                            )
                            self._last_log_state = signature
                        await asyncio.sleep(5)
                        continue

                    await self._stop_danmaku_listener()
                    signature = ("interval", interval, settings.announce_skip_offline)
                    if signature != self._last_log_state:
                        self.logger.debug(
                            "定时弹幕检查: 间隔 %ss，开播时发送=%s",
                            interval,
                            settings.announce_skip_offline,
                        )
                        self._last_log_state = signature

                    await self._send_next_message(settings)
                    await asyncio.sleep(interval)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self.logger.exception("定时弹幕循环异常，5 秒后重试")
                    await asyncio.sleep(5)
        finally:
            await self._stop_danmaku_listener()
            self._release_lock()

    def start(self) -> asyncio.Task:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())
        return self._task
