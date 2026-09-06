"""按各自 K 线独立识别日线与周线江恩结构。"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.gann.anchors import confirmed_gann_anchor
from app.gann.fan import angle_price
from app.gann.models import GannConfig
from app.gann.pivots import confirmed_pivots
from app.gann.scale import build_scale
from app.gann.time_cycles import infer_base_cycles
from app.indicators import add_indicators


def resample_weekly(frame: pd.DataFrame) -> pd.DataFrame:
    """用已完成日线重采样周线，不从日线 Pivot 做比例换算。"""
    indexed = frame.copy()
    indexed["datetime"] = pd.to_datetime(indexed["datetime"])
    indexed = indexed.set_index("datetime")
    aggregations = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    if "amount" in indexed:
        aggregations["amount"] = "sum"
    latest_time = pd.Timestamp(indexed.index.max()).normalize()
    weekly = (
        indexed.resample("W-FRI", label="right", closed="right")
        .agg(aggregations)
        .dropna(subset=["open", "high", "low", "close"])
    )
    if not weekly.empty and pd.Timestamp(weekly.index[-1]).normalize() > latest_time:
        weekly = weekly.iloc[:-1]
    weekly = weekly.reset_index()
    return add_indicators(weekly) if len(weekly) >= 20 else weekly


def higher_timeframe_context(
    frame: pd.DataFrame, period: str, config: GannConfig = GannConfig()
) -> dict[str, Any] | None:
    if period != "daily" or len(frame) < 100:
        return None
    weekly = resample_weekly(frame)
    if "ATR14" not in weekly or len(weekly) < 25:
        return None
    anchor = confirmed_gann_anchor(weekly, config)
    if anchor is None:
        return None
    scale = build_scale(anchor, config)
    latest = len(weekly) - 1
    fan = {
        label: round(angle_price(anchor, scale, ratio, latest), 6)
        for label, ratio in (("2×1", 2.0), ("1×1", 1.0), ("1×2", 0.5))
    }
    cycles = infer_base_cycles(confirmed_pivots(weekly, config), config)
    return {
        "timeframe": "weekly",
        "direction": anchor.direction,
        "anchor": anchor.as_dict(),
        "scale": scale.as_dict(),
        "fan_at_latest": fan,
        "time_cycles": cycles,
        "independent": True,
        "note": "周线由日线 OHLC 独立聚合后重新识别 Pivot 与锚点。",
    }


__all__ = ["higher_timeframe_context", "resample_weekly"]
