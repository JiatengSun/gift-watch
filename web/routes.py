from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time, timedelta
import json

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from zoneinfo import ZoneInfo

from config.env_store import save_env
from config.settings import DEFAULT_ENV_FILE, Settings, get_settings, resolve_env_file
from db.repo import (
    delete_gift_by_id,
    query_gift_by_id,
    query_gifts_by_uname,
    query_gifts_by_uname_and_gift,
    query_recent_gifts_paginated,
    query_recent_gifts,
    query_flow_summary,
    query_user_events,
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
    blind_box_enabled: bool = Field(True, description="盲盒盈亏查询是否启用")
    blind_box_triggers: list[str] = Field(default_factory=list, description="触发短句")
    blind_box_base_gift: str = Field("心动盲盒", description="盲盒基础礼物名")
    blind_box_rewards: list[str] = Field(default_factory=list, description="盲盒可能开出的礼物")
    blind_box_template: str = Field("", description="盲盒盈亏回复模板")
    blind_box_send_danmaku: bool = Field(True, description="是否发送盲盒盈亏弹幕")

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
        "blind_box_enabled": settings.blind_box_enabled,
        "blind_box_triggers": settings.blind_box_triggers,
        "blind_box_base_gift": settings.blind_box_base_gift,
        "blind_box_rewards": settings.blind_box_rewards,
        "blind_box_template": settings.blind_box_template,
        "blind_box_send_danmaku": settings.blind_box_send_danmaku,
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
        "BLIND_BOX_ENABLED": "1" if payload.blind_box_enabled else "0",
        "BLIND_BOX_TRIGGERS": ",".join(payload.blind_box_triggers),
        "BLIND_BOX_BASE_GIFT": payload.blind_box_base_gift,
        "BLIND_BOX_REWARDS": ",".join(payload.blind_box_rewards),
        "BLIND_BOX_TEMPLATE": payload.blind_box_template,
        "BLIND_BOX_SEND_DANMAKU": "1" if payload.blind_box_send_danmaku else "0",
    }


def _default_start_ts(now: datetime) -> int:
    eight_am = datetime.combine(now.date(), time(8, 0))
    if eight_am > now:
        eight_am = eight_am - timedelta(days=1)
    return int(eight_am.timestamp())


def _align_session_start(dt: datetime, session_start_hour: int = 8) -> datetime:
    anchor = dt.replace(hour=session_start_hour, minute=0, second=0, microsecond=0)
    if dt < anchor:
        anchor = anchor - timedelta(days=1)
    return anchor


def _extract_message_length(raw_json: str) -> int:
    try:
        data = json.loads(raw_json)
    except Exception:
        return 0

    text = ""
    if isinstance(data, dict):
        for key in ("msg", "message", "content", "text"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                text = val.strip()
                break

        if not text:
            info = data.get("info")
            if isinstance(info, (list, tuple)) and len(info) > 1 and isinstance(info[1], str):
                text = info[1].strip()

    return len(text)


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


@router.get("/api/gifts/paged")
def list_gifts_paginated(
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(50, ge=1, le=500, description="每页条数"),
    start_ts: int | None = Query(None, description="开始时间（Unix 秒）"),
    end_ts: int | None = Query(None, description="结束时间（Unix 秒）"),
    uname: str | None = Query(None, description="用户名"),
    gift_name: str | None = Query(None, description="礼物名"),
    guard_level: int | None = Query(None, ge=1, le=3, description="大航海等级：1=总督 2=提督 3=舰长"),
    env: str | None = Query(None, description="可选 .env 文件路径，用于绑定前端/后端"),
):
    settings = get_settings(_resolve_env(env))
    total, rows = query_recent_gifts_paginated(
        settings,
        page=page,
        page_size=page_size,
        start_ts=start_ts,
        end_ts=end_ts,
        uname=uname,
        gift_name=gift_name,
        guard_level=guard_level,
    )

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": [
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
        ],
    }


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


