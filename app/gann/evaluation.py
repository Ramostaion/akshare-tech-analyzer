"""江恩锚点生命周期与固定角线的逐根保守回放。"""

from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np
import pandas as pd

from app.gann.anchors import confirmed_gann_anchors
from app.gann.projection import project_gann


def _evaluate_lifecycle(
    future: pd.DataFrame,
    projection: dict[str, Any],
    direction: str,
) -> dict[str, Any]:
    sign = 1 if direction == "up" else -1
    confirmation = float(projection["confirmation"])
    invalidation = float(projection["invalidation"])
    target_zone = projection.get("target_zone", [confirmation, confirmation])
    target = float(target_zone[0] if sign > 0 else target_zone[-1])
    unit = float(projection["scale"]["unit_per_bar"])
    pivot_position = int(projection["anchor"]["position"])
    history_end = int(projection.get("history_end_position", pivot_position))
    confirmed = projection.get("confirmation_status") == "confirmed"
    confirmation_bar = 0 if confirmed else None
    touched = False
    held = False
    consecutive_breach = 0
    target_reached = False
    mfe = 0.0
    mae = 0.0
    anchor_price = float(projection["anchor"]["price"])
    for bars, row in enumerate(future.itertuples(), start=1):
        favorable = (float(row.high) - anchor_price) * sign if sign > 0 else (
            anchor_price - float(row.low)
        )
        adverse = (anchor_price - float(row.low)) if sign > 0 else (
            float(row.high) - anchor_price
        )
        mfe = max(mfe, favorable)
        mae = max(mae, adverse)
        invalid = row.close <= invalidation if sign > 0 else row.close >= invalidation
        if invalid:
            return {
                "confirmed": confirmed,
                "confirmation_bar": confirmation_bar,
                "resolved": True,
                "target_reached": False,
                "angle_touched": touched,
                "angle_held": held,
                "angle_broken": consecutive_breach >= 1,
                "bars": bars,
                "mfe_atr": mfe / float(projection["scale"]["atr"]),
                "mae_atr": mae / float(projection["scale"]["atr"]),
            }
        if not confirmed:
            confirmed = row.close > confirmation if sign > 0 else row.close < confirmation
            if confirmed:
                confirmation_bar = bars
                continue
        absolute_position = history_end + bars
        line = anchor_price + sign * unit * (absolute_position - pivot_position)
        tolerance = float(projection["scale"]["atr"]) * 0.35
        touched_now = row.low <= line + tolerance and row.high >= line - tolerance
        side = (float(row.close) - line) * sign
        if touched_now:
            touched = True
            held = held or side >= 0
        consecutive_breach = consecutive_breach + 1 if side < 0 else 0
        if consecutive_breach >= 2:
            return {
                "confirmed": confirmed,
                "confirmation_bar": confirmation_bar,
                "resolved": True,
                "target_reached": False,
                "angle_touched": touched,
                "angle_held": held,
                "angle_broken": True,
                "bars": bars,
                "mfe_atr": mfe / float(projection["scale"]["atr"]),
                "mae_atr": mae / float(projection["scale"]["atr"]),
            }
        reached = row.high >= target if sign > 0 else row.low <= target
        if confirmed and reached:
            target_reached = True
    return {
        "confirmed": confirmed,
        "confirmation_bar": confirmation_bar,
        "resolved": target_reached or consecutive_breach >= 2,
        "target_reached": target_reached,
        "angle_touched": touched,
        "angle_held": held,
        "angle_broken": consecutive_breach >= 2,
        "bars": len(future),
        "mfe_atr": mfe / float(projection["scale"]["atr"]),
        "mae_atr": mae / float(projection["scale"]["atr"]),
    }


