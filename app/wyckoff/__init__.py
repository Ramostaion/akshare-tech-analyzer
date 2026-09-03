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
        "威科夫结果是量价规则候选，不是确定预测；事件均在当根收盘后确认。"
    )
    return result


__all__ = ["analyze_wyckoff", "detect_wyckoff_structure"]
