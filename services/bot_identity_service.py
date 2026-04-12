from __future__ import annotations

import hashlib
import threading
import time
import urllib.error
import urllib.request
from typing import Any

from config.settings import get_settings, resolve_env_file

_CACHE_TTL_SEC = 300
_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _cache_key(env_file: str | None, sessdata: str, bili_jct: str, buvid3: str) -> str:
    resolved = resolve_env_file(env_file) or ""
    raw = f"{resolved}|{sessdata}|{bili_jct}|{buvid3}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cookie_header(sessdata: str, bili_jct: str, buvid3: str) -> str:
    parts = [f"SESSDATA={sessdata}", f"bili_jct={bili_jct}"]
    if buvid3:
        parts.append(f"buvid3={buvid3}")
    return "; ".join(parts)


def _base_payload(env_file: str | None) -> dict[str, Any]:
    resolved = resolve_env_file(env_file)
    return {
        "env_file": resolved,
        "configured": False,
        "status": "missing_credentials",
        "uid": None,
        "uname": "",
        "message": "未配置发送号登录态",
        "checked_at": int(time.time()),
        "cache_hit": False,
    }


def detect_bot_identity(env_file: str | None) -> dict[str, Any]:
    settings = get_settings(env_file)
    sessdata = (settings.bot_sessdata or "").strip()
    bili_jct = (settings.bot_bili_jct or "").strip()
    buvid3 = (settings.bot_buvid3 or "").strip()

    payload = _base_payload(env_file)
    if not sessdata or not bili_jct:
        return payload

    key = _cache_key(env_file, sessdata, bili_jct, buvid3)
    now = time.time()
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached and now - cached[0] <= _CACHE_TTL_SEC:
            cached_payload = dict(cached[1])
            cached_payload["cache_hit"] = True
            return cached_payload

    request = urllib.request.Request(
        "https://api.bilibili.com/x/web-interface/nav",
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/127.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.bilibili.com/",
            "Cookie": _cookie_header(sessdata, bili_jct, buvid3),
        },
    )

    result = dict(payload)
    result["configured"] = True
    try:
        with urllib.request.urlopen(request, timeout=2) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        result["status"] = "request_failed"
        result["message"] = f"检测失败：HTTP {exc.code}"
    except Exception as exc:
        result["status"] = "request_failed"
        result["message"] = f"检测失败：{type(exc).__name__}"
    else:
        import json

        try:
            payload_json = json.loads(raw)
            data = payload_json.get("data") if isinstance(payload_json, dict) else None
        except Exception:
            payload_json = None
            data = None

        if not isinstance(payload_json, dict) or not isinstance(data, dict):
            result["status"] = "request_failed"
            result["message"] = "检测失败：返回格式异常"
        elif payload_json.get("code") != 0:
            result["status"] = "request_failed"
            result["message"] = f"检测失败：code={payload_json.get('code')}"
        elif not data.get("isLogin"):
            result["status"] = "login_required"
            result["message"] = "发送号登录已失效"
        else:
            uid = data.get("mid")
            uname = str(data.get("uname") or "").strip()
            try:
                uid = int(uid) if uid is not None else None
            except Exception:
                uid = None
            result.update(
                {
                    "status": "ok",
                    "uid": uid,
                    "uname": uname,
                    "message": f"{uname or '已登录账号'}" + (f" (UID {uid})" if uid else ""),
                }
            )

    result["checked_at"] = int(time.time())
    result["cache_hit"] = False
    with _CACHE_LOCK:
        _CACHE[key] = (time.time(), dict(result))
    return result
