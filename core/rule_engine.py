from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from core.gift_parser import GiftEvent

@dataclass
class GiftRule:
    target_gifts: set[str]
    min_num: int

    def hit(self, gift: GiftEvent) -> bool:
        return gift.gift_name in self.target_gifts and gift.num >= self.min_num

def build_rule(target_gifts: Iterable[str], min_num: int) -> GiftRule:
    return GiftRule(
        target_gifts=set([g.strip() for g in target_gifts if g.strip()]),
        min_num=min_num,
    )
