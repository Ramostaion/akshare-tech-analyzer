"""独立于价格目标的摆幅时间周期与宽容观察窗。"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.gann.models import GannAnchor, GannConfig, GannPivot

CYCLE_MULTIPLES = (0.5, 1.0, 1.5, 2.0, 3.0)


def future_bar_datetime(latest: pd.Timestamp, bars: int, period: str) -> pd.Timestamp:
    """仅把未来 bar 序号转换成显示坐标，计算本身仍以 bar index 为准。"""
    if period == "daily":
        return latest + pd.offsets.BDay(bars)
    if period == "weekly":
        return latest + pd.offsets.Week(bars)
    if period == "monthly":
        return latest + pd.offsets.MonthEnd(bars)
    minutes = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "60m": 60}.get(period)
    return (
        latest + pd.Timedelta(minutes=minutes * bars)
        if minutes
        else latest + pd.Timedelta(days=bars)
    )


def infer_base_cycles(
    pivots: list[GannPivot], config: GannConfig = GannConfig()
) -> list[dict[str, Any]]:
    durations = [item.duration for item in pivots if item.duration >= 2]
    recent = durations[-config.cycle_lookback :]
    if not recent:
        return []
    candidates = [
        ("recent_swing", "最近摆幅", recent[-1]),
        ("previous_swing", "前一摆幅", recent[-2] if len(recent) > 1 else recent[-1]),
        ("median_recent", "近期摆幅中位数", int(round(float(np.median(recent))))),
    ]
    result: list[dict[str, Any]] = []
    seen: set[int] = set()
    for key, label, bars in candidates:
        bars = max(2, int(bars))
        if bars in seen:
            continue
        seen.add(bars)
        consistency = 1 - min(float(np.std(recent)) / max(float(np.mean(recent)), 1), 1)
        result.append(
            {
                "key": key,
                "source": label,
                "bars": bars,
                "sample_count": len(recent),
                "cycle_strength": round(50 + consistency * 30 + min(len(recent), 5) * 4, 1),
            }
        )
    return result


def build_time_windows(
    frame: pd.DataFrame,
    anchor: GannAnchor,
    pivots: list[GannPivot],
    horizon: int,
    period: str = "daily",
    config: GannConfig = GannConfig(),
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """以 bar index 投影时间窗；日期仅由现有 K 线间隔用于显示。"""
    cycles = infer_base_cycles(pivots, config)
    latest = len(frame) - 1
    windows: list[dict[str, Any]] = []
    latest_time = pd.Timestamp(frame["datetime"].iloc[-1])
    for cycle in cycles:
        base = int(cycle["bars"])
        for multiple in CYCLE_MULTIPLES:
            center = anchor.pivot.position + int(round(base * multiple))
            while center <= latest:
                center += base
            if center > latest + horizon:
                continue
            tolerance = max(1, round(base * config.window_tolerance))
            start = max(latest + 1, center - tolerance)
            end = min(latest + horizon, center + tolerance)
            alignment = sum(
                abs(center - (latest + int(other["bars"]))) <= tolerance for other in cycles
            )
            score = min(100.0, float(cycle["cycle_strength"]) * 0.55 + alignment * 12 + 20)
            windows.append(
                {
                    "source": cycle["source"],
                    "base_cycle": base,
                    "multiple": multiple,
                    "label": f"{multiple:g}T",
                    "center_position": center,
                    "start_position": start,
                    "end_position": end,
                    "bars_from_now": center - latest,
                    "start_datetime": future_bar_datetime(
                        latest_time, start - latest, period
                    ).isoformat(),
                    "center_datetime": future_bar_datetime(
                        latest_time, center - latest, period
                    ).isoformat(),
                    "end_datetime": future_bar_datetime(
                        latest_time, end - latest, period
                    ).isoformat(),
                    "score": round(score, 1),
                    "note": "观察窗按实际 K 线序号计算，不代表必然转折日期。",
                }
            )
    deduped: dict[tuple[int, int], dict[str, Any]] = {}
    for item in sorted(
        windows, key=lambda value: (-float(value["score"]), int(value["center_position"]))
    ):
        key = (int(item["start_position"]), int(item["end_position"]))
        deduped.setdefault(key, item)
    return cycles, sorted(deduped.values(), key=lambda item: int(item["center_position"]))[:6]


__all__ = ["CYCLE_MULTIPLES", "build_time_windows", "future_bar_datetime", "infer_base_cycles"]
