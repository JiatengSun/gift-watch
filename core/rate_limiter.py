from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict

@dataclass
class RateLimiter:
    global_cooldown_sec: int
    per_user_cooldown_sec: int

    _last_global_ts: float = field(default=0.0, init=False)
    _last_user_ts: Dict[int, float] = field(default_factory=dict, init=False)

    def allow(self, uid: int) -> bool:
        now = time.time()

        if self.global_cooldown_sec > 0 and (now - self._last_global_ts) < self.global_cooldown_sec:
            return False

        last = self._last_user_ts.get(uid, 0.0)
        if self.per_user_cooldown_sec > 0 and (now - last) < self.per_user_cooldown_sec:
            return False

        self._last_global_ts = now
        self._last_user_ts[uid] = now
        return True
