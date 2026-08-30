"""确定性市场状态识别。"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

REGIMES = {
    "UPTREND",
    "DOWNTREND",
    "RANGE",
    "HIGH_VOLATILITY",
    "LOW_VOLATILITY",
    "INSUFFICIENT_DATA",
}


def _value(row: pd.Series, name: str) -> float | None:
    value = row.get(name)
    return float(value) if value is not None and np.isfinite(value) else None


def classify_regime(frame: pd.DataFrame, factors: pd.DataFrame) -> dict[str, Any]:
    """识别最新市场状态并返回置信度与可审计证据。

    高低波动优先于方向状态；方向由均线位置、斜率及 HH/HL 或 LH/LL 结构投票。
    只读取 ``frame`` 与 ``factors`` 最后一行及此前已计算值，少于 60 根返回数据不足。
    """
    if len(frame) < 60 or factors.empty:
        return {
            "regime": "INSUFFICIENT_DATA",
            "confidence": 0.0,
            "evidence": ["至少需要60根K线识别市场状态"],
        }
    latest = factors.iloc[-1]
    atr_percentile = _value(latest, "atr_percentile_250")
    width_percentile = _value(latest, "boll_width_percentile_250")
    if atr_percentile is not None and atr_percentile >= 0.85:
        evidence = [f"ATR分位={atr_percentile:.2f}，处于高波动区"]
        if width_percentile is not None:
            evidence.append(f"布林带宽分位={width_percentile:.2f}")
        return {
            "regime": "HIGH_VOLATILITY",
            "confidence": round(min(1.0, 0.55 + (atr_percentile - 0.85) * 3), 3),
            "evidence": evidence,
        }
    if (
        atr_percentile is not None
        and width_percentile is not None
        and atr_percentile <= 0.20
        and width_percentile <= 0.25
    ):
        confidence = 0.55 + (0.20 - atr_percentile) + (0.25 - width_percentile)
        return {
            "regime": "LOW_VOLATILITY",
            "confidence": round(min(1.0, confidence), 3),
            "evidence": [
                f"ATR分位={atr_percentile:.2f}",
                f"布林带宽分位={width_percentile:.2f}，波动收缩",
            ],
        }

    close = float(frame["close"].iloc[-1])
    votes_up: list[str] = []
    votes_down: list[str] = []
    ma20 = float(frame["MA20"].iloc[-1]) if pd.notna(frame["MA20"].iloc[-1]) else None
    ma60 = float(frame["MA60"].iloc[-1]) if pd.notna(frame["MA60"].iloc[-1]) else None
    ma120 = float(frame["MA120"].iloc[-1]) if pd.notna(frame["MA120"].iloc[-1]) else None
    if ma20 is not None and ma60 is not None:
        (votes_up if close > ma20 > ma60 else votes_down if close < ma20 < ma60 else []).append(
            "价格与MA20/MA60方向排列"
        )
    if ma120 is not None and ma60 is not None:
        (votes_up if ma60 > ma120 else votes_down if ma60 < ma120 else []).append(
            "MA60与MA120方向排列"
        )
    slope20 = _value(latest, "ma20_slope_5")
    slope60 = _value(latest, "ma60_slope_5")
    if slope20 is not None and slope60 is not None:
        if slope20 > 0 and slope60 > 0:
            votes_up.append("MA20与MA60斜率向上")
        elif slope20 < 0 and slope60 < 0:
            votes_down.append("MA20与MA60斜率向下")
    hh = _value(latest, "higher_high_count_20") or 0
    hl = _value(latest, "higher_low_count_20") or 0
    lh = _value(latest, "lower_high_count_20") or 0
    ll = _value(latest, "lower_low_count_20") or 0
    if hh + hl >= lh + ll + 4:
        votes_up.append("最近20根HH/HL计数占优")
    elif lh + ll >= hh + hl + 4:
        votes_down.append("最近20根LH/LL计数占优")

    if len(votes_up) >= 2 and len(votes_up) > len(votes_down):
        return {
            "regime": "UPTREND",
            "confidence": round(min(0.95, 0.5 + len(votes_up) * 0.12), 3),
            "evidence": votes_up,
        }
    if len(votes_down) >= 2 and len(votes_down) > len(votes_up):
        return {
            "regime": "DOWNTREND",
            "confidence": round(min(0.95, 0.5 + len(votes_down) * 0.12), 3),
            "evidence": votes_down,
        }
    return {
        "regime": "RANGE",
        "confidence": round(0.55 + 0.05 * min(len(votes_up), len(votes_down)), 3),
        "evidence": ["趋势投票未形成一致方向", *votes_up, *votes_down],
    }


def regime_series(frame: pd.DataFrame, factors: pd.DataFrame) -> pd.Series:
    """逐时点计算状态；每个值仅使用截至该行的数据。"""
    values = [
        classify_regime(frame.iloc[: position + 1], factors.iloc[: position + 1])["regime"]
        for position in range(len(frame))
    ]
    return pd.Series(values, index=frame.index, name="regime")
