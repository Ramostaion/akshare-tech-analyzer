"""基于 price unit / bar 的江恩角度族与状态机。"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from app.gann.models import GannAnchor, GannScale

ANGLE_FAMILY = (
    ("8×1", 8.0),
    ("4×1", 4.0),
    ("2×1", 2.0),
    ("1×1", 1.0),
    ("1×2", 0.5),
    ("1×4", 0.25),
    ("1×8", 0.125),
)
DEFAULT_ANGLES = {"2×1", "1×1", "1×2"}


def angle_price(anchor: GannAnchor, scale: GannScale, ratio: float, position: int) -> float:
    elapsed = max(0, position - anchor.pivot.position)
    sign = 1.0 if anchor.direction == "up" else -1.0
    if scale.mode == "log":
        return math.exp(math.log(anchor.pivot.price) + sign * scale.price_unit * ratio * elapsed)
    return anchor.pivot.price + sign * scale.price_unit * ratio * elapsed


def build_fan(
    frame: pd.DataFrame, anchor: GannAnchor, scale: GannScale, horizon: int
) -> list[dict[str, Any]]:
    latest = len(frame) - 1
    return [
        {
            "label": label,
            "ratio": ratio,
            "start_position": anchor.pivot.position,
            "start_time": anchor.pivot.timestamp.isoformat(),
            "start_price": round(anchor.pivot.price, 6),
            "current_position": latest,
            "current_time": pd.Timestamp(frame["datetime"].iloc[-1]).isoformat(),
            "current_price": round(angle_price(anchor, scale, ratio, latest), 6),
            "end_position": latest + horizon,
            "end_price": round(angle_price(anchor, scale, ratio, latest + horizon), 6),
            "default_visible": label in DEFAULT_ANGLES,
            "role": "动态支撑/阻力",
        }
        for label, ratio in ANGLE_FAMILY
    ]


def classify_state(
    frame: pd.DataFrame, anchor: GannAnchor, scale: GannScale
) -> tuple[str, str, dict[str, str]]:
    latest = len(frame) - 1
    close = float(frame["close"].iloc[-1])
    values = {label: angle_price(anchor, scale, ratio, latest) for label, ratio in ANGLE_FAMILY}
    sign = 1 if anchor.direction == "up" else -1

    def favorable(level: float) -> float:
        return (close - level) * sign

    if favorable(values["2×1"]) >= 0:
        state, label = "STRONG_BULL", "强上行：价格位于 2×1 有利侧"
    elif favorable(values["1×1"]) >= 0:
        state, label = "BULL", "上行：价格位于 1×1 有利侧"
    elif favorable(values["1×2"]) >= 0:
        state, label = "NEUTRAL", "中性：价格处于 1×1 与 1×2 之间"
    else:
        state, label = "BEAR", "结构转弱：价格已越过 1×2 不利侧"
    if anchor.direction == "down":
        state = {"STRONG_BULL": "STRONG_BEAR", "BULL": "BEAR", "BEAR": "BULL"}.get(state, state)
        label = label.replace("上行", "下行")
    relation = {
        key: "有利侧" if favorable(value) >= 0 else "不利侧"
        for key, value in values.items()
        if key in DEFAULT_ANGLES
    }
    return state, label, relation


__all__ = ["ANGLE_FAMILY", "DEFAULT_ANGLES", "angle_price", "build_fan", "classify_state"]
