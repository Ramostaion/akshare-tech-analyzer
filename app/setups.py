"""可交易结构（Setup）与明确触发条件。"""

from __future__ import annotations

import numpy as np
import pandas as pd

SETUP_NAMES = ("trend_pullback", "breakout", "support_reversal", "trend_breakdown")


def evaluate_setups(
    frame: pd.DataFrame,
    factors: pd.DataFrame,
    regimes: pd.Series,
) -> pd.DataFrame:
    """逐行返回四类 Setup 和 Trigger。

    Setup 表示结构存在，``*_trigger`` 才是收盘后确认的事件。突破与跌破阈值均由
    ``rolling(...).shift(1)`` 得到，成交量基准已在 Factor 层排除当前根。
    """
    if not frame.index.equals(factors.index) or not frame.index.equals(regimes.index):
        raise ValueError("frame、factors 与 regimes 必须使用相同索引")
    result = pd.DataFrame(False, index=frame.index, columns=[])
    close = frame["close"].astype(float)
    prior_high_20 = frame["high"].astype(float).rolling(20, min_periods=20).max().shift(1)
    prior_low_20 = frame["low"].astype(float).rolling(20, min_periods=20).min().shift(1)
    atr = frame["ATR14"].replace(0, np.nan)

    trend_fit = (
        regimes.eq("UPTREND")
        & close.gt(frame["MA60"])
        & frame["MA20"].gt(frame["MA60"])
        & factors["ma20_slope_5"].gt(0)
    )
    near_ma20 = factors["close_vs_ma20_atr"].between(-0.35, 0.85)
    near_support = factors["distance_to_support_atr"].between(0, 0.8)
    controlled_volume = factors["volume_ratio_20"].le(1.05)
    structure_intact = factors["higher_low_count_20"].ge(
        factors["lower_low_count_20"] - 2
    )
    result["trend_pullback"] = (
        trend_fit & (near_ma20 | near_support) & controlled_volume & structure_intact
    )
    result["trend_pullback_trigger"] = result["trend_pullback"] & close.gt(
        frame["high"].shift(1)
    )

    distance_to_breakout = (prior_high_20 - close) / atr
    contraction = factors["boll_width_percentile_250"].le(0.45)
    result["breakout"] = distance_to_breakout.between(-0.25, 1.0) & contraction
    prior_breakout_setup = result["breakout"].shift(1, fill_value=False)
    result["breakout_trigger"] = (
        prior_breakout_setup
        & close.gt(prior_high_20)
        & factors["breakout_volume_ratio"].ge(1.2)
        & factors["macd_hist_delta_3"].gt(0)
    )

    support_fit = regimes.isin(["RANGE", "UPTREND", "LOW_VOLATILITY"])
    result["support_reversal"] = (
        support_fit
        & factors["distance_to_support_atr"].between(0, 0.75)
        & factors["nearest_support_strength"].ge(1)
    )
    bullish_reversal = close.gt(frame["high"].shift(1)) & close.gt(frame["open"])
    result["support_reversal_trigger"] = result["support_reversal"] & bullish_reversal & (
        factors["rsi12_delta_3"].gt(0) | factors["volume_ratio_20"].ge(1.0)
    )

    failed_reclaim = (
        close.shift(1).lt(frame["MA20"].shift(1))
        & frame["high"].ge(frame["MA20"])
        & close.lt(frame["MA20"])
    )
    result["trend_breakdown"] = (
        regimes.isin(["UPTREND", "DOWNTREND", "HIGH_VOLATILITY"])
        & close.lt(frame["MA20"])
        & (frame["MA20"].le(frame["MA60"]) | factors["ma20_slope_5"].lt(0))
    )
    result["trend_breakdown_trigger"] = result["trend_breakdown"] & (
        close.lt(prior_low_20) | failed_reclaim
    )
    return result.fillna(False).astype(bool)


def current_setups(setups: pd.DataFrame) -> list[dict[str, object]]:
    """返回最新一行存在的 Setup 及其是否已触发。"""
    if setups.empty:
        return []
    latest = setups.iloc[-1]
    return [
        {"setup": name, "triggered": bool(latest[f"{name}_trigger"])}
        for name in SETUP_NAMES
        if bool(latest[name]) or bool(latest[f"{name}_trigger"])
    ]
