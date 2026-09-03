"""无未来函数的威科夫交易区间与事件候选识别。"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

LOOKBACK = 60
RECENT_EVENT_BARS = 24


def detect_wyckoff_structure(frame: pd.DataFrame) -> dict[str, Any]:
    """仅使用每根 K 线当时及之前的数据识别当前交易区间和事件。"""
    if len(frame) < LOOKBACK + 20 or "ATR14" not in frame:
        return {"status": "insufficient", "note": "至少需要 80 根 K 线识别威科夫结构。"}
    if "volume" not in frame:
        return {
            "status": "volume_unavailable",
            "note": "当前序列缺少可靠成交量，第一版不生成完整威科夫量价结构。",
        }
    volume = pd.to_numeric(frame["volume"], errors="coerce")
    reliable_volume = bool((volume.notna() & (volume > 0)).mean() >= 0.8)
    if not reliable_volume:
        return {
            "status": "volume_unavailable",
            "note": "当前序列缺少可靠成交量，第一版不生成完整威科夫量价结构。",
        }

    work = frame.reset_index(drop=True).copy()
    prior_low = work["low"].shift(1).rolling(LOOKBACK, min_periods=LOOKBACK).quantile(0.12)
    prior_high = work["high"].shift(1).rolling(LOOKBACK, min_periods=LOOKBACK).quantile(0.88)
    volume_ratio = volume / volume.shift(1).rolling(20, min_periods=10).mean()
    spread_ratio = (work["high"] - work["low"]) / work["ATR14"].replace(0, np.nan)
    events: list[dict[str, Any]] = []
    start = max(LOOKBACK, len(work) - RECENT_EVENT_BARS)
    for position in range(start, len(work)):
        row = work.iloc[position]
        support = prior_low.iloc[position]
        resistance = prior_high.iloc[position]
        vr = volume_ratio.iloc[position]
        spread = spread_ratio.iloc[position]
        if pd.isna(support) or pd.isna(resistance) or pd.isna(vr):
            continue
        label = None
        direction = "neutral"
        if row["low"] < support and row["close"] > support and vr >= 0.8:
            label, direction = "Spring", "up"
        elif row["high"] > resistance and row["close"] < resistance and vr >= 0.8:
            label, direction = "UTAD", "down"
        elif row["close"] > resistance and vr >= 1.1 and spread >= 0.9:
            label, direction = "SOS", "up"
        elif row["close"] < support and vr >= 1.1 and spread >= 0.9:
            label, direction = "SOW", "down"
        elif abs(row["close"] - support) <= float(row["ATR14"]) * 0.45 and vr <= 0.9:
            label, direction = "LPS", "up"
        elif abs(row["close"] - resistance) <= float(row["ATR14"]) * 0.45 and vr <= 0.9:
            label, direction = "LPSY", "down"
        if label:
            events.append(
                {
                    "event": label,
                    "direction": direction,
                    "position": position,
                    "timestamp": pd.Timestamp(row["datetime"]).isoformat(),
                    "price": round(float(row["close"]), 6),
                    "volume_ratio": round(float(vr), 3),
                    "spread_atr": round(float(spread), 3),
                    "confirmed_at": pd.Timestamp(row["datetime"]).isoformat(),
                }
            )

    latest = work.iloc[-1]
    support = float(prior_low.iloc[-1])
    resistance = float(prior_high.iloc[-1])
    if not np.isfinite(support) or not np.isfinite(resistance) or resistance <= support:
        return {"status": "insufficient", "note": "当前无法形成稳定的威科夫交易区间。"}
    recent_event = events[-1] if events else None
    close = float(latest["close"])
    if "OBV" in work:
        obv = pd.to_numeric(work["OBV"], errors="coerce")
        has_obv_window = len(obv.dropna()) >= 10
    else:
        obv = pd.Series(dtype=float)
        has_obv_window = False
    if has_obv_window:
        obv_bias = "up" if obv.iloc[-1] >= obv.iloc[-10] else "down"
    else:
        comparison = pd.to_numeric(work["close"], errors="coerce").rolling(20).mean().iloc[-1]
        obv_bias = "up" if close >= comparison else "down"
    direction = recent_event["direction"] if recent_event else obv_bias
    event_name = recent_event["event"] if recent_event else "Trading Range"
    if close > resistance or close < support:
        phase = "E"
    elif event_name in {"Spring", "UTAD"}:
        phase = "C"
    elif event_name in {"SOS", "SOW", "LPS", "LPSY"}:
        phase = "D"
    else:
        phase = "B"
    structure = "accumulation" if direction == "up" else "distribution"
    score = 45 + min(25, len(events) * 4)
    if recent_event:
        score += min(20, max(0, (recent_event["volume_ratio"] - 0.8) * 20))
    return {
        "status": "active",
        "structure": structure,
        "direction": direction,
        "phase": phase,
        "current_event": event_name,
        "range": {"support": round(support, 6), "resistance": round(resistance, 6)},
        "events": events[-8:],
        "structural_fit": round(min(0.92, score / 100), 3),
        "volume_reliable": True,
    }
