"""多尺度 Elliott Wave 候选分析。"""

from typing import Any

from app.wave.evaluation import candidate_group, evaluate_candidate_history, scenario_state
from app.wave.patterns import find_wave_candidates
from app.wave.pivots import confirmed_zigzag_pivots

WAVE_SCALES = (
    ("短尺度", 2, 0.8),
    ("标准尺度", 3, 1.0),
    ("宽尺度", 5, 1.5),
)


def _candidate_key(candidate: dict[str, Any]) -> tuple[object, ...]:
    return (
        candidate["pattern"],
        candidate["direction"],
        tuple(item["position"] for item in candidate["pivots"]),
    )


def _advance_completed_target_zone(candidate: dict[str, Any], close: float) -> None:
    """已完成结构穿过前一观察区时推进到下一档，不删除结构候选。"""
    projection = candidate["projection"]
    target_zones = projection.get("target_zones", [])
    direction = projection.get("path_direction")
    if candidate.get("status") != "completed" or not target_zones:
        return
    selected = len(target_zones) - 1
    for index, item in enumerate(target_zones):
        lower, upper = sorted(float(value) for value in item["zone"])
        passed = close > upper if direction == "up" else close < lower
        if not passed:
            selected = index
            break
    projection["primary_zone"] = target_zones[selected]["zone"]
    projection["target_label"] = target_zones[selected]["label"]
    projection["zone_stage"] = selected + 1


def analyze_wave_candidates(frame, top_n: int = 3):
    """返回多尺度 Top-N 竞争候选；匹配度不是上涨或下跌概率。"""
    candidates: list[dict[str, Any]] = []
    pivot_counts: dict[str, int] = {}
    seen: set[tuple[object, ...]] = set()
    for scale, swing_window, atr_threshold in WAVE_SCALES:
        pivots = confirmed_zigzag_pivots(frame, swing_window, atr_threshold)
        pivot_counts[scale] = len(pivots)
        for candidate in find_wave_candidates(frame, pivots, top_n=top_n):
            key = _candidate_key(candidate)
            if key in seen:
                continue
            seen.add(key)
            candidate["scale"] = scale
            candidates.append(candidate)
    candidates.sort(key=lambda item: item["structural_fit"], reverse=True)
    current_close = float(frame["close"].iloc[-1]) if not frame.empty else float("nan")
    state_labels = {
        "waiting": "等待收盘确认",
        "confirmed": "路径已经收盘确认",
        "invalidated": "候选已经失效",
        "in_target_zone": "价格正在目标观察区内",
        "target_reached": "目标观察区已经触及",
    }
    for candidate in candidates:
        _advance_completed_target_zone(candidate, current_close)
        state = scenario_state(current_close, candidate["projection"])
        candidate["current_state"] = state
        candidate["current_state_label"] = state_labels[state]
    display_candidates = candidates[: max(0, top_n)]
    historical = evaluate_candidate_history(frame, display_candidates, WAVE_SCALES)
    for candidate in display_candidates:
        candidate["historical_validation"] = historical.get(
            candidate_group(candidate),
            {
                "sample_count": 0,
                "resolved_count": 0,
                "target_first_rate": None,
                "median_target_bars": None,
                "calibrated": False,
                "lookahead_bars": 20,
                "note": "历史同类已决样本不足，暂不展示概率。",
            },
        )
    return {
        "candidates": display_candidates,
        "pivot_count": pivot_counts["标准尺度"],
        "pivot_counts": pivot_counts,
        "note": (
            "波浪结果来自多尺度已确认 Pivot；结构匹配度是规则质量分，不是方向概率。"
            "目标区与失效位均为条件情景，横轴不预测到达时间。"
        ),
    }


__all__ = ["analyze_wave_candidates", "confirmed_zigzag_pivots", "find_wave_candidates"]
