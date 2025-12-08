from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict

@dataclass
class RateLimiter:
    global_cooldown_sec: int
    per_user_cooldown_sec: int
    per_user_daily: bool

    _last_global_ts: float = field(default=0.0, init=False)
    _last_user_ts: Dict[int, float] = field(default_factory=dict, init=False)
    _last_user_day: Dict[int, str] = field(default_factory=dict, init=False)

    def _day_key(self, ts: float) -> str:
        return time.strftime("%Y-%m-%d", time.localtime(ts))

    def allow(self, uid: int, ts: float | None = None) -> bool:
        now = ts or time.time()

        if self.global_cooldown_sec > 0 and (now - self._last_global_ts) < self.global_cooldown_sec:
            return False

        if self.per_user_daily:
            current_day = self._day_key(now)
            last_day = self._last_user_day.get(uid)
            if last_day == current_day:
                return False

        last = self._last_user_ts.get(uid, 0.0)
        if self.per_user_cooldown_sec > 0 and (now - last) < self.per_user_cooldown_sec:
            return False

        self._last_global_ts = now
        self._last_user_ts[uid] = now
        if self.per_user_daily:
            self._last_user_day[uid] = self._day_key(now)
        return True