@router.get("/api/ops/engagement")
def engagement_panel(
    session_count: int = Query(6, ge=1, le=30, description="需要统计的场次数"),
    lookback: int = Query(3, ge=1, le=30, description="老观众需要连续出现的场次"),
    end_ts: int | None = Query(None, description="最近一场的结束时间（Unix 秒），默认当前时间"),
    env: str | None = Query(None, description="可选 .env 文件路径"),
):
    settings = get_settings(_resolve_env(env))
    tz = ZoneInfo("Asia/Shanghai")
    now = datetime.now(tz)
    anchor_end = datetime.fromtimestamp(end_ts, tz) if end_ts else now

    effective_lookback = max(min(lookback, session_count - 1), 1) if session_count > 1 else 1
    aligned_start = _align_session_start(anchor_end)
    aligned_end = aligned_start + timedelta(days=1)

    ranges: list[tuple[datetime, datetime]] = []
    cur_start, cur_end = aligned_start, aligned_end
    for _ in range(session_count):
        ranges.append((cur_start, cur_end))
        cur_end = cur_start
        cur_start = cur_start - timedelta(days=1)
    ranges.reverse()

    session_users: list[set[str]] = []
    seen_users: set[str] = set()
    user_stats: dict[str, dict] = defaultdict(
        lambda: {
            "uid": None,
            "uname": "",
            "sessions": set(),
            "message_count": 0,
            "total_price": 0,
            "total_length": 0,
            "sent_gift": False,
            "first_ts": None,
            "last_ts": None,
        }
    )

    session_rows: list[dict] = []

    for idx, (start_dt, end_dt) in enumerate(ranges):
        rows = query_user_events(settings, int(start_dt.timestamp()), int(end_dt.timestamp()))
        users_this_session: set[str] = set()

        for uid, uname, raw_json, gift_id, total_price, ts in rows:
            key = str(uid) if uid is not None else (uname or "")
            if not key:
                continue

            profile = user_stats[key]
            profile["uid"] = uid
            profile["uname"] = uname
            profile["sessions"].add(idx)
            profile["message_count"] += 1
            profile["total_price"] += int(total_price or 0)
            profile["total_length"] += _extract_message_length(raw_json or "")
            profile["sent_gift"] = profile["sent_gift"] or bool(gift_id) or (total_price or 0) > 0
            profile["first_ts"] = ts if profile["first_ts"] is None else min(profile["first_ts"], ts)
            profile["last_ts"] = ts if profile["last_ts"] is None else max(profile["last_ts"], ts)

            users_this_session.add(key)

        session_users.append(users_this_session)
        prior_sets = session_users[-effective_lookback - 1 : -1]
        returning = set(users_this_session)
        if len(prior_sets) >= effective_lookback:
            for s in prior_sets[-effective_lookback:]:
                returning &= s
        else:
            returning = set()

        new_users = users_this_session - seen_users
        seen_users |= users_this_session

        session_rows.append(
            {
                "label": start_dt.strftime("%m/%d %H:%M") + " - " + end_dt.strftime("%m/%d %H:%M"),
                "start_ts": int(start_dt.timestamp()),
                "end_ts": int(end_dt.timestamp()),
                "active_count": len(users_this_session),
                "returning_count": len(returning),
                "new_count": len(new_users),
            }
        )

    users_out = []
    for key, data in user_stats.items():
        if not data["sessions"]:
            continue
        msg_count = data["message_count"]
        total_len = data["total_length"]
        users_out.append(
            {
                "uid": data["uid"],
                "uname": data["uname"] or key,
                "session_count": len(data["sessions"]),
                "message_count": msg_count,
                "avg_length": round(total_len / msg_count, 1) if msg_count else 0,
                "total_price": data["total_price"],
                "sent_gift": data["sent_gift"],
                "first_ts": data["first_ts"],
                "last_ts": data["last_ts"],
            }
        )

    users_out.sort(key=lambda r: (-r["message_count"], -r["session_count"], -(r["last_ts"] or 0)))
    session_rows.reverse()

    return {
        "lookback": effective_lookback,
        "session_count": session_count,
        "session_hours": 24,
        "anchor_end_ts": int(aligned_end.timestamp()),
        "sessions": session_rows,
        "users": users_out,
    }


