"""可解释、可回放的威科夫第一版分析。"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.wyckoff.evaluation import evaluate_wyckoff_history
from app.wyckoff.events import detect_wyckoff_structure
from app.wyckoff.projection import project_wyckoff


def analyze_wyckoff(frame: pd.DataFrame) -> dict[str, Any]:
    """返回当前威科夫候选、条件路径和历史回放。"""
    result = detect_wyckoff_structure(frame)
    if result.get("status") != "active":
        result["historical_validation"] = {}
        return result
    result["projection"] = project_wyckoff(frame, result)
    result["historical_validation"] = evaluate_wyckoff_history(frame, result["direction"])
    result["note"] = (
        "威科夫 V2 同时评估吸筹与派发候选；事件先按收盘确认，Test、LPS/LPSY "
        "等后续行为再提供跟随确认。结果不是确定预测。"
    )
    return result


def wyckoff_decision_context(result: dict[str, Any], decision_status: str) -> dict[str, Any]:
    """将威科夫结构作为决策证据，不越过严格 Trigger 独立发单。"""
    if result.get("status") != "active":
        return {
            "bias": "unavailable",
            "alignment": "neutral",
            "note": result.get("note", "威科夫结构当前不可用，不参与方向判断。"),
        }
    structure = "吸筹" if result["direction"] == "up" else "派发"
    phase = str(result.get("phase", "B"))
    if result.get("ambiguous"):
        return {
            "bias": "ambiguous",
            "alignment": "neutral",
            "note": f"吸筹与派发候选分差较小；当前 Phase {phase} 不参与方向确认。",
        }
    if phase in {"A", "B", "C"}:
        return {
            "bias": result["direction"],
            "alignment": "pending",
            "note": f"{structure}候选处于 Phase {phase}，仍需突破与跟随确认。",
        }
    expected = "up" if decision_status == "long_trigger" else (
        "down" if decision_status == "exit_trigger" else None
    )
    alignment = "neutral" if expected is None else (
        "supportive" if expected == result["direction"] else "conflicting"
    )
    suffix = "，与当前 Trigger 方向一致" if alignment == "supportive" else (
        "，与当前 Trigger 方向不一致，需降低执行信心"
        if alignment == "conflicting"
        else ""
    )
    return {
        "bias": result["direction"],
        "alignment": alignment,
        "note": f"{structure}候选进入 Phase {phase}{suffix}。",
    }


__all__ = ["analyze_wyckoff", "detect_wyckoff_structure", "wyckoff_decision_context"]
