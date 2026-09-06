"""威科夫候选结构的确认、目标与失效条件。"""

from __future__ import annotations

from typing import Any

import pandas as pd


def project_wyckoff(frame: pd.DataFrame, structure: dict[str, Any]) -> dict[str, Any]:
    """按 Phase 与关键事件生成条件路径，不预测精确到达日期。"""
    support = float(structure["range"]["support"])
    resistance = float(structure["range"]["resistance"])
    width = resistance - support
    atr = float(frame["ATR14"].iloc[-1])
    direction = structure["direction"]
    phase = str(structure.get("phase", "B"))
    events = structure.get("events", [])
    strength_label = "SOS" if direction == "up" else "SOW"
    test_label = "LPS" if direction == "up" else "LPSY"
    strength_event = next(
        (item for item in reversed(events) if item.get("event") == strength_label),
        None,
    )
    test_event = next(
        (item for item in reversed(events) if item.get("event") == test_label),
        None,
    )
    spring_or_utad = next(
        (
            item
            for item in reversed(events)
            if item.get("event") in {"Spring", "UTAD"}
        ),
        None,
    )
    if direction == "up":
        confirmation = resistance
        if phase == "C" and spring_or_utad:
            invalidation = float(spring_or_utad["low"]) - atr * 0.1
            invalidation_basis = "Spring 低点"
        elif phase in {"D", "E"} and test_event:
            invalidation = float(test_event["low"]) - atr * 0.15
            invalidation_basis = "LPS 回测低点"
        elif phase in {"D", "E"} and strength_event:
            invalidation = resistance - atr * 0.5
            invalidation_basis = "SOS 突破带"
        else:
            invalidation = support - atr * 0.25
            invalidation_basis = "交易区间下沿"
        target_zone = [resistance + width * 0.5, resistance + width]
        confirmation_rule = "收盘突破 Creek（交易区间上沿）后确认上行路径"
    else:
        confirmation = support
        if phase == "C" and spring_or_utad:
            invalidation = float(spring_or_utad["high"]) + atr * 0.1
            invalidation_basis = "UTAD 高点"
        elif phase in {"D", "E"} and test_event:
            invalidation = float(test_event["high"]) + atr * 0.15
            invalidation_basis = "LPSY 回测高点"
        elif phase in {"D", "E"} and strength_event:
            invalidation = support + atr * 0.5
            invalidation_basis = "SOW 跌破带"
        else:
            invalidation = resistance + atr * 0.25
            invalidation_basis = "交易区间上沿"
        target_zone = [support - width, support - width * 0.5]
        confirmation_rule = "收盘跌破 Ice（交易区间下沿）后确认下行路径"
    confirmed_at = strength_event.get("confirmed_at") if strength_event else None
    confirmation_status = "confirmed" if strength_event or phase == "E" else "waiting"
    return {
        "path_direction": direction,
        "confirmation_status": confirmation_status,
        "confirmed_at": confirmed_at,
        "confirmation": round(confirmation, 6),
        "invalidation": round(invalidation, 6),
        "invalidation_basis": invalidation_basis,
        "target_zone": [round(value, 6) for value in sorted(target_zone)],
        "target_method": "冻结交易区间宽度的 0.5×～1.0× 条件投影",
        "confirmation_rule": confirmation_rule,
        "invalidation_rule": f"收盘越过{invalidation_basis}后撤销当前候选",
        "note": "路径横向距离仅为结构示意，不预测到达时间。",
    }
