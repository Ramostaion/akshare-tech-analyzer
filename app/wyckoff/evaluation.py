"""威科夫候选按稳定区间生命周期进行保守历史回放。"""

from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np
import pandas as pd

from app.wyckoff.events import detect_wyckoff_structure
from app.wyckoff.projection import project_wyckoff


def _direction_candidate(structure: dict[str, Any], direction: str) -> dict[str, Any] | None:
    candidate = next(
        (
            item
            for item in structure.get("alternatives", [])
            if item.get("direction") == direction
        ),
        None,
    )
    if candidate is None:
        return None
    return structure | candidate


def _evaluate_lifecycle(
    future: pd.DataFrame,
    projection: dict[str, Any],
    direction: str,
) -> dict[str, Any]:
    confirmation = float(projection["confirmation"])
    invalidation = float(projection["invalidation"])
    lower, upper = (float(value) for value in projection["target_zone"])
    confirmed = projection.get("confirmation_status") == "confirmed"
    confirmation_bar = 0 if confirmed else None
    for bars, row in enumerate(future.itertuples(), start=1):
        invalid = row.close <= invalidation if direction == "up" else row.close >= invalidation
        if invalid:
            return {
                "confirmed": confirmed,
                "confirmation_bar": confirmation_bar,
                "resolved": True,
                "target_reached": False,
                "bars": bars,
            }
        if not confirmed:
            confirmed = row.close > confirmation if direction == "up" else row.close < confirmation
            if confirmed:
                confirmation_bar = bars
                continue
        target = row.high >= lower if direction == "up" else row.low <= upper
        if confirmed and target:
            return {
                "confirmed": True,
                "confirmation_bar": confirmation_bar,
                "resolved": True,
                "target_reached": True,
                "bars": bars,
            }
    return {
        "confirmed": confirmed,
        "confirmation_bar": confirmation_bar,
        "resolved": False,
        "target_reached": False,
        "bars": len(future),
    }


def evaluate_wyckoff_history(
    frame: pd.DataFrame,
    direction: str,
    lookahead_bars: int = 20,
    max_history_bars: int = 420,
    evaluation_stride: int = 3,
) -> dict[str, Any]:
    """每个冻结区间和方向只采样一次，并分开统计确认率与目标先达率。"""
    outcomes: list[dict[str, Any]] = []
    seen_lifecycles: set[tuple[str, str]] = set()
    phase_counts: Counter[str] = Counter()
    event_counts: Counter[str] = Counter()
    first_end = max(80, len(frame) - max_history_bars)
    for end in range(first_end, len(frame) - lookahead_bars, evaluation_stride):
        history = frame.iloc[: end + 1]
        detected = detect_wyckoff_structure(history)
        if detected.get("status") != "active":
            continue
        structure = _direction_candidate(detected, direction)
        if structure is None or structure.get("phase") not in {"C", "D", "E"}:
            continue
        if structure.get("current_event") == "Trading Range":
            continue
        lifecycle = (str(detected["range"]["start_timestamp"]), direction)
        if lifecycle in seen_lifecycles:
            continue
        seen_lifecycles.add(lifecycle)
        phase = str(structure["phase"])
        current_event = str(structure["current_event"])
        phase_counts[phase] += 1
        event_counts[current_event] += 1
        projection = project_wyckoff(history, structure)
        future = frame.iloc[end + 1 : end + 1 + lookahead_bars]
        outcome = _evaluate_lifecycle(future, projection, direction)
        outcome.update({"phase": phase, "event": current_event})
        outcomes.append(outcome)

    confirmed = [item for item in outcomes if item["confirmed"]]
    confirmed_resolved = [item for item in confirmed if item["resolved"]]
    target_wins = [item for item in confirmed_resolved if item["target_reached"]]
    candidate_resolved = [item for item in outcomes if item["resolved"]]
    calibrated = len(confirmed_resolved) >= 30
    confirmation_calibrated = len(outcomes) >= 30
    confirmation_rate = (
        round(len(confirmed) / len(outcomes) * 100, 1)
        if confirmation_calibrated and outcomes
        else None
    )
    target_rate = (
        round(len(target_wins) / len(confirmed_resolved) * 100, 1)
        if calibrated and confirmed_resolved
        else None
    )
    target_bars = [int(item["bars"]) for item in target_wins]
    return {
        "sample_count": len(outcomes),
        "resolved_count": len(candidate_resolved),
        "unresolved_count": len(outcomes) - len(candidate_resolved),
        "confirmation_count": len(confirmed),
        "confirmation_rate": confirmation_rate,
        "confirmation_calibrated": confirmation_calibrated,
        "confirmed_resolved_count": len(confirmed_resolved),
        "target_first_rate": target_rate,
        "median_target_bars": (
            round(float(np.median(target_bars)), 1)
            if calibrated and target_bars
            else None
        ),
        "calibrated": calibrated,
        "lookahead_bars": lookahead_bars,
        "evaluation_stride": evaluation_stride,
        "sampling_policy": (
            "每个冻结交易区间和方向只在首次检测到 Phase C～E 时采样一次；"
            f"为控制计算量，每 {evaluation_stride} 根 K 线检查一次"
        ),
        "phase_counts": dict(phase_counts),
        "event_counts": dict(event_counts),
        "note": (
            "确认后的已决样本不足 30 次，暂不展示目标先达率。"
            if not calibrated
            else "历史统计来自去重的结构生命周期，不代表未来收益。"
        ),
    }
