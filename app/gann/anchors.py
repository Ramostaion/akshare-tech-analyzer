"""江恩锚点评分、竞争方向与因果晋升。"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from app.gann.models import Direction, GannAnchor, GannConfig, GannPivot
from app.gann.pivots import confirmed_pivots


def _bounded(value: float) -> float:
    return round(float(np.clip(value, 0.0, 1.0)), 4)


def anchor_score(
    frame: pd.DataFrame, pivot: GannPivot, previous: GannPivot
) -> tuple[float, dict[str, float]]:
    """按七项固定权重计算可解释 Anchor Score（满分 100）。"""
    atr = max(pivot.atr_at_confirmation, 1e-12)
    left = max(0, pivot.position - 20)
    segment = frame.iloc[left : pivot.confirmation_position + 1]
    swing_atr = pivot.swing_size / atr
    pivot_strength = _bounded(max(swing_atr / 5, pivot.duration / 24))
    swing_magnitude = _bounded(swing_atr / 6)
    atr_significance = _bounded(swing_atr / 4)
    prices = pd.concat([segment["high"], segment["low"]]).astype(float)
    touches = int((prices.sub(pivot.price).abs() <= atr * 0.35).sum())
    support_resistance = _bounded(touches / 4)
    volume_confirmation = 0.5
    if "volume" in segment:
        volumes = pd.to_numeric(segment["volume"], errors="coerce").replace(0, np.nan)
        median = float(volumes.median())
        pivot_volume = float(volumes.iloc[min(pivot.position - left, len(volumes) - 1)])
        if np.isfinite(median) and median > 0 and np.isfinite(pivot_volume):
            volume_confirmation = _bounded(pivot_volume / median / 2)
    closes = pd.to_numeric(frame["close"], errors="coerce")
    before = float(closes.iloc[max(0, pivot.position - 2)])
    after = float(closes.iloc[pivot.confirmation_position])
    reversal = (after - before) * (1 if pivot.kind == "low" else -1) / atr
    momentum_reversal = _bounded(reversal / 2)
    time_persistence = _bounded(pivot.duration / 20)
    components = {
        "pivot_strength": round(pivot_strength * 25, 2),
        "swing_magnitude": round(swing_magnitude * 20, 2),
        "atr_significance": round(atr_significance * 15, 2),
        "support_resistance": round(support_resistance * 15, 2),
        "volume_confirmation": round(volume_confirmation * 10, 2),
        "momentum_reversal": round(momentum_reversal * 10, 2),
        "time_persistence": round(time_persistence * 5, 2),
    }
    return round(sum(components.values()), 1), components


def _lifecycle_id(direction: Direction, pivot: GannPivot) -> str:
    raw = f"{direction}|{pivot.timestamp.isoformat()}|{pivot.price:.8f}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def build_anchor_candidates(
    frame: pd.DataFrame, config: GannConfig = GannConfig()
) -> list[GannAnchor]:
    """为已确认反转构造锚点，评分只读取 confirmation_position 以前的数据。"""
    pivots = confirmed_pivots(frame, config)
    anchors: list[GannAnchor] = []
    for index in range(1, len(pivots)):
        pivot = pivots[index]
        previous = next(
            (item for item in reversed(pivots[:index]) if item.kind != pivot.kind),
            None,
        )
        if previous is None:
            continue
        history = frame.iloc[: pivot.confirmation_position + 1]
        score, components = anchor_score(history, pivot, previous)
        direction: Direction = "up" if pivot.kind == "low" else "down"
        anchors.append(
            GannAnchor(
                direction,
                pivot,
                previous,
                score,
                components,
                _lifecycle_id(direction, pivot),
            )
        )
    return anchors


def confirmed_gann_anchors(
    frame: pd.DataFrame, config: GannConfig = GannConfig()
) -> list[GannAnchor]:
    """返回上、下行最新 ATR 显著确认锚，旧高分锚仅作长期参考。"""
    candidates = build_anchor_candidates(frame, config)
    active: list[GannAnchor] = []
    for direction in ("up", "down"):
        matching = [item for item in candidates if item.direction == direction]
        if not matching:
            continue
        current = matching[-1]
        reference = max(matching[:-1], key=lambda item: item.score, default=None)
        active.append(
            GannAnchor(
                current.direction,
                current.pivot,
                current.previous_pivot,
                current.score,
                current.score_components,
                current.lifecycle_id,
                reference.pivot if reference else None,
                "active",
            )
        )
    return active


def anchor_lifecycles(
    frame: pd.DataFrame, config: GannConfig = GannConfig()
) -> list[dict[str, object]]:
    """按确认顺序生成不可回写的锚点生命周期。"""
    candidates = build_anchor_candidates(frame, config)
    result: list[dict[str, object]] = []
    for index, anchor in enumerate(candidates):
        successor = next(
            (item for item in candidates[index + 1 :] if item.direction == anchor.direction),
            None,
        )
        row = anchor.as_dict()
        lifecycle_end = (
            successor.pivot.confirmation_position if successor is not None else len(frame)
        )
        closes = pd.to_numeric(
            frame["close"].iloc[anchor.pivot.confirmation_position + 1 : lifecycle_end],
            errors="coerce",
        )
        invalidated = (
            closes[closes < anchor.pivot.price - anchor.atr * 0.15]
            if anchor.direction == "up"
            else closes[closes > anchor.pivot.price + anchor.atr * 0.15]
        )
        invalidated_at = (
            pd.Timestamp(frame.loc[invalidated.index[0], "datetime"])
            if not invalidated.empty
            else None
        )
        row["lifecycle_events"] = [
            {"status": "candidate", "at": anchor.pivot.timestamp.isoformat()},
            {"status": "confirmed", "at": anchor.pivot.confirmed_at.isoformat()},
            {"status": "active", "at": anchor.pivot.confirmed_at.isoformat()},
        ]
        if invalidated_at is not None:
            row["status"] = "invalidated"
            row["invalidated_at"] = invalidated_at.isoformat()
            row["lifecycle_events"].append(
                {"status": "invalidated", "at": invalidated_at.isoformat()}
            )
        elif successor is not None:
            row["status"] = "replaced"
            row["invalidated_at"] = successor.pivot.confirmed_at.isoformat()
            row["replacement_anchor_id"] = successor.lifecycle_id
            row["lifecycle_events"].append(
                {"status": "replaced", "at": successor.pivot.confirmed_at.isoformat()}
            )
        else:
            row["status"] = "active"
        result.append(row)
    return result


def confirmed_gann_anchor(
    frame: pd.DataFrame, config: GannConfig = GannConfig()
) -> GannAnchor | None:
    candidates = confirmed_gann_anchors(frame, config)
    return max(
        candidates, key=lambda item: (item.score, item.pivot.confirmation_position), default=None
    )


__all__ = [
    "GannAnchor",
    "anchor_score",
    "anchor_lifecycles",
    "build_anchor_candidates",
    "confirmed_gann_anchor",
    "confirmed_gann_anchors",
]