def evaluate_gann_history(
    frame: pd.DataFrame,
    direction: str,
    lookahead_bars: int = 24,
    max_history_bars: int = 800,
    evaluation_stride: int = 2,
) -> dict[str, object]:
    """每个晋升主锚只采样一次，并在下一主锚确认时结束旧生命周期。"""
    outcomes: list[dict[str, Any]] = []
    seen: set[tuple[str, pd.Timestamp]] = set()
    scale_counts: Counter[str] = Counter()
    first_end = max(30, len(frame) - max_history_bars)
    last_end = max(first_end + 1, len(frame) - 1)
    for end in range(first_end, last_end, evaluation_stride):
        history = frame.iloc[: end + 1].reset_index(drop=True)
        anchor = next(
            (item for item in confirmed_gann_anchors(history) if item.direction == direction),
            None,
        )
        if anchor is None:
            continue
        key = (anchor.pivot.kind, anchor.pivot.timestamp)
        if key in seen:
            continue
        seen.add(key)
        projection = project_gann(history, anchor)
        if projection.get("status") != "active":
            continue
        projection["history_end_position"] = end
        scale_counts[str(projection["scale"]["key"])] += 1
        future_end = min(len(frame), end + 1 + lookahead_bars)
        superseded = False
        for next_end in range(end + 1, future_end):
            next_history = frame.iloc[: next_end + 1].reset_index(drop=True)
            next_anchor = next(
                (
                    item
                    for item in confirmed_gann_anchors(next_history)
                    if item.direction == direction
                ),
                None,
            )
            if next_anchor is not None and next_anchor.pivot.timestamp != anchor.pivot.timestamp:
                future_end = next_end
                superseded = True
                break
        future = frame.iloc[end + 1 : future_end]
        outcome = _evaluate_lifecycle(future, projection, direction)
        outcome["superseded"] = superseded
        outcomes.append(outcome)
    confirmed = [item for item in outcomes if item["confirmed"]]
    resolved = [item for item in outcomes if item["resolved"]]
    target_wins = [item for item in resolved if item["target_reached"]]
    touches = [item for item in outcomes if item["angle_touched"]]
    holds = [item for item in touches if item["angle_held"]]
    calibrated = len(resolved) >= 30
    confirmation_calibrated = len(outcomes) >= 30
    touch_calibrated = len(touches) >= 30
    return {
        "sample_count": len(outcomes),
        "resolved_count": len(resolved),
        "unresolved_count": len(outcomes) - len(resolved),
        "confirmation_count": len(confirmed),
        "confirmation_rate": (
            round(len(confirmed) / len(outcomes) * 100, 1)
            if confirmation_calibrated and outcomes
            else None
        ),
        "angle_touch_count": len(touches),
        "angle_hold_count": len(holds),
        "angle_hold_rate": (
            round(len(holds) / len(touches) * 100, 1) if touch_calibrated else None
        ),
        "angle_break_count": sum(bool(item["angle_broken"]) for item in outcomes),
        "promotion_count": sum(bool(item["superseded"]) for item in outcomes),
        "target_first_count": len(target_wins),
        "invalidation_first_count": len(resolved) - len(target_wins),
        "target_first_rate": (
            round(len(target_wins) / len(resolved) * 100, 1)
            if calibrated and resolved
            else None
        ),
        "median_target_bars": (
            round(float(np.median([item["bars"] for item in target_wins])), 1)
            if calibrated and target_wins
            else None
        ),
        "median_mfe_atr": (
            round(float(np.median([item["mfe_atr"] for item in outcomes])), 2)
            if outcomes
            else None
        ),
        "median_mae_atr": (
            round(float(np.median([item["mae_atr"] for item in outcomes])), 2)
            if outcomes
            else None
        ),
        "scale_counts": dict(scale_counts),
        "calibrated": calibrated,
        "confirmation_calibrated": confirmation_calibrated,
        "angle_hold_calibrated": touch_calibrated,
        "lookahead_bars": lookahead_bars,
        "evaluation_stride": evaluation_stride,
        "evaluation_bars": min(len(frame), max_history_bars),
        "sampling_policy": (
            "每个右确认晋升主锚只在首次出现时采样一次，下一同向主锚确认时结束旧生命周期；"
            f"为控制计算量，每 {evaluation_stride} 根 K 线检查一次"
        ),
        "note": (
            "已决样本不足 30 次，暂不展示目标概率；确认率与角线守住率分别校准。"
            if not calibrated
            else "历史结果按锚点生命周期去重，不代表未来收益。"
        ),
    }
