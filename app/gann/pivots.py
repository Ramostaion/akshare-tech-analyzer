"""仅在右侧窗口完成后发布的 ATR + 百分比混合 Pivot。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.gann.models import GannConfig, GannPivot


def confirmed_pivots(frame: pd.DataFrame, config: GannConfig = GannConfig()) -> list[GannPivot]:
    """返回截至最后一根 K 线已确认的交替 Pivot，不发布末端未确认极值。"""
    required = {"datetime", "high", "low", "close", "ATR14"}
    window = config.pivot_window
    if required.difference(frame.columns) or len(frame) < window * 2 + 2:
        return []
    highs = pd.to_numeric(frame["high"], errors="coerce").to_numpy(float)
    lows = pd.to_numeric(frame["low"], errors="coerce").to_numpy(float)
    atr = pd.to_numeric(frame["ATR14"], errors="coerce").to_numpy(float)
    times = pd.to_datetime(frame["datetime"])
    raw: list[tuple[str, int, int, float, float]] = []
    for position in range(window, len(frame) - window):
        confirmation = position + window
        current_atr = atr[confirmation]
        if not np.isfinite(current_atr) or current_atr <= 0:
            continue
        high_window = highs[position - window : confirmation + 1]
        low_window = lows[position - window : confirmation + 1]
        if (
            highs[position] == np.nanmax(high_window)
            and np.count_nonzero(np.isclose(high_window, highs[position])) == 1
        ):
            raw.append(("high", position, confirmation, highs[position], current_atr))
        if (
            lows[position] == np.nanmin(low_window)
            and np.count_nonzero(np.isclose(low_window, lows[position])) == 1
        ):
            raw.append(("low", position, confirmation, lows[position], current_atr))
    raw.sort(key=lambda item: (item[2], item[1], item[0]))
    accepted: list[GannPivot] = []
    for kind, position, confirmation, price, current_atr in raw:
        if accepted and position <= accepted[-1].position:
            continue
        threshold = max(
            current_atr * config.pivot_atr_factor, price * config.pivot_percent_threshold
        )
        if accepted and kind == accepted[-1].kind:
            is_more_extreme = (
                price > accepted[-1].price if kind == "high" else price < accepted[-1].price
            )
            if not is_more_extreme or abs(price - accepted[-1].price) < threshold:
                continue
            previous = next(
                (item for item in reversed(accepted) if item.kind != kind), accepted[-1]
            )
        else:
            previous = accepted[-1] if accepted else None
        swing = abs(price - previous.price) if previous else 0.0
        if previous and swing < threshold:
            continue
        accepted.append(
            GannPivot(
                kind=kind,  # type: ignore[arg-type]
                position=position,
                confirmation_position=confirmation,
                timestamp=pd.Timestamp(times.iloc[position]),
                confirmed_at=pd.Timestamp(times.iloc[confirmation]),
                price=float(price),
                swing_size=float(swing),
                duration=max(0, position - previous.position) if previous else 0,
                atr_at_confirmation=float(current_atr),
            )
        )
    return accepted


__all__ = ["confirmed_pivots"]
