"""带触发、确认、目标、时间窗和失效条件的江恩情景。"""

from __future__ import annotations

import math
from typing import Any

from app.gann.models import GannAnchor, GannConfig, GannScale, GannScenario


def horizon_for_period(period: str) -> tuple[int, int]:
    if period == "weekly":
        return 6, 16
    if period == "monthly":
        return 4, 12
    if period in {"1m", "5m", "15m", "30m", "60m"}:
        return 12, 24
    return 15, 30


def _softmax(values: list[float]) -> list[float]:
    maximum = max(values)
    weights = [math.exp((value - maximum) / 12) for value in values]
    total = sum(weights)
    return [weight / total for weight in weights]


def _decay(horizon: int) -> float:
    if horizon <= 5:
        return 1.0
    if horizon <= 10:
        return 0.85
    if horizon <= 15:
        return 0.65
    return 0.45


def build_scenarios(
    anchor: GannAnchor,
    scale: GannScale,
    fan: list[dict[str, Any]],
    price_levels: list[dict[str, Any]],
    time_windows: list[dict[str, Any]],
    confluence_zones: list[dict[str, Any]],
    state: str,
    period: str,
    config: GannConfig = GannConfig(),
) -> list[dict[str, Any]]:
    """生成突破 1×1 与拒绝 1×1 两个互斥条件情景。"""
    one = next(item for item in fan if item["label"] == "1×1")
    slow = next(item for item in fan if item["label"] == "1×2")
    one_price = float(one["current_price"])
    slow_price = float(slow["current_price"])
    sign = 1 if anchor.direction == "up" else -1
    primary_horizon, _hard_cap = horizon_for_period(period)
    zones = [[float(item["lower"]), float(item["upper"])] for item in confluence_zones[:2]]
    if not zones:
        directional = sorted(
            (
                float(item["price"])
                for item in price_levels
                if (float(item["price"]) - one_price) * sign > 0
            ),
            key=lambda price: abs(price - one_price),
        )
        target = directional[0] if directional else one_price + sign * anchor.atr * 2
        zones = [sorted([target - anchor.atr * 0.25, target + anchor.atr * 0.25])]
    selected_windows = time_windows[:2]
    continuation_score = (
        anchor.score * 0.45
        + (25 if state in {"STRONG_BULL", "BULL", "STRONG_BEAR", "BEAR"} else 12)
        + min(len(confluence_zones), 2) * 10
    )
    rejection_score = anchor.score * 0.35 + (25 if state == "NEUTRAL" else 15) + 15
    confidences = _softmax([continuation_score, rejection_score])
    favorable = "高于" if anchor.direction == "up" else "低于"
    adverse = "低于" if anchor.direction == "up" else "高于"
    opposite = "down" if anchor.direction == "up" else "up"
    scenario_data = [
        GannScenario(
            f"{anchor.lifecycle_id}:break",
            "突破并站稳 1×1",
            anchor.direction,
            round(continuation_score, 1),
            round(confidences[0], 4),
            round(confidences[0] * _decay(primary_horizon), 4),
            f"收盘{favorable}当前 1×1",
            one_price,
            f"连续 {config.scenario_confirmation_bars} 根 K 线收盘站在 1×1 有利侧",
            zones,
            selected_windows,
            f"收盘重新{adverse} 1×1，或穿越 1×2",
            slow_price,
            ["固定标准化角线", "已确认锚点", "时价共振目标区"],
        ),
        GannScenario(
            f"{anchor.lifecycle_id}:reject",
            "触及 1×1 后受阻",
            opposite,  # type: ignore[arg-type]
            round(rejection_score, 1),
            round(confidences[1], 4),
            round(confidences[1] * _decay(primary_horizon), 4),
            f"触及 1×1 后收盘仍在其{adverse}一侧",
            one_price,
            "触及与收盘拒绝发生在同一根或相邻两根 K 线",
            [sorted([slow_price - anchor.atr * 0.25, slow_price + anchor.atr * 0.25])],
            selected_windows,
            f"连续 {config.scenario_confirmation_bars} 根收盘{favorable} 1×1",
            one_price,
            ["1×1 动态阻力/支撑", "失败情景不等同于反向订单"],
        ),
    ]
    return [item.as_dict() for item in scenario_data]


__all__ = ["build_scenarios", "horizon_for_period"]
