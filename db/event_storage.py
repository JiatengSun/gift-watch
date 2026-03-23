from __future__ import annotations

import json


def build_gift_payload(
    *,
    ts: int,
    room_id: int,
    uid: int | None,
    uname: str,
    gift_id: int | None,
    gift_name: str,
    num: int,
    total_price: int,
) -> str:
    return json.dumps(
        {
            "kind": "gift",
            "ts": int(ts),
            "room_id": int(room_id),
            "uid": uid,
            "uname": uname or "",
            "gift_id": gift_id,
            "gift_name": gift_name or "",
            "num": int(num or 0),
            "total_price": int(total_price or 0),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def build_danmaku_payload(
    *,
    ts: int,
    room_id: int,
    uid: int | None,
    uname: str,
    content: str,
) -> str:
    return json.dumps(
        {
            "kind": "danmaku",
            "ts": int(ts),
            "room_id": int(room_id),
            "uid": uid,
            "uname": uname or "",
            "content": content or "",
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def normalize_payload(
    *,
    mode: str,
    fallback_payload: str | None,
    compact_payload: str,
) -> str | None:
    normalized_mode = (mode or "compact").strip().lower()
    if normalized_mode == "none":
        return None
    if normalized_mode == "full":
        return fallback_payload or None
    return compact_payload


def compact_json_text(raw_json: str | None, compact_payload: str) -> str | None:
    if raw_json is None:
        return None

    candidate = raw_json.strip()
    if not candidate:
        return None

    # Leave already-compact payloads untouched to avoid unnecessary rewrites.
    if candidate == compact_payload:
        return compact_payload

    return compact_payload
