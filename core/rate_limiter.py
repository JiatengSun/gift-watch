from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict

@dataclass
class RateLimiter:
    global_cooldown_sec: int
    per_user_cooldown_sec: int
    per_user_daily_limit: int = 0

    _last_global_ts: float = field(default=0.0, init=False)
    _last_user_ts: Dict[Any, float] = field(default_factory=dict, init=False)
    _user_day: Dict[Any, str] = field(default_factory=dict, init=False)
    _user_day_count: Dict[Any, int] = field(default_factory=dict, init=False)

    def _day_key(self, ts: float) -> str:
        return time.strftime("%Y-%m-%d", time.localtime(ts))

    def allow(self, uid: Any, ts: float | None = None, ignore_cooldown: bool = False) -> bool:
        now = ts or time.time()

        if not ignore_cooldown:
            if self.global_cooldown_sec > 0 and (now - self._last_global_ts) < self.global_cooldown_sec:
                return False

            last = self._last_user_ts.get(uid, 0.0)
            if self.per_user_cooldown_sec > 0 and (now - last) < self.per_user_cooldown_sec:
                return False

        day = self._day_key(now)
        last_day = self._user_day.get(uid)
        daily_count = self._user_day_count.get(uid, 0)
        if last_day != day:
            daily_count = 0

        if self.per_user_daily_limit > 0 and daily_count >= self.per_user_daily_limit:
            return False

        self._last_global_ts = now
        self._last_user_ts[uid] = now
        self._user_day[uid] = day
        self._user_day_count[uid] = daily_count + 1
        return True
