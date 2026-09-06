"""江恩锚点、角线和时间窗的无未来回放与 baseline 对照。"""

from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np
import pandas as pd

from app.gann.anchors import build_anchor_candidates
from app.gann.fan import angle_price
from app.gann.models import GannConfig
from app.gann.pivots import confirmed_pivots
from app.gann.scale import build_scale
from app.gann.time_cycles import infer_base_cycles

RETURN_HORIZONS = (1, 3, 5, 10, 20)


def _event_outcome(
    frame: pd.DataFrame, position: int, direction: str, atr: float
) -> dict[str, Any]:
    sign = 1 if direction == "up" else -1
    entry = float(frame["close"].iloc[position])
    result: dict[str, Any] = {}
    for horizon in RETURN_HORIZONS:
        end = position + horizon
        if end < len(frame):
            change = (float(frame["close"].iloc[end]) / entry - 1) * sign
            result[f"return_{horizon}"] = round(change, 6)
            result[f"correct_{horizon}"] = change > 0
    future = frame.iloc[position + 1 : min(len(frame), position + 21)]
    if future.empty:
        result.update({"mfe_atr": None, "mae_atr": None})
    else:
        favorable = (
            pd.to_numeric(future["high"]).max() - entry
            if sign > 0
            else entry - pd.to_numeric(future["low"]).min()
        )
        adverse = (
            entry - pd.to_numeric(future["low"]).min()
            if sign > 0
            else pd.to_numeric(future["high"]).max() - entry
        )
        result.update(
            {
                "mfe_atr": round(max(0.0, float(favorable)) / atr, 3),
                "mae_atr": round(max(0.0, float(adverse)) / atr, 3),
            }
        )
    return result


def _angle_events(frame: pd.DataFrame, config: GannConfig) -> list[dict[str, Any]]:
    anchors = build_anchor_candidates(frame, config)
    events: list[dict[str, Any]] = []
    for index, anchor in enumerate(anchors):
        next_confirmation = min(
            (
                item.pivot.confirmation_position
                for item in anchors[index + 1 :]
                if item.direction == anchor.direction
            ),
            default=len(frame),
        )
        scale = build_scale(anchor, config)
        sign = 1 if anchor.direction == "up" else -1
        start = anchor.pivot.confirmation_position + 1
        end = min(next_confirmation, len(frame) - max(RETURN_HORIZONS))
        for position in range(start, end):
            previous_close = float(frame["close"].iloc[position - 1])
            close = float(frame["close"].iloc[position])
            prior_line = angle_price(anchor, scale, 1.0, position - 1)
            line = angle_price(anchor, scale, 1.0, position)
            prior_side = (previous_close - prior_line) * sign
            side = (close - line) * sign
            prior_slow = angle_price(anchor, scale, 0.5, position - 1)
            slow = angle_price(anchor, scale, 0.5, position)
            prior_slow_side = (previous_close - prior_slow) * sign
            slow_side = (close - slow) * sign
            high = float(frame["high"].iloc[position])
            low = float(frame["low"].iloc[position])
            touched_one = low <= line + anchor.atr * 0.15 and high >= line - anchor.atr * 0.15
            if prior_side < 0 <= side:
                event = "reclaim_1x1"
            elif prior_side >= 0 > side:
                event = "break_1x1"
            elif prior_slow_side >= 0 > slow_side:
                event = "break_1x2"
            elif touched_one and side < 0 and prior_side < 0:
                event = "reject_1x1"
            else:
                event = None
            if event:
                event_direction = (
                    anchor.direction
                    if event == "reclaim_1x1"
                    else ("down" if anchor.direction == "up" else "up")
                )
                events.append(
                    {
                        "event": event,
                        "position": position,
                        "signal_time": pd.Timestamp(frame["datetime"].iloc[position]).isoformat(),
                        "anchor_confirmed_at": anchor.pivot.confirmed_at.isoformat(),
                        "anchor_score": anchor.score,
                        "direction": event_direction,
                        **_event_outcome(frame, position, event_direction, anchor.atr),
                    }
                )
    return events


