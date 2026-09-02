"""ATR 归一化江恩角线、价格分割与时间周期。"""

from __future__ import annotations

import pandas as pd

from app.gann.anchors import GannAnchor

FAN_RATIOS = (("2×1", 2.0), ("1×1", 1.0), ("1×2", 0.5))
PRICE_DIVISIONS = (0.125, 0.25, 1 / 3, 0.5, 2 / 3, 0.75, 0.875, 1.0)
TIME_CYCLES = (8, 16, 24, 32, 48)
DISPLAY_BARS = 24


def project_gann(frame: pd.DataFrame, anchor: GannAnchor) -> dict[str, object]:
    """从确认锚点生成条件路径；单位为 ATR14/8 每根 K 线。"""
    datetimes = pd.to_datetime(frame["datetime"])
    intervals = datetimes.diff().dropna()
    if intervals.empty or intervals.median() <= pd.Timedelta(0):
        return {"status": "insufficient"}
    interval = intervals.median()
    direction_sign = 1 if anchor.direction == "up" else -1
    unit_per_bar = anchor.atr / 8
    anchor_time = pd.Timestamp(anchor.pivot.timestamp)
    future_time = pd.Timestamp(datetimes.iloc[-1]) + interval * DISPLAY_BARS
    elapsed_bars = max(
        0,
        int(round((pd.Timestamp(datetimes.iloc[-1]) - anchor_time) / interval)),
    )
    current_market_price = float(frame["close"].iloc[-1])
    fan_lines = [
        {
            "label": label,
            "ratio": ratio,
            "start_time": anchor_time.isoformat(),
            "start_price": round(anchor.pivot.price, 6),
            "current_time": pd.Timestamp(datetimes.iloc[-1]).isoformat(),
            "current_price": round(current_market_price, 6),
            "anchor_line_current_price": round(
                anchor.pivot.price + direction_sign * unit_per_bar * ratio * elapsed_bars,
                6,
            ),
            "end_time": future_time.isoformat(),
            "end_price": round(
                current_market_price + direction_sign * unit_per_bar * ratio * DISPLAY_BARS,
                6,
            ),
        }
        for label, ratio in FAN_RATIOS
    ]
    swing = abs(anchor.pivot.price - anchor.previous_pivot.price)
    price_levels = [
        {
            "fraction": round(fraction, 4),
            "label": f"{fraction * 100:.1f}%",
            "price": round(anchor.pivot.price + direction_sign * swing * fraction, 6),
        }
        for fraction in PRICE_DIVISIONS
    ]
    cycles = [
        {
            "bars": bars,
            "datetime": (anchor_time + interval * bars).isoformat(),
        }
        for bars in TIME_CYCLES
        if anchor_time + interval * bars > pd.Timestamp(datetimes.iloc[-1])
    ]
    confirmation = anchor.previous_pivot.price
    current_close = float(frame["close"].iloc[-1])
    invalidated = (
        current_close < anchor.pivot.price
        if anchor.direction == "up"
        else current_close > anchor.pivot.price
    )
    confirmed = (
        current_close > confirmation if anchor.direction == "up" else current_close < confirmation
    )
    state = "invalidated" if invalidated else "confirmed" if confirmed else "waiting"
    state_labels = {
        "waiting": "等待收盘突破确认位",
        "confirmed": "方向已经收盘确认",
        "invalidated": "锚点结构已经失效",
    }
    return {
        "status": "active",
        "direction": anchor.direction,
        "anchor": anchor.as_dict(),
        "scale": {
            "atr": round(anchor.atr, 6),
            "unit_per_bar": round(unit_per_bar, 6),
            "method": "ATR14/8 每根 K 线",
        },
        "fan_lines": fan_lines,
        "price_levels": price_levels,
        "time_cycles": cycles,
        "confirmation": round(confirmation, 6),
        "invalidation": round(anchor.pivot.price, 6),
        "current_state": state,
        "current_state_label": state_labels[state],
        "note": (
            "江恩角线采用 ATR 归一化，不代表屏幕固定 45°；时间周期是观察窗口，"
            "不是精确到达日期。"
        ),
    }
