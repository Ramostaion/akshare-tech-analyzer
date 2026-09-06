"""确定性、可回放的江恩结构 V2。"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.gann.anchors import confirmed_gann_anchor, confirmed_gann_anchors
from app.gann.evaluation import evaluate_gann_history
from app.gann.projection import project_gann


def analyze_gann(frame: pd.DataFrame) -> dict[str, Any]:
    """同时评估上、下行晋升主锚，并返回分数更高的主候选。"""
    anchors = confirmed_gann_anchors(frame)
    if not anchors:
        return {
            "status": "insufficient",
            "version": "2.1",
            "anchor_mode": "promoted_confirmed_pivot",
            "alternatives": [],
            "historical_validation": {},
            "note": "分析区间内没有足够的已确认高低点，暂不生成江恩图层。",
        }
    alternatives: list[dict[str, Any]] = []
    for anchor in anchors:
        candidate = project_gann(frame, anchor)
        if candidate.get("status") != "active":
            continue
        confirmation = anchor.pivot.confirmation_position
        candidate["anchor"]["confirmed_at"] = pd.Timestamp(
            frame["datetime"].iloc[confirmation]
        ).isoformat()
        candidate["anchor"]["age_bars"] = len(frame) - 1 - anchor.pivot.position
        alternatives.append(candidate)
    if not alternatives:
        return {
            "status": "insufficient",
            "version": "2.1",
            "anchor_mode": "promoted_confirmed_pivot",
            "alternatives": [],
            "historical_validation": {},
            "note": "已确认锚点缺少可靠波动尺度，暂不生成江恩图层。",
        }
    alternatives.sort(
        key=lambda item: (
            item["anchor"].get("invalidated_at_position") is None,
            float(item["structural_fit"]),
        ),
        reverse=True,
    )
    primary = alternatives[0]
    candidates_comparable = len(alternatives) > 1 and (
        (primary["anchor"].get("invalidated_at_position") is None)
        == (alternatives[1]["anchor"].get("invalidated_at_position") is None)
    )
    score_gap = (
        float(primary["structural_fit"]) - float(alternatives[1]["structural_fit"])
        if len(alternatives) > 1
        else 1.0
    )
    result = dict(primary)
    result.update(
        {
            "version": "2.1",
            "anchor_mode": "promoted_confirmed_pivot",
            "anchor_selection_policy": (
                "同方向新 Pivot 达到 1 ATR 摆幅并完成右侧三根确认后晋升为当前主锚；"
                "旧锚仅保留为长期参考。"
            ),
            "alternatives": alternatives,
            "ambiguous": candidates_comparable and score_gap < 0.08,
            "score_gap": round(score_gap, 3),
            "historical_validation": evaluate_gann_history(frame, str(primary["direction"])),
        }
    )
    return result


def gann_decision_context(result: dict[str, Any], decision_status: str) -> dict[str, Any]:
    """江恩仅评价 Trigger 与当前运动速度是否一致，不独立发单。"""
    if result.get("status") != "active":
        return {
            "bias": "unavailable",
            "alignment": "neutral",
            "note": result.get("note", "江恩结构当前不可用，不参与交易结论。"),
        }
    direction = str(result.get("direction"))
    state = str(result.get("current_state"))
    if result.get("ambiguous"):
        return {
            "bias": "ambiguous",
            "alignment": "neutral",
            "note": "上、下行江恩候选分差较小，仅保留为速度观察，不参与方向确认。",
        }
    if state in {"anchor_invalidated", "slow_angle_broken", "one_by_one_broken"}:
        return {
            "bias": direction,
            "alignment": "fragile",
            "note": f"{result.get('current_state_label')}，当前江恩候选不提供执行支持。",
        }
    expected = (
        "up"
        if decision_status == "long_trigger"
        else "down"
        if decision_status == "exit_trigger"
        else None
    )
    alignment = (
        "neutral"
        if expected is None
        else "supportive"
        if expected == direction
        else "conflicting"
    )
    direction_label = "上行" if direction == "up" else "下行"
    suffix = (
        "，与当前 Trigger 方向一致"
        if alignment == "supportive"
        else "，与当前 Trigger 方向冲突，需降低执行信心"
        if alignment == "conflicting"
        else ""
    )
    return {
        "bias": direction,
        "alignment": alignment,
        "note": f"{direction_label}固定角线：{result.get('current_state_label')}{suffix}。",
    }


__all__ = [
    "analyze_gann",
    "confirmed_gann_anchor",
    "confirmed_gann_anchors",
    "gann_decision_context",
]