def _normalize_time_range(range_key: str, tz: ZoneInfo) -> tuple[datetime, datetime, int, bool]:
    now = datetime.now(tz)
    range_key = (range_key or "today").lower()

    if range_key == "today":
        start = datetime(now.year, now.month, now.day, tzinfo=tz)
        return start, now, 300, False

    if range_key == "week":
        start = datetime(now.year, now.month, now.day, tzinfo=tz) - timedelta(days=6)
        end = datetime(now.year, now.month, now.day, tzinfo=tz) + timedelta(days=1)
        return start, end, 24 * 3600, True

    if range_key == "month":
        start = datetime(now.year, now.month, 1, tzinfo=tz)
        end = datetime(now.year, now.month, now.day, tzinfo=tz) + timedelta(days=1)
        return start, end, 24 * 3600, True

    start = datetime(now.year, now.month, now.day, tzinfo=tz) - timedelta(days=89)
    end = datetime(now.year, now.month, now.day, tzinfo=tz) + timedelta(days=1)
    return start, end, 24 * 3600, True


@router.get("/api/ops/timeline")
def ops_timeline(
    range_key: str = Query("today", description="时间范围：today/week/month/all"),
    end_ts: int | None = Query(None, description="可选覆盖结束时间，Unix 秒"),
    env: str | None = Query(None, description="可选 .env 文件路径"),
):
    settings = get_settings(_resolve_env(env))
    tz = ZoneInfo("Asia/Shanghai")
    start_dt, default_end, bucket_seconds, cumulative = _normalize_time_range(range_key, tz)

    if end_ts:
        default_end = datetime.fromtimestamp(end_ts, tz)

    rows = query_user_events(settings, int(start_dt.timestamp()), int(default_end.timestamp()))
    start_ts = int(start_dt.timestamp())
    end_ts_val = int(default_end.timestamp())

    if range_key == "today":
        ts_values = [int(ts) for *_rest, ts in rows if ts is not None]
        if ts_values:
            earliest = min(ts_values)
            latest = max(ts_values)
            start_ts = max(start_ts, (earliest // bucket_seconds) * bucket_seconds)
            end_ts_val = min(
                end_ts_val,
                max(start_ts + bucket_seconds, ((latest // bucket_seconds) + 1) * bucket_seconds),
            )

    total_buckets = max(1, int((end_ts_val - start_ts) / bucket_seconds) + 1)

    bucket_users: list[set[str]] = [set() for _ in range(total_buckets)]

    def uid_key(uid, uname):
        return str(uid) if uid is not None else (uname or "")

    for uid, uname, _raw_json, _gift_id, _price, ts in rows:
        if ts is None:
            continue
        key = uid_key(uid, uname)
        if not key:
            continue
        if ts < start_ts or ts >= end_ts_val:
            continue
        idx = min(total_buckets - 1, max(0, int((ts - start_ts) // bucket_seconds)))
        bucket_users[idx].add(key)

    seen: set[str] = set()
    points: list[dict] = []
    for idx, users in enumerate(bucket_users):
        if cumulative:
            seen |= users
            value = len(seen)
        else:
            value = len(users)

        points.append({"ts": start_ts + idx * bucket_seconds, "value": value})

    metric = "ONLINE_RANK_COUNT" if not cumulative else "WATCHED_CHANGE"
    metric_label = "同时在线人数" if metric == "ONLINE_RANK_COUNT" else "累计进房人数"

    return {
        "range": range_key,
        "start_ts": start_ts,
        "end_ts": end_ts_val,
        "bucket_seconds": bucket_seconds,
        "metric": metric,
        "metric_label": metric_label,
        "points": points,
    }


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
