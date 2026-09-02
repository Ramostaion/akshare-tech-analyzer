"""确定性、可回放的 ATR 归一化江恩分析。"""

from __future__ import annotations

import pandas as pd

from app.gann.anchors import confirmed_gann_anchor
from app.gann.evaluation import evaluate_gann_history
from app.gann.projection import project_gann


def analyze_gann(frame: pd.DataFrame) -> dict[str, object]:
    """返回自动确认锚点及江恩条件路径。"""
    anchor = confirmed_gann_anchor(frame)
    if anchor is None:
        return {
            "status": "insufficient",
            "anchor_mode": "auto_confirmed_pivot",
            "historical_validation": {},
            "note": "分析区间内没有足够的已确认高低点，暂不生成江恩图层。",
        }
    result = project_gann(frame, anchor)
    result["anchor_mode"] = "auto_confirmed_pivot"
    result["anchor"]["confirmed_at"] = pd.Timestamp(
        frame["datetime"].iloc[anchor.pivot.confirmation_position]
    ).isoformat()
    result["historical_validation"] = evaluate_gann_history(frame, anchor.direction)
    return result


__all__ = ["analyze_gann", "confirmed_gann_anchor"]