def _summarize_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(item["event"] for item in events)
    summary: dict[str, Any] = {
        "sample_count": len(events),
        "by_event": {
            name: counts[name] for name in ("break_1x1", "reject_1x1", "break_1x2", "reclaim_1x1")
        },
    }
    for horizon in RETURN_HORIZONS:
        values = [
            float(item[f"return_{horizon}"]) for item in events if f"return_{horizon}" in item
        ]
        summary[f"horizon_{horizon}"] = {
            "sample_count": len(values),
            "direction_accuracy": round(sum(value > 0 for value in values) / len(values) * 100, 1)
            if values
            else None,
            "median_return": round(float(np.median(values)) * 100, 3) if values else None,
        }
    mfe = [float(item["mfe_atr"]) for item in events if item.get("mfe_atr") is not None]
    mae = [float(item["mae_atr"]) for item in events if item.get("mae_atr") is not None]
    summary["median_mfe_atr"] = round(float(np.median(mfe)), 3) if mfe else None
    summary["median_mae_atr"] = round(float(np.median(mae)), 3) if mae else None
    return summary


def _is_reversal(frame: pd.DataFrame, position: int, radius: int = 2) -> bool:
    if position < radius or position + radius >= len(frame):
        return False
    window = frame.iloc[position - radius : position + radius + 1]
    high = float(frame["high"].iloc[position])
    low = float(frame["low"].iloc[position])
    return high >= float(window["high"].max()) or low <= float(window["low"].min())


def _has_volatility_expansion(frame: pd.DataFrame, position: int) -> bool:
    if position < 10 or position + 3 >= len(frame):
        return False
    prior = (frame["high"] - frame["low"]).iloc[position - 10 : position]
    future = (frame["high"] - frame["low"]).iloc[position : position + 4]
    return float(future.mean()) > float(prior.median()) * 1.25


def _has_breakout(frame: pd.DataFrame, position: int) -> bool:
    if position < 10 or position + 3 >= len(frame):
        return False
    prior_high = float(frame["high"].iloc[position - 10 : position].max())
    prior_low = float(frame["low"].iloc[position - 10 : position].min())
    future = frame["close"].iloc[position : position + 4]
    return bool((future > prior_high).any() or (future < prior_low).any())


def _time_window_study(frame: pd.DataFrame, config: GannConfig) -> dict[str, Any]:
    pivots = confirmed_pivots(frame, config)
    positions: list[int] = []
    for index, pivot in enumerate(pivots[:-1]):
        visible = pivots[: index + 1]
        cycles = infer_base_cycles(visible, config)
        if not cycles:
            continue
        center = pivot.position + int(cycles[-1]["bars"])
        if pivot.confirmation_position <= center < len(frame) - 2:
            positions.append(center)
    positions = sorted(set(positions))
    hits = sum(_is_reversal(frame, position) for position in positions)
    valid_random = [position for position in range(2, len(frame) - 2) if position not in positions]
    if positions and valid_random:
        indices = np.linspace(
            0, len(valid_random) - 1, min(len(positions), len(valid_random)), dtype=int
        )
        baseline_positions = [valid_random[int(index)] for index in indices]
    else:
        baseline_positions = []
    baseline_hits = sum(_is_reversal(frame, position) for position in baseline_positions)
    volatility_hits = sum(_has_volatility_expansion(frame, position) for position in positions)
    breakout_hits = sum(_has_breakout(frame, position) for position in positions)
    return {
        "sample_count": len(positions),
        "reversal_rate": round(hits / len(positions) * 100, 1) if positions else None,
        "baseline_sample_count": len(baseline_positions),
        "random_baseline_reversal_rate": round(baseline_hits / len(baseline_positions) * 100, 1)
        if baseline_positions
        else None,
        "edge_percentage_points": round(
            (hits / len(positions) - baseline_hits / len(baseline_positions)) * 100, 1
        )
        if positions and baseline_positions
        else None,
        "volatility_expansion_rate": round(volatility_hits / len(positions) * 100, 1)
        if positions
        else None,
        "breakout_rate": round(breakout_hits / len(positions) * 100, 1) if positions else None,
        "baseline_policy": "使用相同样本数、等距选取且不与江恩窗口重叠的历史 K 线作为基线。",
    }


