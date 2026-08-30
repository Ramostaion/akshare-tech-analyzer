"""Fibonacci、动量与成交量仅作为候选评分特征。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.wave.pivots import WavePivot


def fib_closeness(value: float, typical: tuple[float, ...], tolerance: float = 0.35) -> float:
    """按到最近典型 Fib 比率的距离给 0~1 分，不作为硬约束。"""
    if not np.isfinite(value) or tolerance <= 0:
        return 0.0
    distance = min(abs(value - target) / max(target, 0.001) for target in typical)
    return float(np.clip(1 - distance / tolerance, 0, 1))


def impulse_fib_score(pivots: list[WavePivot]) -> tuple[float, dict[str, float]]:
    """计算上涨五浪候选的 W2/W3/W4/W5 比率及接近度。"""
    prices = [item.price for item in pivots[-6:]]
    w1 = prices[1] - prices[0]
    w2 = prices[1] - prices[2]
    w3 = prices[3] - prices[2]
    w4 = prices[3] - prices[4]
    w5 = prices[5] - prices[4]
    ratios = {
        "wave2_retracement": w2 / w1 if w1 else np.nan,
        "wave3_extension": w3 / w1 if w1 else np.nan,
        "wave4_retracement": w4 / w3 if w3 else np.nan,
        "wave5_extension": w5 / w1 if w1 else np.nan,
    }
    scores = (
        fib_closeness(ratios["wave2_retracement"], (0.382, 0.5, 0.618, 0.786)),
        fib_closeness(ratios["wave3_extension"], (1.0, 1.618, 2.618)),
        fib_closeness(ratios["wave4_retracement"], (0.236, 0.382, 0.5)),
        fib_closeness(ratios["wave5_extension"], (0.618, 1.0, 1.618)),
    )
    return round(float(np.mean(scores)), 3), {
        key: round(float(value), 3) for key, value in ratios.items()
    }


def momentum_volume_score(frame: pd.DataFrame, pivots: list[WavePivot]) -> float:
    """比较 W1 与 W3 末端的 MACD/成交量扩张，缺失时保持中性。"""
    if len(pivots) < 4:
        return 0.5
    first_end = pivots[-5].position if len(pivots) >= 6 else pivots[1].position
    third_end = pivots[-3].position if len(pivots) >= 6 else pivots[3].position
    scores: list[float] = []
    if "MACD" in frame:
        first = frame["MACD"].iloc[first_end]
        third = frame["MACD"].iloc[third_end]
        if pd.notna(first) and pd.notna(third):
            scores.append(1.0 if third > first else 0.35)
    if "volume" in frame:
        first_volume = frame["volume"].iloc[max(0, first_end - 2) : first_end + 1].mean()
        third_volume = frame["volume"].iloc[max(0, third_end - 2) : third_end + 1].mean()
        if np.isfinite(first_volume) and first_volume > 0 and np.isfinite(third_volume):
            scores.append(float(np.clip(third_volume / first_volume / 1.2, 0, 1)))
    return round(float(np.mean(scores)) if scores else 0.5, 3)
