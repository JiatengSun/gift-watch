from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
import unicodedata

from core.gift_parser import GiftEvent

def _normalize_gift_name(name: str) -> str:
    """Normalize gift names for robust matching.

    - Strip surrounding whitespace to avoid mismatches caused by padding
    - Case-fold to make matching insensitive to accidental casing differences
    - Normalize unicode width/compatibility so full-width commas/spaces don't break
      matching when configs are copied from Chinese sources
    """

    normalized = unicodedata.normalize("NFKC", name or "")
    return normalized.strip().casefold()


@dataclass
class GiftRule:
    target_gift_names: set[str]
    target_gift_ids: set[int]
    min_num: int

    def hit(self, gift: GiftEvent) -> bool:
        """Return True when the gift meets quantity plus name/id matching rules.

        - First enforce `min_num`; no matching occurs if 数量不足。
        - 如果配置了名字列表，则对礼物名做 NFKC + 去空白 + casefold 后检查集合。
        - 如果配置了 ID 列表，则直接检查礼物 ID 是否在集合中。
        - 当名字和 ID 都配置时，两条检查独立进行，只要有任意一条命中即可触发
          感谢（逻辑或）。
        """
        if gift.num < self.min_num:
            return False

        name_hit = False
        if self.target_gift_names:
            normalized_name = _normalize_gift_name(gift.gift_name)
            name_hit = normalized_name in self.target_gift_names

        id_hit = False
        if self.target_gift_ids and gift.gift_id:
            id_hit = gift.gift_id in self.target_gift_ids

        return name_hit or id_hit


def build_rule(
    target_gift_names: Iterable[str], target_gift_ids: Iterable[int], min_num: int
) -> GiftRule:
    normalized_targets = [_normalize_gift_name(g) for g in target_gift_names]
    return GiftRule(
        target_gift_names=set([g for g in normalized_targets if g]),
        target_gift_ids=set([i for i in target_gift_ids if i]),
        min_num=min_num,
    )
