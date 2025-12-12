from __future__ import annotations

from datetime import datetime, time, timedelta

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from config.env_store import save_env
from config.settings import DEFAULT_ENV_FILE, Settings, get_settings, resolve_env_file
from db.repo import (
    delete_gift_by_id,
    query_gift_by_id,
    query_gifts_by_uname,
    query_gifts_by_uname_and_gift,
    query_recent_gifts,
    query_flow_summary,
)
from services.gift_list_service import fetch_room_gift_list

router = APIRouter()


def _resolve_env(env: str | None) -> str | None:
    effective = (env or "").strip()
    return resolve_env_file(effective or DEFAULT_ENV_FILE)


class ThankTemplatesPayload(BaseModel):
    summary: str = Field(..., description="汇总感谢弹幕模板")
    guard: str = Field(..., description="大航海感谢弹幕模板")
    single: str = Field(..., description="单个礼物感谢弹幕模板")


class SettingsPayload(BaseModel):
    thank_guard: bool = Field(True, description="是否感谢大航海")
    thank_mode: str = Field("count", description="感谢模式 count/value")
    target_gifts: list[str] = Field(default_factory=list, description="目标礼物名")
    target_gift_ids: list[int] = Field(default_factory=list, description="目标礼物 ID")
    target_min_num: int = Field(1, ge=1, description="数量阈值")
    thank_per_user_daily_limit: int = Field(0, ge=0, description="单日感谢次数上限，0 表示不限制")
    thank_value_threshold: int = Field(0, ge=0, description="单次礼物总价阈值，单位金瓜子")
    thank_templates: ThankTemplatesPayload
    announce_enabled: bool = Field(False, description="定时弹幕是否启用")
    announce_interval_sec: int = Field(300, ge=30, description="定时弹幕间隔秒")
    announce_message: str = Field("", description="定时弹幕内容，多行会轮播发送")
    announce_skip_offline: bool = Field(True, description="未开播时是否跳过")
    announce_mode: str = Field("interval", description="定时弹幕模式 interval/message_count")
    announce_danmaku_threshold: int = Field(5, ge=1, description="弹幕触发模式下的计数阈值")

    @field_validator("thank_mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        v = (v or "").lower()
        return v if v in {"count", "value"} else "count"

    @field_validator("announce_mode")
    @classmethod
    def validate_announce_mode(cls, v: str) -> str:
        v = (v or "").lower()
        return v if v in {"interval", "message_count"} else "interval"


def _serialize_settings(settings: Settings) -> dict:
    return {
        "thank_guard": settings.thank_guard,
        "thank_mode": settings.thank_mode,
        "target_gifts": settings.target_gifts,
        "target_gift_ids": settings.target_gift_ids,
        "target_min_num": settings.target_min_num,
        "thank_per_user_daily_limit": settings.thank_per_user_daily_limit,
        "thank_value_threshold": settings.thank_value_threshold,
        "thank_templates": {
            "single": settings.thank_message_single,
            "summary": settings.thank_message_summary,
            "guard": settings.thank_message_guard,
        },
        "announce_enabled": settings.announce_enabled,
        "announce_interval_sec": settings.announce_interval_sec,
        "announce_message": "\n".join(settings.announce_messages),
        "announce_skip_offline": settings.announce_skip_offline,
        "announce_mode": settings.announce_mode,
        "announce_danmaku_threshold": settings.announce_danmaku_threshold,
    }


def _env_payload_from_settings(payload: SettingsPayload) -> dict[str, str]:
    gifts = ",".join([g.strip() for g in payload.target_gifts if g.strip()])
    gift_ids = ",".join([str(i) for i in payload.target_gift_ids if i])
    return {
        "TARGET_GIFTS": gifts,
        "TARGET_GIFT_IDS": gift_ids,
        "TARGET_MIN_NUM": str(max(payload.target_min_num, 1)),
        "THANK_PER_USER_DAILY_LIMIT": str(max(payload.thank_per_user_daily_limit, 0)),
        "THANK_MODE": payload.thank_mode,
        "THANK_VALUE_THRESHOLD": str(max(payload.thank_value_threshold, 0)),
        "THANK_GUARD": "1" if payload.thank_guard else "0",
        "THANK_MESSAGE_SINGLE": payload.thank_templates.single,
        "THANK_MESSAGE_SUMMARY": payload.thank_templates.summary,
        "THANK_MESSAGE_GUARD": payload.thank_templates.guard,
        "ANNOUNCE_ENABLED": "1" if payload.announce_enabled else "0",
        "ANNOUNCE_INTERVAL_SEC": str(max(payload.announce_interval_sec, 30)),
        "ANNOUNCE_MESSAGE": payload.announce_message,
        "ANNOUNCE_SKIP_OFFLINE": "1" if payload.announce_skip_offline else "0",
        "ANNOUNCE_MODE": payload.announce_mode,
        "ANNOUNCE_DANMAKU_THRESHOLD": str(max(payload.announce_danmaku_threshold, 1)),
    }


def _default_start_ts(now: datetime) -> int:
    eight_am = datetime.combine(now.date(), time(8, 0))
    if eight_am > now:
        eight_am = eight_am - timedelta(days=1)
    return int(eight_am.timestamp())


@router.get("/api/search")
def search(
    uname: str = Query(..., description="用户名"),
    gift_name: str | None = Query(None, description="礼物名"),
    guard_level: int | None = Query(None, ge=1, le=3, description="大航海等级：1=总督 2=提督 3=舰长"),
    limit: int = Query(200, ge=1, le=1000),
    start_ts: int | None = Query(None, description="开始时间（Unix 秒）"),
    env: str | None = Query(None, description="可选 .env 文件路径，用于绑定前端/后端"),
):
    settings = get_settings(_resolve_env(env))
    now = datetime.now()
    effective_start_ts = start_ts if start_ts is not None else _default_start_ts(now)
    end_ts = int(now.timestamp())

    if gift_name:
        rows = query_gifts_by_uname_and_gift(
            settings,
            uname=uname,
            gift_name=gift_name,
            limit=limit,
            start_ts=effective_start_ts,
            end_ts=end_ts,
            guard_level=guard_level,
        )
    else:
        rows = query_gifts_by_uname(
            settings, uname=uname, limit=limit, start_ts=effective_start_ts, end_ts=end_ts, guard_level=guard_level
        )

    return [
        {
            "id": r[0],
            "ts": r[1],
            "uid": r[2],
            "uname": r[3],
            "gift_name": r[4],
            "num": r[5],
            "total_price": r[6],
        }
        for r in rows
    ]


@router.get("/api/gifts")
def list_gifts(
    limit: int = Query(200, ge=1, le=1000),
    start_ts: int | None = Query(None, description="开始时间（Unix 秒）"),
    end_ts: int | None = Query(None, description="结束时间（Unix 秒）"),
    uname: str | None = Query(None, description="用户名"),
    gift_name: str | None = Query(None, description="礼物名"),
    guard_level: int | None = Query(None, ge=1, le=3, description="大航海等级：1=总督 2=提督 3=舰长"),
    env: str | None = Query(None, description="可选 .env 文件路径，用于绑定前端/后端"),
):
    settings = get_settings(_resolve_env(env))
    rows = query_recent_gifts(
        settings,
        limit=limit,
        start_ts=start_ts,
        end_ts=end_ts,
        uname=uname,
        gift_name=gift_name,
        guard_level=guard_level,
    )

    return [
        {
            "id": r[0],
            "ts": r[1],
            "uid": r[2],
            "uname": r[3],
            "gift_name": r[4],
            "num": r[5],
            "total_price": r[6],
        }
        for r in rows
    ]


@router.get("/api/gifts/{gift_id}")
def get_gift(gift_id: int, env: str | None = Query(None, description="可选 .env 文件路径，用于绑定前端/后端")):
    settings = get_settings(_resolve_env(env))
    row = query_gift_by_id(settings, gift_id)
    if not row:
        raise HTTPException(status_code=404, detail="记录不存在")

    return {
        "id": row[0],
        "ts": row[1],
        "uid": row[2],
        "uname": row[3],
        "gift_name": row[4],
        "num": row[5],
        "total_price": row[6],
    }


@router.delete("/api/gifts/{gift_id}")
def delete_gift(gift_id: int, env: str | None = Query(None, description="可选 .env 文件路径，用于绑定前端/后端")):
    settings = get_settings(_resolve_env(env))
    deleted = delete_gift_by_id(settings, gift_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="记录不存在或已删除")
    return {"deleted": True, "id": gift_id}


@router.get("/api/room_gift_list")
def room_gift_list(env: str | None = Query(None, description="可选 .env 文件路径，用于绑定前端/后端")):
    settings = get_settings(_resolve_env(env))
    return fetch_room_gift_list(settings)


@router.get("/api/summary")
def summary(
    start_ts: int | None = Query(None, description="开始时间（Unix 秒）"),
    end_ts: int | None = Query(None, description="结束时间（Unix 秒）"),
    env: str | None = Query(None, description="可选 .env 文件路径，用于绑定前端/后端"),
):
    settings = get_settings(_resolve_env(env))
    return query_flow_summary(settings, start_ts=start_ts, end_ts=end_ts)


@router.get("/api/settings")
def read_settings(env: str | None = Query(None, description="可选 .env 文件路径")):
    settings = get_settings(_resolve_env(env))
    return _serialize_settings(settings)


@router.post("/api/settings")
def update_settings(
    payload: SettingsPayload = Body(..., description="配置内容"),
    env: str | None = Query(None, description="可选 .env 文件路径"),
):
    env_payload = _env_payload_from_settings(payload)
    resolved_env = _resolve_env(env)
    save_env(env_payload, resolved_env)
    settings = get_settings(resolved_env)
    return _serialize_settings(settings)


@router.get("/api/check")
def check(
    uname: str = Query(...),
    gift_name: str = Query(...),
    env: str | None = Query(None, description="可选 .env 文件路径，用于绑定前端/后端"),
):
    settings = get_settings(_resolve_env(env))
    rows = query_gifts_by_uname_and_gift(settings, uname=uname, gift_name=gift_name, limit=1)
    if not rows:
        return {"found": False, "latest": None}

    r = rows[0]
    return {
        "found": True,
        "latest": {
            "id": r[0],
            "ts": r[1],
            "uid": r[2],
            "uname": r[3],
            "gift_name": r[4],
            "num": r[5],
            "total_price": r[6],
        },
    }
