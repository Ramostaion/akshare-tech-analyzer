"""威科夫候选结构的确认、目标与失效条件。"""

from __future__ import annotations

from typing import Any

import pandas as pd


def project_wyckoff(frame: pd.DataFrame, structure: dict[str, Any]) -> dict[str, Any]:
    """从交易区间宽度生成条件路径，不预测精确到达日期。"""
    support = float(structure["range"]["support"])
    resistance = float(structure["range"]["resistance"])
    width = resistance - support
    atr = float(frame["ATR14"].iloc[-1])
    direction = structure["direction"]
    if direction == "up":
        confirmation = resistance
        invalidation = support - atr * 0.25
        target_zone = [resistance + width * 0.5, resistance + width]
        confirmation_rule = "收盘突破 Creek（交易区间上沿）后确认上行路径"
    else:
        confirmation = support
        invalidation = resistance + atr * 0.25
        target_zone = [support - width, support - width * 0.5]
        confirmation_rule = "收盘跌破 Ice（交易区间下沿）后确认下行路径"
    return {
        "path_direction": direction,
        "confirmation": round(confirmation, 6),
        "invalidation": round(invalidation, 6),
        "target_zone": [round(value, 6) for value in sorted(target_zone)],
        "confirmation_rule": confirmation_rule,
        "invalidation_rule": "收盘越过结构另一侧边界后撤销当前候选",
        "note": "路径横向距离仅为结构示意，不预测到达时间。",
    }
