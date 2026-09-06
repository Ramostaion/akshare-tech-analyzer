"""基于已确认摆动的江恩时间周期与评分观察窗。"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.gann.models import GannAnchor, GannConfig, GannPivot

CYCLE_MULTIPLES = (0.5, 1.0, 1.5, 2.0, 3.0)


def future_bar_datetime(latest: pd.Timestamp, bars: int, period: str) -> pd.Timestamp:
    """把未来 bar 序号转换为显示坐标；算法仍以 bar index 为准。"""
    if period == "daily":
        return latest + pd.offsets.BDay(bars)
    if period == "weekly":
        return latest + pd.offsets.Week(bars)
    if period == "monthly":
        return latest + pd.offsets.MonthEnd(bars)
    minutes = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "60m": 60}.get(period)
    return latest + (pd.Timedelta(minutes=minutes * bars) if minutes else pd.Timedelta(days=bars))


def infer_base_cycles(
    pivots: list[GannPivot], config: GannConfig = GannConfig()
) -> list[dict[str, Any]]:
    durations = [item.duration for item in pivots if item.duration >= 2]
    recent = durations[-config.cycle_lookback :]
    if not recent:
        return []
    consistency = 1 - min(float(np.std(recent)) / max(float(np.mean(recent)), 1), 1)
    candidates = [
        ("recent_swing", "最近摆动", recent[-1]),
        ("previous_swing", "前一摆动", recent[-2] if len(recent) > 1 else recent[-1]),
        ("median_recent", "近期摆动时长中位数", int(round(float(np.median(recent))))),
    ]
    result: list[dict[str, Any]] = []
    seen: set[int] = set()
    for key, source, bars in candidates:
        bars = max(2, int(bars))
        if bars in seen:
            continue
        seen.add(bars)
        result.append(
            {
                "key": key,
                "source": source,
                "bars": bars,
                "sample_count": len(recent),
                "cycle_strength": round(45 + consistency * 35 + min(len(recent), 5) * 4, 1),
            }
        )
    return result


def _window_score(
    cycle_strength: float,
    overlap: int,
    multiple: float,
    higher_timeframe_alignment: bool,
    nearby_price_confluence: float,
    trend_alignment: bool,
) -> tuple[float, dict[str, float]]:
    """返回可解释的 TimeWindowScore；历史命中率留给校准层，不伪装成概率。"""
    factors = {
        "cycle_strength": min(30.0, cycle_strength * 0.30),
        "multiple_cycle_overlap": min(20.0, max(0, overlap - 1) * 10.0),
        "historical_hit_rate": 8.0,
        "higher_timeframe_alignment": 12.0 if higher_timeframe_alignment else 6.0,
        "nearby_price_confluence": min(15.0, nearby_price_confluence * 15.0),
        "trend_context": 15.0 if trend_alignment else 7.5,
    }
    distance_penalty = 8.0 if multiple >= 3 else 3.0 if multiple >= 2 else 0.0
    return round(max(0.0, min(100.0, sum(factors.values()) - distance_penalty)), 1), factors


def _merge_overlapping_windows(windows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not windows:
        return []
    ordered = sorted(windows, key=lambda item: (int(item["start_position"]), -float(item["score"])))
    merged: list[dict[str, Any]] = []
    for item in ordered:
        if not merged or int(item["start_position"]) > int(merged[-1]["end_position"]):
            merged.append(dict(item))
            merged[-1]["cycle_ratios"] = [item["cycle_ratio"]]
            merged[-1]["source_cycles"] = [item["source_cycle"]]
            continue
        current = merged[-1]
        current["start_position"] = min(int(current["start_position"]), int(item["start_position"]))
        current["end_position"] = max(int(current["end_position"]), int(item["end_position"]))
        current["score"] = round(
            min(100.0, max(float(current["score"]), float(item["score"])) + 7), 1
        )
        current["cycle_ratios"].append(item["cycle_ratio"])
        current["source_cycles"].append(item["source_cycle"])
        current["label"] = "多周期时间窗"
        current["multiple_cycle"] = True
    return merged


def build_time_windows(
    frame: pd.DataFrame,
    anchor: GannAnchor,
    pivots: list[GannPivot],
    horizon: int,
    period: str = "daily",
    config: GannConfig = GannConfig(),
    *,
    higher_timeframe_alignment: bool = False,
    nearby_price_confluence: float = 0.5,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """生成全部统计窗口，并标记前端可见级别。"""
    cycles = infer_base_cycles(pivots, config)
    latest = len(frame) - 1
    latest_time = pd.Timestamp(frame["datetime"].iloc[-1])
    candidates: list[dict[str, Any]] = []
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
            overlap = sum(
                abs(center - (anchor.pivot.position + int(round(int(other["bars"]) * multiple))))
                <= tolerance
                for other in cycles
            )
            score, factors = _window_score(
                float(cycle["cycle_strength"]),
                overlap,
                multiple,
                higher_timeframe_alignment,
                nearby_price_confluence,
                True,
            )
            candidates.append(
                {
                    "source": cycle["source"],
                    "source_cycle": cycle["source"],
                    "base_cycle": base,
                    "multiple": multiple,
                    "cycle_ratio": f"{multiple:g}T",
                    "label": f"{multiple:g}T",
                    "center_position": center,
                    "center_bar": center,
                    "start_position": start,
                    "start_bar": start,
                    "end_position": end,
                    "end_bar": end,
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
                    "score": score,
                    "score_factors": factors,
                    "note": "按实际 K 线序号计算的观察窗，不代表必然转折日期。",
                }
            )
    windows = _merge_overlapping_windows(candidates)
    for item in windows:
        score = float(item["score"])
        item["visibility"] = "normal" if score >= 70 else "faded" if score >= 55 else "hidden"
        item["default_visible"] = score >= config.visible_time_window_score
        item["start_bar"] = item["start_position"]
        item["end_bar"] = item["end_position"]
        item["start_datetime"] = future_bar_datetime(
            latest_time, int(item["start_position"]) - latest, period
        ).isoformat()
        item["end_datetime"] = future_bar_datetime(
            latest_time, int(item["end_position"]) - latest, period
        ).isoformat()
    return cycles, sorted(windows, key=lambda item: int(item["center_position"]))


__all__ = ["CYCLE_MULTIPLES", "build_time_windows", "future_bar_datetime", "infer_base_cycles"]
