"""基于已确认 ZigZag Pivot 的江恩结构锚点。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from app.wave.pivots import WavePivot, confirmed_zigzag_pivots


@dataclass(frozen=True, slots=True)
class GannAnchor:
    """只使用右侧确认数据发布的江恩锚点。"""

    direction: Literal["up", "down"]
    pivot: WavePivot
    previous_pivot: WavePivot
    atr: float

    def as_dict(self) -> dict[str, object]:
        return {
            "direction": self.direction,
            "kind": self.pivot.kind,
            "position": self.pivot.position,
            "confirmation_position": self.pivot.confirmation_position,
            "timestamp": self.pivot.timestamp.isoformat(),
            "confirmed_at": None,
            "price": round(self.pivot.price, 6),
            "previous_price": round(self.previous_pivot.price, 6),
            "atr": round(self.atr, 6),
        }


def confirmed_gann_anchor(frame: pd.DataFrame) -> GannAnchor | None:
    """选择分析区间内最近一个已确认高低点作为自动江恩锚点。"""
    pivots = confirmed_zigzag_pivots(frame, swing_window=3, atr_threshold=1.0)
    if len(pivots) < 2:
        return None
    pivot = pivots[-1]
    previous = pivots[-2]
    confirmation = pivot.confirmation_position
    if confirmation >= len(frame):
        return None
    atr = float(frame["ATR14"].iloc[confirmation])
    if not pd.notna(atr) or atr <= 0:
        return None
    return GannAnchor("up" if pivot.kind == "low" else "down", pivot, previous, atr)

