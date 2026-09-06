"""基于右侧确认 Pivot 的江恩锚点生命周期。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

import numpy as np
import pandas as pd

from app.wave.pivots import WavePivot, confirmed_zigzag_pivots

Direction = Literal["up", "down"]


@dataclass(frozen=True, slots=True)
class GannAnchor:
    """只使用右侧确认数据发布，并可由更新的同向重要 Pivot 晋升的江恩锚点。"""

    direction: Direction
    pivot: WavePivot
    previous_pivot: WavePivot
    atr: float
    lifecycle_start: int | None = None
    invalidated_at: int | None = None
    quality: float = 0.0
    reference_pivot: WavePivot | None = None
    reference_quality: float | None = None
    promotion_reason: str = "initial_confirmed_pivot"

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
            "lifecycle_start_position": self.lifecycle_start,
            "invalidated_at_position": self.invalidated_at,
            "quality": round(self.quality, 3),
            "promotion_reason": self.promotion_reason,
            "reference_anchor": (
                {
                    "kind": self.reference_pivot.kind,
                    "position": self.reference_pivot.position,
                    "confirmation_position": self.reference_pivot.confirmation_position,
                    "timestamp": self.reference_pivot.timestamp.isoformat(),
                    "price": round(self.reference_pivot.price, 6),
                    "quality": round(float(self.reference_quality or 0.0), 3),
                }
                if self.reference_pivot is not None
                else None
            ),
        }


def _anchor_quality(
    frame: pd.DataFrame,
    pivot: WavePivot,
    previous: WavePivot,
    atr: float,
) -> float:
    swing_atr = abs(pivot.price - previous.price) / atr
    duration = max(1, pivot.position - previous.position)
    duration_score = min(duration / 16, 1.0)
    swing_score = min(swing_atr / 4, 1.0)
    prominence = min(max(pivot.atr_move, swing_atr) / 4, 1.0)
    volume_score = 0.5
    if "volume" in frame and pivot.position < len(frame):
        recent = pd.to_numeric(
            frame["volume"].iloc[max(0, pivot.position - 20) : pivot.position + 1]
        )
        median = float(recent.median()) if not recent.empty else np.nan
        current = float(recent.iloc[-1]) if not recent.empty else np.nan
        if np.isfinite(median) and median > 0 and np.isfinite(current):
            volume_score = min(current / median, 2.0) / 2
    return float(0.4 * swing_score + 0.25 * duration_score + 0.2 * prominence + 0.15 * volume_score)


def _invalidated_position(
    frame: pd.DataFrame,
    direction: Direction,
    pivot: WavePivot,
    atr: float,
) -> int | None:
    """两根连续收盘穿越锚点缓冲区才结束生命周期。"""
    closes = pd.to_numeric(frame["close"], errors="coerce").to_numpy(dtype=float)
    threshold = pivot.price - 0.15 * atr if direction == "up" else pivot.price + 0.15 * atr
    consecutive = 0
    for position in range(pivot.confirmation_position + 1, len(frame)):
        crossed = (
            closes[position] < threshold
            if direction == "up"
            else closes[position] > threshold
        )
        consecutive = consecutive + 1 if crossed else 0
        if consecutive >= 2:
            return position
    return None


def confirmed_gann_anchors(frame: pd.DataFrame) -> list[GannAnchor]:
    """返回每个方向最新晋升的右确认锚点，并携带长期参考锚。"""
    pivots = confirmed_zigzag_pivots(frame, swing_window=3, atr_threshold=1.0)
    candidates: list[GannAnchor] = []
    for index in range(1, len(pivots)):
        pivot = pivots[index]
        previous = pivots[index - 1]
        confirmation = pivot.confirmation_position
        if confirmation >= len(frame):
            continue
        atr = float(frame["ATR14"].iloc[confirmation])
        if not np.isfinite(atr) or atr <= 0:
            continue
        direction: Direction = "up" if pivot.kind == "low" else "down"
        invalidated_at = _invalidated_position(frame, direction, pivot, atr)
        candidates.append(
            GannAnchor(
                direction,
                pivot,
                previous,
                atr,
                lifecycle_start=confirmation,
                invalidated_at=invalidated_at,
                quality=_anchor_quality(frame, pivot, previous, atr),
            )
        )
    active: list[GannAnchor] = []
    for direction in ("up", "down"):
        matching = sorted(
            (item for item in candidates if item.direction == direction),
            key=lambda item: item.pivot.confirmation_position,
        )
        if not matching:
            continue
        latest = matching[-1]
        prior = matching[:-1]
        valid_references = [
            item
            for item in prior
            if item.invalidated_at is None
            or item.invalidated_at > latest.pivot.confirmation_position
        ]
        reference = max(valid_references, key=lambda item: item.quality, default=None)
        current = replace(
            latest,
            reference_pivot=reference.pivot if reference is not None else None,
            reference_quality=reference.quality if reference is not None else None,
            promotion_reason=(
                "newer_confirmed_pivot"
                if len(matching) > 1
                else "initial_confirmed_pivot"
            ),
        )
        active.append(current)
    return active


def confirmed_gann_anchor(frame: pd.DataFrame) -> GannAnchor | None:
    """兼容入口：从各方向最新晋升锚点中选择当前主候选。"""
    candidates = confirmed_gann_anchors(frame)
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda item: (
            item.invalidated_at is None,
            item.quality,
            item.pivot.confirmation_position,
        ),
    )