def _walk_forward_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    if len(events) < 15:
        return {"available": False, "note": "事件样本不足 15 次，暂不进行样本外校准。"}
    train_end = int(len(events) * 0.6)
    validation_end = int(len(events) * 0.8)
    groups = {
        "train": events[:train_end],
        "validation": events[train_end:validation_end],
        "out_of_sample": events[validation_end:],
    }
    result: dict[str, Any] = {"available": True, "split": "60%/20%/20%，严格按时间顺序"}
    for name, rows in groups.items():
        values = [float(item["return_5"]) for item in rows if "return_5" in item]
        result[name] = {
            "sample_count": len(values),
            "direction_accuracy": round(sum(value > 0 for value in values) / len(values) * 100, 1)
            if values
            else None,
            "median_return": round(float(np.median(values)) * 100, 3) if values else None,
        }
    result["calibrated"] = result["out_of_sample"]["sample_count"] >= 30
    return result


def evaluate_gann_history(frame: pd.DataFrame, config: GannConfig = GannConfig()) -> dict[str, Any]:
    """回放只使用已到 confirmation_position 的锚点，结果与随机时间窗对照。"""
    anchors = build_anchor_candidates(frame, config)
    events = _angle_events(frame, config)
    scores = [item.score for item in anchors]
    score_buckets: dict[str, list[float]] = {"low": [], "medium": [], "high": []}
    for event in events:
        if "return_5" not in event:
            continue
        score = float(event["anchor_score"])
        bucket = "high" if score >= 70 else "medium" if score >= 50 else "low"
        score_buckets[bucket].append(float(event["return_5"]))
    survival = []
    for index, anchor in enumerate(anchors):
        end = min(
            (
                item.pivot.confirmation_position
                for item in anchors[index + 1 :]
                if item.direction == anchor.direction
            ),
            default=len(frame),
        )
        closes = pd.to_numeric(
            frame["close"].iloc[anchor.pivot.confirmation_position : end], errors="coerce"
        )
        threshold = (
            anchor.pivot.price - anchor.atr * 0.15
            if anchor.direction == "up"
            else anchor.pivot.price + anchor.atr * 0.15
        )
        survived = (
            not bool((closes < threshold).any())
            if anchor.direction == "up"
            else not bool((closes > threshold).any())
        )
        survival.append(survived)
    return {
        "anchor": {
            "sample_count": len(anchors),
            "survival_rate": round(sum(survival) / len(survival) * 100, 1) if survival else None,
            "revision_frequency": round(max(len(anchors) - 2, 0) / max(len(frame), 1) * 100, 2),
            "median_score": round(float(np.median(scores)), 1) if scores else None,
            "score_vs_performance": {
                key: {
                    "sample_count": len(values),
                    "median_5_bar_return": round(float(np.median(values)) * 100, 3)
                    if values
                    else None,
                }
                for key, values in score_buckets.items()
            },
        },
        "angle_events": _summarize_events(events),
        "time_windows": _time_window_study(frame, config),
        "walk_forward": _walk_forward_summary(events),
        "sample_count": len(events),
        "resolved_count": sum("return_5" in item for item in events),
        "calibrated": len([item for item in events if "return_5" in item]) >= 30,
        "no_lookahead": True,
        "note": "统计按锚点确认时间和生命周期回放；不足 30 个已决样本时不作为概率。",
    }


__all__ = ["RETURN_HORIZONS", "evaluate_gann_history"]
