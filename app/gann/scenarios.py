"""带触发、确认、目标、时间窗和失效条件的江恩情景。"""

from __future__ import annotations

import math
from typing import Any

from app.gann.confluence import horizon_decay
from app.gann.models import GannAnchor, GannConfig, GannScale, GannScenario


def horizon_for_period(period: str) -> tuple[int, int]:
    if period == "weekly":
        return 6, 8
    if period == "monthly":
        return 4, 8
    if period in {"1m", "5m", "15m", "30m", "60m"}:
        return 12, 20
    return 15, 20


def _softmax(values: list[float]) -> list[float]:
    maximum = max(values)
    weights = [math.exp((value - maximum) / 12) for value in values]
    total = sum(weights)
    return [weight / total for weight in weights]


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
    directional_confluence = [
        item
        for item in confluence_zones
        if (float(item["center"]) - one_price) * sign > 0
    ]
    ranked_confluence = [
        item for item in directional_confluence if float(item.get("score", 0)) >= 65
    ][:3]
    scenario_confluence = ranked_confluence or directional_confluence[:1]
    zones = [
        [float(item["price_low"]), float(item["price_high"])]
        for item in scenario_confluence[:2]
    ]
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
    selected_windows = [
        item for item in time_windows if bool(item.get("default_visible"))
    ][:2]
    if not selected_windows:
        selected_windows = sorted(
            time_windows, key=lambda item: float(item.get("score", 0)), reverse=True
        )[:1]
    scenario_horizon = primary_horizon
    confluence_bonus = max(
        (float(item.get("score", 0)) for item in ranked_confluence), default=0.0
    ) * 0.2
    continuation_score = (
        anchor.score * 0.45
        + (25 if state in {"STRONG_BULL", "BULL", "STRONG_BEAR", "BEAR"} else 12)
        + confluence_bonus
    )
    rejection_score = anchor.score * 0.35 + (25 if state == "NEUTRAL" else 15) + 15
    confidences = _softmax([continuation_score, rejection_score])
    favorable = "高于" if anchor.direction == "up" else "低于"
    adverse = "低于" if anchor.direction == "up" else "高于"
    opposite = "down" if anchor.direction == "up" else "up"
    confluence_condition = (
        f"共振区 {zones[0][0]:.3f}~{zones[0][1]:.3f}"
        if scenario_confluence
        else "候选价格区"
    )
    scenario_data = [
        GannScenario(
            f"{anchor.lifecycle_id}:break",
            "突破并站稳 1×1",
            anchor.direction,
            round(continuation_score, 1),
            round(confidences[0], 4),
            round(confidences[0] * horizon_decay(scenario_horizon), 4),
            f"收盘{favorable}当前 1×1，并突破{confluence_condition}",
            one_price,
            (
                f"连续 {config.scenario_confirmation_bars} 根 K 线站稳 1×1，"
                f"并确认{confluence_condition}突破"
            ),
            zones,
            selected_windows,
            f"收盘重新{adverse} 1×1，或穿越 1×2",
            slow_price,
            [
                "固定标准化角线",
                "已确认锚点",
                *(
                    [f"高分共振区 {ranked_confluence[0]['score']} 分"]
                    if ranked_confluence
                    else ["当前没有 65 分以上共振区"]
                ),
            ],
        ),
        GannScenario(
            f"{anchor.lifecycle_id}:reject",
            "触及 1×1 后受阻",
            opposite,  # type: ignore[arg-type]
            round(rejection_score, 1),
            round(confidences[1], 4),
            round(confidences[1] * horizon_decay(scenario_horizon), 4),
            f"触及 1×1 或{confluence_condition}后收盘转弱",
            one_price,
            "触及与收盘拒绝发生在同一根或相邻两根 K 线",
            [sorted([slow_price - anchor.atr * 0.25, slow_price + anchor.atr * 0.25])],
            selected_windows,
            f"连续 {config.scenario_confirmation_bars} 根收盘{favorable} 1×1",
            one_price,
            [
                "1×1 动态阻力/支撑",
                "高分共振区拒绝",
                "失败情景不等同于反向订单",
            ],
        ),
    ]
    return [item.as_dict() for item in scenario_data]


__all__ = ["build_scenarios", "horizon_for_period"]
