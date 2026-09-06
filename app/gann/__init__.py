"""可计算、可解释、可回测且无未来函数的江恩 Price-Time 引擎。"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pandas as pd

from app.gann.anchors import anchor_lifecycles, confirmed_gann_anchor, confirmed_gann_anchors
from app.gann.backtest import evaluate_gann_history
from app.gann.calibration import calibrate_gann_parameters
from app.gann.models import GannConfig, ScaleMode
from app.gann.multitimeframe import higher_timeframe_context
from app.gann.projection import project_gann
from app.gann.snapshots import build_snapshot


def analyze_gann(
    frame: pd.DataFrame,
    period: str = "daily",
    horizontal_levels: dict[str, Any] | None = None,
    *,
    config: GannConfig | None = None,
    scale_mode: ScaleMode | None = None,
    include_backtest: bool = True,
) -> dict[str, Any]:
    """同时保留上、下行锚点候选，并输出当前评分最高的完整 Price-Time 结构。"""
    selected_config = config or GannConfig()
    if scale_mode is not None:
        selected_config = replace(selected_config, scale_mode=scale_mode)
    anchors = confirmed_gann_anchors(frame, selected_config)
    if not anchors:
        return {
            "status": "insufficient",
            "version": "3.0",
            "anchor_mode": "confirmed_atr_zigzag_scored",
            "alternatives": [],
            "historical_validation": {},
            "note": "分析区间内没有完成右侧确认且达到 ATR/百分比阈值的锚点。",
        }
    higher = higher_timeframe_context(frame, period, selected_config)
    alternatives = [
        project_gann(
            frame,
            anchor,
            period,
            horizontal_levels,
            higher,
            selected_config,
            selected_config.scale_mode,
        )
        for anchor in anchors
    ]
    alternatives = [item for item in alternatives if item.get("status") == "active"]
    if not alternatives:
        return {
            "status": "insufficient",
            "version": "3.0",
            "alternatives": [],
            "historical_validation": {},
            "note": "锚点缺少可用标准化价格单位。",
        }
    alternatives.sort(
        key=lambda item: (
            float(item["anchor"]["score"]),
            int(item["anchor"]["confirmation_position"]),
        ),
        reverse=True,
    )
    result = dict(alternatives[0])
    gap = (
        float(alternatives[0]["anchor"]["score"]) - float(alternatives[1]["anchor"]["score"])
        if len(alternatives) > 1
        else 100.0
    )
    compact_alternatives = [
        {
            "direction": item["direction"],
            "anchor": item["anchor"],
            "structural_fit": item["structural_fit"],
            "current_state": item["current_state"],
            "current_state_label": item["current_state_label"],
        }
        for item in alternatives
    ]
    result.update(
        {
            "anchor_mode": "confirmed_atr_zigzag_scored",
            "anchor_selection_policy": (
                "ATR 与百分比混合阈值确认 Pivot；同向新锚确认后晋升，Anchor Score 用于评价权重。"
            ),
            "alternatives": compact_alternatives,
            "ambiguous": len(alternatives) > 1 and gap < 8,
            "score_gap": round(gap, 1),
            "low_confidence_anchor": float(result["anchor"]["score"])
            < selected_config.minimum_anchor_score,
            "historical_validation": (
                evaluate_gann_history(frame, selected_config) if include_backtest else {}
            ),
            "anchor_lifecycles": anchor_lifecycles(frame, selected_config),
            "config": {
                "pivot_window": selected_config.pivot_window,
                "pivot_atr_factor": selected_config.pivot_atr_factor,
                "pivot_percent_threshold": selected_config.pivot_percent_threshold,
                "atr_multiplier": selected_config.atr_multiplier,
                "cycle_lookback": selected_config.cycle_lookback,
                "window_tolerance": selected_config.window_tolerance,
                "price_cluster_tolerance_atr": (
                    selected_config.price_cluster_tolerance_atr
                ),
                "visible_price_zones": selected_config.visible_price_zones,
                "visible_confluence_zones": selected_config.visible_confluence_zones,
                "visible_time_window_score": selected_config.visible_time_window_score,
            },
        }
    )
    result["prediction_snapshot"] = build_snapshot("", period, result)
    return result


def gann_decision_context(result: dict[str, Any], decision_status: str) -> dict[str, Any]:
    """江恩只提供支持、冲突或中性背景，永远不创建订单。"""
    if result.get("status") != "active":
        return {
            "bias": "unavailable",
            "alignment": "neutral",
            "note": result.get("note", "江恩结构不可用。"),
        }
    if result.get("ambiguous") or result.get("low_confidence_anchor"):
        return {
            "bias": "ambiguous",
            "alignment": "neutral",
            "note": "江恩双向候选接近或锚点评分偏低，仅作观察。",
        }
    expected = (
        "up"
        if decision_status == "long_trigger"
        else "down"
        if decision_status == "exit_trigger"
        else None
    )
    direction = str(result["direction"])
    alignment = (
        "neutral" if expected is None else "supportive" if expected == direction else "conflicting"
    )
    suffix = (
        "与当前 Trigger 同向。"
        if alignment == "supportive"
        else "与当前 Trigger 冲突。"
        if alignment == "conflicting"
        else "当前没有严格 Trigger。"
    )
    return {
        "bias": direction,
        "alignment": alignment,
        "note": f"江恩 {result.get('current_state_label', '中性观察')}；{suffix}",
    }


__all__ = [
    "GannConfig",
    "analyze_gann",
    "calibrate_gann_parameters",
    "confirmed_gann_anchor",
    "confirmed_gann_anchors",
    "gann_decision_context",
]
