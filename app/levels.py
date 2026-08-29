"""基于已确认摆动点的支撑阻力聚类。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd

from app.config import Settings, settings


@dataclass(slots=True)
class Pivot:
    kind: Literal["high", "low"]
    position: int
    price: float
    volume_weight: float


def confirmed_swings(frame: pd.DataFrame, window: int = 4) -> list[Pivot]:
    """识别左右窗口均完成后的摆动高低点，最后 window 根不会被确认。"""
    if window < 1 or len(frame) < window * 2 + 1:
        return []
    median_volume = float(frame["volume"].replace(0, np.nan).median())
    if not np.isfinite(median_volume) or median_volume <= 0:
        median_volume = 1.0
    pivots: list[Pivot] = []
    highs = frame["high"].to_numpy(dtype=float)
    lows = frame["low"].to_numpy(dtype=float)
    volumes = frame["volume"].fillna(0).to_numpy(dtype=float)
    for position in range(window, len(frame) - window):
        high_segment = highs[position - window : position + window + 1]
        low_segment = lows[position - window : position + window + 1]
        volume_weight = float(np.clip(volumes[position] / median_volume, 0.25, 3.0))
        if (
            highs[position] == np.max(high_segment)
            and np.count_nonzero(high_segment == highs[position]) == 1
        ):
            pivots.append(Pivot("high", position, float(highs[position]), volume_weight))
        if (
            lows[position] == np.min(low_segment)
            and np.count_nonzero(low_segment == lows[position]) == 1
        ):
            pivots.append(Pivot("low", position, float(lows[position]), volume_weight))
    return pivots


def _cluster_pivots(
    pivots: list[Pivot],
    kind: Literal["high", "low"],
    price_band: float,
    row_count: int,
) -> list[dict[str, Any]]:
    candidates = sorted(
        (pivot for pivot in pivots if pivot.kind == kind), key=lambda item: item.price
    )
    clusters: list[list[Pivot]] = []
    for pivot in candidates:
        matching: list[Pivot] | None = None
        for cluster in clusters:
            center = float(np.average([item.price for item in cluster]))
            if abs(pivot.price - center) <= price_band:
                matching = cluster
                break
        if matching is None:
            clusters.append([pivot])
        else:
            matching.append(pivot)

    results: list[dict[str, Any]] = []
    decay_scale = max(row_count * 0.35, 1.0)
    for cluster in clusters:
        recency_weights = [
            math.exp(-(row_count - 1 - item.position) / decay_scale) for item in cluster
        ]
        combined_weights = [
            recency * (0.7 + 0.3 * item.volume_weight)
            for item, recency in zip(cluster, recency_weights, strict=True)
        ]
        price = float(
            np.average([item.price for item in cluster], weights=np.maximum(combined_weights, 0.01))
        )
        touch_score = 0.7 * len(cluster)
        volume_score = 0.25 * sum(min(item.volume_weight, 2.5) for item in cluster)
        recency_score = 0.55 * sum(recency_weights)
        score = touch_score + volume_score + recency_score
        if len(cluster) >= 4 and score >= 5:
            confidence = "高"
        elif len(cluster) >= 2 and score >= 2.7:
            confidence = "中"
        else:
            confidence = "低"
        results.append(
            {
                "price": round(price, 4),
                "lower": round(price - price_band / 2, 4),
                "upper": round(price + price_band / 2, 4),
                "touches": len(cluster),
                "score": round(score, 3),
                "confidence": confidence,
                "last_confirmed_position": max(item.position for item in cluster),
            }
        )
    return results


def identify_levels(frame: pd.DataFrame, app_settings: Settings = settings) -> dict[str, Any]:
    """返回距现价最近的最多三个有效支撑和阻力，以及可选参考情景。"""
    required = {"high", "low", "close", "volume", "ATR14"}
    if required.difference(frame.columns) or len(frame) < app_settings.level_swing_window * 2 + 5:
        return {
            "supports": [],
            "resistances": [],
            "message": "样本不足，未识别出可靠关键位",
            "scenario": None,
        }
    current_price = float(frame["close"].iloc[-1])
    atr_value = frame["ATR14"].iloc[-1]
    atr_component = float(atr_value) * app_settings.level_atr_factor if pd.notna(atr_value) else 0.0
    price_band = max(current_price * app_settings.level_price_pct, atr_component)
    if not np.isfinite(price_band) or price_band <= 0:
        price_band = current_price * app_settings.level_price_pct

    pivots = confirmed_swings(frame, app_settings.level_swing_window)
    lows = _cluster_pivots(pivots, "low", price_band, len(frame))
    highs = _cluster_pivots(pivots, "high", price_band, len(frame))
    supports = [
        item
        for item in lows
        if item["price"] < current_price and item["score"] >= app_settings.level_min_score
    ]
    resistances = [
        item
        for item in highs
        if item["price"] > current_price and item["score"] >= app_settings.level_min_score
    ]
    supports = sorted(supports, key=lambda item: current_price - item["price"])[:3]
    resistances = sorted(resistances, key=lambda item: item["price"] - current_price)[:3]

    scenario = None
    if supports and resistances:
        nearest_support = supports[0]
        nearest_resistance = resistances[0]
        invalidation = float(nearest_support["lower"])
        target = float(nearest_resistance["price"])
        risk = current_price - invalidation
        reward = target - current_price
        if risk > 0 and reward > 0:
            scenario = {
                "label": "参考情景",
                "observation_lower": nearest_support["upper"],
                "observation_upper": nearest_resistance["lower"],
                "invalidation": round(invalidation, 4),
                "target": round(target, 4),
                "reward_risk_ratio": round(reward / risk, 2),
                "note": "仅按最近支撑/阻力计算，不代表交易建议。",
            }
    message = None if supports or resistances else "未识别出可靠关键位"
    return {
        "supports": supports,
        "resistances": resistances,
        "message": message,
        "scenario": scenario,
        "cluster_band": round(price_band, 4),
    }
