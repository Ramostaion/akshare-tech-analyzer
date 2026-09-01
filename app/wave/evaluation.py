"""浪形条件情景的逐根历史回放统计。"""

from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Any

import pandas as pd

from app.wave.patterns import find_wave_candidates
from app.wave.pivots import confirmed_zigzag_pivots

CandidateGroup = tuple[str, str, str, str]


def candidate_group(candidate: dict[str, Any]) -> CandidateGroup:
    """返回用于历史同类样本分组的稳定键。"""
    return (
        str(candidate.get("scale", "标准尺度")),
        str(candidate["pattern"]),
        str(candidate["direction"]),
        str(candidate["status"]),
    )


def scenario_state(close: float, projection: dict[str, Any]) -> str:
    """仅使用当前收盘价判断候选处于等待、确认或失效状态。"""
    direction = projection.get("path_direction")
    confirmation = projection.get("confirmation")
    invalidation = projection.get("invalidation")
    if direction not in {"up", "down"} or invalidation is None:
        return "waiting"
    invalidated = close < float(invalidation) if direction == "up" else close > float(invalidation)
    if invalidated:
        return "invalidated"
    zone = projection.get("primary_zone", [])
    if len(zone) == 2:
        zone_lower, zone_upper = sorted(float(value) for value in zone)
        inside_zone = zone_lower <= close <= zone_upper
        if inside_zone:
            return "in_target_zone"
        target_reached = close > zone_upper if direction == "up" else close < zone_lower
        if target_reached:
            return "target_reached"
    if confirmation is None:
        return "confirmed"
    confirmed = close > float(confirmation) if direction == "up" else close < float(confirmation)
    return "confirmed" if confirmed else "waiting"


def _evaluate_projection(
    future: pd.DataFrame,
    analysis_close: float,
    projection: dict[str, Any],
) -> tuple[str, int | None]:
    """按当时已知阈值回放未来；同根目标/失效时保守记为失效。"""
    zone = projection.get("primary_zone", [])
    invalidation = projection.get("invalidation")
    confirmation = projection.get("confirmation")
    direction = projection.get("path_direction")
    if len(zone) != 2 or invalidation is None or direction not in {"up", "down"}:
        return "unresolved", None
    zone_lower, zone_upper = sorted(float(value) for value in zone)
    invalidation = float(invalidation)
    confirmed = confirmation is None
    if confirmation is not None:
        confirmation = float(confirmation)
        confirmed = (
            analysis_close > confirmation
            if direction == "up"
            else analysis_close < confirmation
        )

    for bars, row in enumerate(future.itertuples(), start=1):
        close = float(row.close)
        invalidated = close < invalidation if direction == "up" else close > invalidation
        if invalidated:
            return "invalidation_first", bars
        if not confirmed and confirmation is not None:
            confirmed = close > confirmation if direction == "up" else close < confirmation
            # 确认只在本根收盘后可知；本根盘中即使触及目标也不能倒推为确认后到达。
            continue
        target_touched = (
            float(row.high) >= zone_lower if direction == "up" else float(row.low) <= zone_upper
        )
        if target_touched:
            return "target_first", bars
    return ("unresolved" if confirmed else "unconfirmed"), None


def evaluate_candidate_history(
    frame: pd.DataFrame,
    current_candidates: list[dict[str, Any]],
    scales: tuple[tuple[str, int, float], ...],
    *,
    lookahead: int = 20,
    minimum_history: int = 80,
    maximum_bars: int = 480,
    calibration_samples: int = 30,
) -> dict[CandidateGroup, dict[str, Any]]:
    """在有限窗口内逐根生成候选并统计目标/失效先达结果。"""
    wanted = {candidate_group(candidate) for candidate in current_candidates}
    if not wanted or len(frame) < minimum_history + lookahead + 1:
        return {}
    required = {"datetime", "open", "high", "low", "close", "ATR14"}
    if required.difference(frame.columns):
        return {}

    sample = frame.tail(maximum_bars + lookahead).reset_index(drop=True)
    seen: set[tuple[object, ...]] = set()
    events: dict[CandidateGroup, list[tuple[str, int | None]]] = defaultdict(list)
    last_endpoint = len(sample) - lookahead
    for endpoint in range(minimum_history, last_endpoint):
        prefix = sample.iloc[: endpoint + 1]
        analysis_close = float(prefix["close"].iloc[-1])
        future = sample.iloc[endpoint + 1 : endpoint + 1 + lookahead]
        for scale, swing_window, atr_threshold in scales:
            pivots = confirmed_zigzag_pivots(prefix, swing_window, atr_threshold)
            for candidate in find_wave_candidates(prefix, pivots, top_n=3):
                candidate["scale"] = scale
                group = candidate_group(candidate)
                if group not in wanted:
                    continue
                projection = candidate["projection"]
                if scenario_state(analysis_close, projection) == "invalidated":
                    continue
                signature = (
                    *group,
                    tuple(item["timestamp"] for item in candidate["pivots"]),
                )
                if signature in seen:
                    continue
                seen.add(signature)
                events[group].append(
                    _evaluate_projection(future, analysis_close, projection)
                )

    results: dict[CandidateGroup, dict[str, Any]] = {}
    for group in wanted:
        group_events = events.get(group, [])
        target_bars = [bars for outcome, bars in group_events if outcome == "target_first"]
        invalidations = sum(outcome == "invalidation_first" for outcome, _ in group_events)
        unresolved = sum(outcome == "unresolved" for outcome, _ in group_events)
        unconfirmed = sum(outcome == "unconfirmed" for outcome, _ in group_events)
        resolved = len(target_bars) + invalidations
        calibrated = resolved >= calibration_samples
        results[group] = {
            "sample_count": len(group_events),
            "resolved_count": resolved,
            "target_first_count": len(target_bars),
            "invalidation_first_count": invalidations,
            "unresolved_count": unresolved,
            "unconfirmed_count": unconfirmed,
            "target_first_rate": round(len(target_bars) / resolved * 100, 1)
            if calibrated
            else None,
            "median_target_bars": round(float(median(target_bars)), 1)
            if calibrated and target_bars
            else None,
            "calibrated": calibrated,
            "lookahead_bars": lookahead,
            "note": (
                "历史同类结构采用逐根无未来回放；概率仅在已决样本不少于"
                f"{calibration_samples}次时展示。"
            ),
        }
    return results
