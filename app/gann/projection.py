"""可证伪的江恩固定角线、事件状态与时价共振。"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.gann.anchors import GannAnchor

FAN_RATIOS = (("2×1", 2.0), ("1×1", 1.0), ("1×2", 0.5))
PRICE_DIVISIONS = (0.125, 0.25, 1 / 3, 0.5, 2 / 3, 0.75, 0.875, 1.0)
TIME_CYCLES = (8, 16, 24, 32, 48)
DISPLAY_BARS = 24


def _scale_candidates(frame: pd.DataFrame, anchor: GannAnchor) -> list[dict[str, Any]]:
    confirmation = anchor.pivot.confirmation_position
    values = pd.to_numeric(
        frame["ATR14"].iloc[max(0, confirmation - 49) : confirmation + 1]
    )
    long_atr = float(values.median())
    duration = max(1, abs(anchor.pivot.position - anchor.previous_pivot.position))
    swing_unit = abs(anchor.pivot.price - anchor.previous_pivot.price) / duration
    raw = [
        ("atr14_eighth", "锚点 ATR14/8", anchor.atr / 8),
        ("swing_velocity", "前一摆幅/持续根数", swing_unit),
        ("long_atr_eighth", "长期 ATR 中位数/8", long_atr / 8),
    ]
    sign = 1 if anchor.direction == "up" else -1
    closes = pd.to_numeric(frame["close"], errors="coerce").to_numpy(dtype=float)
    start = anchor.pivot.confirmation_position
    end = min(len(frame), start + 80)
    candidates: list[dict[str, Any]] = []
    for key, label, unit in raw:
        if not np.isfinite(unit) or unit <= 0:
            continue
        distances: list[float] = []
        touches = 0
        breaches = 0
        for position in range(start, end):
            elapsed = position - anchor.pivot.position
            lines = [
                anchor.pivot.price + sign * unit * ratio * elapsed
                for _name, ratio in FAN_RATIOS
            ]
            distance = min(abs(closes[position] - line) for line in lines) / anchor.atr
            distances.append(min(distance, 3.0))
            touches += distance <= 0.35
            slow = anchor.pivot.price + sign * unit * 0.5 * elapsed
            breaches += closes[position] < slow if sign > 0 else closes[position] > slow
        fit = max(0.0, 1 - float(np.mean(distances)) / 2) if distances else 0.0
        score = (
            0.65 * fit
            + 0.25 * min(touches / 4, 1.0)
            - 0.1 * min(breaches / 3, 1.0)
        )
        candidates.append(
            {
                "key": key,
                "label": label,
                "unit_per_bar": float(unit),
                "fit_score": round(max(0.0, min(score, 1.0)), 3),
                "touch_count": int(touches),
                "breach_count": int(breaches),
            }
        )
    return sorted(candidates, key=lambda item: item["fit_score"], reverse=True)


def _line_price(anchor: GannAnchor, unit: float, ratio: float, position: int) -> float:
    sign = 1 if anchor.direction == "up" else -1
    elapsed = max(0, position - anchor.pivot.position)
    return anchor.pivot.price + sign * unit * ratio * elapsed


def _angle_state(
    frame: pd.DataFrame,
    anchor: GannAnchor,
    unit: float,
) -> tuple[str, str, list[dict[str, Any]]]:
    closes = pd.to_numeric(frame["close"], errors="coerce").to_numpy(dtype=float)
    latest = len(frame) - 1
    sign = 1 if anchor.direction == "up" else -1
    relation: list[int] = []
    for position in range(max(anchor.pivot.confirmation_position, latest - 2), latest + 1):
        one = _line_price(anchor, unit, 1.0, position)
        relation.append(1 if (closes[position] - one) * sign >= 0 else -1)
    current = closes[-1]
    fast = _line_price(anchor, unit, 2.0, latest)
    one = _line_price(anchor, unit, 1.0, latest)
    slow = _line_price(anchor, unit, 0.5, latest)
    if anchor.invalidated_at is not None:
        state, label = "anchor_invalidated", "锚点生命周期已经失效"
    elif len(relation) >= 2 and relation[-2:] == [-1, -1]:
        state, label = "one_by_one_broken", "1×1 已连续两根收盘失守"
    elif len(relation) >= 2 and relation[-2] < 0 < relation[-1]:
        state, label = "one_by_one_reclaimed", "1×1 已收盘重新站回"
    elif (current - fast) * sign >= 0:
        state, label = "accelerating", "运行速度高于 2×1"
    elif (current - one) * sign >= 0:
        state, label = "holding_one_by_one", "价格保持在 1×1 有利侧"
    elif (current - slow) * sign >= 0:
        state, label = "slowed_to_one_by_two", "速度降至 1×2 与 1×1 之间"
    else:
        state, label = "slow_angle_broken", "1×2 也已失守，结构脆弱"
    events: list[dict[str, Any]] = []
    event_start = max(anchor.pivot.confirmation_position + 1, latest - 20)
    for position in range(event_start, latest + 1):
        prior = _line_price(anchor, unit, 1.0, position - 1)
        now = _line_price(anchor, unit, 1.0, position)
        prior_side = (closes[position - 1] - prior) * sign
        current_side = (closes[position] - now) * sign
        if prior_side >= 0 > current_side:
            events.append({"event": "跌破1×1", "position": position})
        elif prior_side < 0 <= current_side:
            events.append({"event": "收复1×1", "position": position})
    return state, label, events[-5:]


def _resonance_zones(
    anchor: GannAnchor,
    unit: float,
    levels: list[dict[str, Any]],
    latest: int,
) -> list[dict[str, Any]]:
    zones: list[dict[str, Any]] = []
    tolerance = anchor.atr * 0.35
    for bars in TIME_CYCLES:
        position = anchor.pivot.position + bars
        if position <= latest:
            continue
        for label, ratio in FAN_RATIOS:
            angle_price = _line_price(anchor, unit, ratio, position)
            nearby = [
                item
                for item in levels
                if abs(float(item["price"]) - angle_price) <= tolerance
            ]
            if nearby:
                center = (angle_price + float(nearby[0]["price"])) / 2
                zones.append(
                    {
                        "bars": bars,
                        "position": position,
                        "angle": label,
                        "price_fraction": nearby[0]["label"],
                        "lower": round(center - tolerance, 6),
                        "upper": round(center + tolerance, 6),
                        "components": 3,
                    }
                )
    return zones[:4]


def project_gann(frame: pd.DataFrame, anchor: GannAnchor) -> dict[str, object]:
    """从当前晋升主锚生成连续固定角线、事件和条件观察区。"""
    datetimes = pd.to_datetime(frame["datetime"])
    intervals = datetimes.diff().dropna()
    if intervals.empty or intervals.median() <= pd.Timedelta(0):
        return {"status": "insufficient"}
    interval = intervals.median()
    scales = _scale_candidates(frame, anchor)
    if not scales:
        return {"status": "insufficient"}
    scale = scales[0]
    unit = float(scale["unit_per_bar"])
    latest = len(frame) - 1
    end_position = latest + DISPLAY_BARS
    anchor_time = pd.Timestamp(anchor.pivot.timestamp)
    latest_time = pd.Timestamp(datetimes.iloc[-1])
    future_time = latest_time + interval * DISPLAY_BARS
    fan_lines = [
        {
            "label": label,
            "ratio": ratio,
            "start_time": anchor_time.isoformat(),
            "start_price": round(anchor.pivot.price, 6),
            "current_time": latest_time.isoformat(),
            "current_price": round(_line_price(anchor, unit, ratio, latest), 6),
            "anchor_line_current_price": round(_line_price(anchor, unit, ratio, latest), 6),
            "end_time": future_time.isoformat(),
            "end_price": round(_line_price(anchor, unit, ratio, end_position), 6),
        }
        for label, ratio in FAN_RATIOS
    ]
    swing = abs(anchor.pivot.price - anchor.previous_pivot.price)
    sign = 1 if anchor.direction == "up" else -1
    price_levels = [
        {
            "fraction": round(fraction, 4),
            "label": f"{fraction * 100:.1f}%",
            "price": round(anchor.pivot.price + sign * swing * fraction, 6),
        }
        for fraction in PRICE_DIVISIONS
    ]
    cycles = [
        {"bars": bars, "datetime": (anchor_time + interval * bars).isoformat()}
        for bars in TIME_CYCLES
        if anchor_time + interval * bars > latest_time
    ]
    confirmation = anchor.previous_pivot.price
    target_zone = sorted(
        [
            confirmation + sign * swing * 0.5,
            confirmation + sign * swing,
        ]
    )
    current_close = float(frame["close"].iloc[-1])
    confirmed = current_close > confirmation if sign > 0 else current_close < confirmation
    state, state_label, events = _angle_state(frame, anchor, unit)
    resonance = _resonance_zones(anchor, unit, price_levels, latest)
    for zone in resonance:
        zone["datetime"] = (
            anchor_time + interval * (int(zone["position"]) - anchor.pivot.position)
        ).isoformat()
    components = {
        "anchor_quality": round(anchor.quality, 3),
        "scale_fit": float(scale["fit_score"]),
        "angle_state": 0.9
        if state in {"accelerating", "holding_one_by_one"}
        else 0.65
        if state in {"one_by_one_reclaimed", "slowed_to_one_by_two"}
        else 0.25,
        "confirmation": 1.0 if confirmed else 0.45,
        "resonance": min(len(resonance) / 2, 1.0),
    }
    score = sum(components.values()) / len(components)
    return {
        "status": "active",
        "version": "2.1",
        "direction": anchor.direction,
        "anchor": anchor.as_dict(),
        "scale": {
            "atr": round(anchor.atr, 6),
            "unit_per_bar": round(unit, 6),
            "method": scale["label"],
            "key": scale["key"],
            "candidates": scales,
        },
        "fan_lines": fan_lines,
        "price_levels": price_levels,
        "time_cycles": cycles,
        "resonance_zones": resonance,
        "angle_events": events,
        "confirmation": round(confirmation, 6),
        "confirmation_status": "confirmed" if confirmed else "waiting",
        "target_zone": [round(value, 6) for value in target_zone],
        "invalidation": round(anchor.pivot.price - sign * anchor.atr * 0.15, 6),
        "current_state": state,
        "current_state_label": state_label,
        "score_components": components,
        "structural_fit": round(score, 3),
        "note": (
            "江恩 V2.1 使用右确认晋升主锚和连续固定角线；旧锚仅作长期参考。"
            "共振区仅表示角线、时间窗与价格分割重叠，"
            "不是精确价格或日期预测。"
        ),
    }
