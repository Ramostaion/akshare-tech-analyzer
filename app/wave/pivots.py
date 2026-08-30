"""仅在右侧窗口完成后发布的 Swing/ZigZag Pivot。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd


@dataclass(frozen=True, slots=True)
class WavePivot:
    kind: Literal["high", "low"]
    position: int
    confirmation_position: int
    timestamp: pd.Timestamp
    price: float
    atr_move: float

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "position": self.position,
            "confirmation_position": self.confirmation_position,
            "timestamp": self.timestamp.isoformat(),
            "price": round(self.price, 6),
            "atr_move": round(self.atr_move, 3),
        }


def confirmed_zigzag_pivots(
    frame: pd.DataFrame,
    swing_window: int = 3,
    atr_threshold: float = 1.0,
) -> list[WavePivot]:
    """压缩已确认 Swing，要求相邻反向 Pivot 至少相距指定 ATR。

    Pivot 的 ``confirmation_position`` 固定为原位置加右侧窗口；末尾未确认 Swing
    永远不会输出。同类连续 Pivot 仅保留更极端者，但其确认时间仍不早于自身右窗结束。
    """
    required = {"datetime", "high", "low", "ATR14"}
    if required.difference(frame.columns) or swing_window < 1:
        return []
    raw: list[WavePivot] = []
    highs = frame["high"].to_numpy(dtype=float)
    lows = frame["low"].to_numpy(dtype=float)
    atr = frame["ATR14"].to_numpy(dtype=float)
    for position in range(swing_window, len(frame) - swing_window):
        high_window = highs[position - swing_window : position + swing_window + 1]
        low_window = lows[position - swing_window : position + swing_window + 1]
        confirmation = position + swing_window
        current_atr = atr[confirmation] if confirmation < len(atr) else np.nan
        if not np.isfinite(current_atr) or current_atr <= 0:
            continue
        if highs[position] == np.max(high_window) and np.count_nonzero(
            high_window == highs[position]
        ) == 1:
            raw.append(
                WavePivot(
                    "high",
                    position,
                    confirmation,
                    pd.Timestamp(frame["datetime"].iloc[position]),
                    float(highs[position]),
                    0.0,
                )
            )
        if lows[position] == np.min(low_window) and np.count_nonzero(
            low_window == lows[position]
        ) == 1:
            raw.append(
                WavePivot(
                    "low",
                    position,
                    confirmation,
                    pd.Timestamp(frame["datetime"].iloc[position]),
                    float(lows[position]),
                    0.0,
                )
            )
    raw.sort(key=lambda item: (item.confirmation_position, item.position))
    result: list[WavePivot] = []
    for pivot in raw:
        if result and pivot.position <= result[-1].position:
            continue
        if result and pivot.kind == result[-1].kind:
            more_extreme = (
                pivot.price > result[-1].price
                if pivot.kind == "high"
                else pivot.price < result[-1].price
            )
            if more_extreme:
                result[-1] = pivot
            continue
        if result:
            reference_atr = float(frame["ATR14"].iloc[pivot.confirmation_position])
            move = abs(pivot.price - result[-1].price) / reference_atr
            if move < atr_threshold:
                continue
            pivot = WavePivot(
                pivot.kind,
                pivot.position,
                pivot.confirmation_position,
                pivot.timestamp,
                pivot.price,
                move,
            )
        result.append(pivot)
    return result
