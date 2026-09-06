"""江恩八分价格、Fibonacci 与已有水平位的统一价格因子。"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.gann.models import GannAnchor, GannConfig

EIGHTHS = tuple(index / 8 for index in range(1, 9))
FIBONACCI = (0.382, 0.5, 0.618, 1.0)


def build_price_levels(
    frame: pd.DataFrame,
    anchor: GannAnchor,
    horizontal_levels: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """围绕已确认摆幅生成价格因子；水平位必须由调用方的因果算法提供。"""
    low = min(anchor.pivot.price, anchor.previous_pivot.price)
    high = max(anchor.pivot.price, anchor.previous_pivot.price)
    span = high - low
    levels = [
        {
            "source": "gann_eighth",
            "fraction": fraction,
            "label": f"{int(fraction * 8)}/8",
            "price": round(low + span * fraction, 6),
            "weight": 15.0 if fraction == 0.5 else 10.0,
        }
        for fraction in EIGHTHS
    ]
    levels.extend(
        {
            "source": "fibonacci",
            "fraction": fraction,
            "label": f"Fib {fraction:g}",
            "price": round(
                anchor.pivot.price + (1 if anchor.direction == "up" else -1) * span * fraction,
                6,
            ),
            "weight": 15.0,
        }
        for fraction in FIBONACCI
    )
    levels.append(
        {
            "source": "prior_pivot",
            "label": "前一已确认高低点",
            "price": round(anchor.previous_pivot.price, 6),
            "weight": 15.0,
        }
    )
    if horizontal_levels:
        for group, label in (("supports", "水平支撑"), ("resistances", "水平阻力")):
            for item in horizontal_levels.get(group, []):
                levels.append(
                    {
                        "source": "horizontal_sr",
                        "label": label,
                        "price": round(float(item["price"]), 6),
                        "weight": 15.0,
                        "quality": item.get("confidence"),
                    }
                )
    latest = frame.iloc[-1]
    for column, label in (
        ("MA20", "MA20"),
        ("MA60", "MA60"),
        ("BOLL_UPPER", "BOLL上轨"),
        ("BOLL_LOWER", "BOLL下轨"),
    ):
        value = latest.get(column)
        if pd.notna(value):
            levels.append(
                {
                    "source": "indicator",
                    "label": label,
                    "price": round(float(value), 6),
                    "weight": 10.0,
                }
            )
    return levels


def cluster_price_levels(
    levels: list[dict[str, Any]],
    anchor: GannAnchor,
    config: GannConfig = GannConfig(),
) -> list[dict[str, Any]]:
    """把相距不超过固定锚点 ATR 阈值的价格因子合并成价格区。"""
    if not levels:
        return []
    tolerance = max(anchor.atr * config.price_cluster_tolerance_atr, anchor.pivot.price * 0.0005)
    groups: list[list[dict[str, Any]]] = []
    for level in sorted(levels, key=lambda item: float(item["price"])):
        if not groups or float(level["price"]) - float(groups[-1][-1]["price"]) > tolerance:
            groups.append([level])
        else:
            groups[-1].append(level)
    zones: list[dict[str, Any]] = []
    for group in groups:
        prices = [float(item["price"]) for item in group]
        source_count = len({str(item["source"]) for item in group})
        raw_strength = sum(float(item.get("weight", 10.0)) for item in group)
        strength = min(100.0, 20.0 + raw_strength * 0.7 + source_count * 8.0)
        zones.append(
            {
                "price_low": round(min(prices) - tolerance * 0.15, 6),
                "price_high": round(max(prices) + tolerance * 0.15, 6),
                "center": round(sum(prices) / len(prices), 6),
                "strength": round(strength, 1),
                "factor_count": len(group),
                "sources": sorted({str(item["source"]) for item in group}),
                "labels": [str(item["label"]) for item in group],
                "members": group,
            }
        )
    ranked = sorted(zones, key=lambda item: (-float(item["strength"]), -int(item["factor_count"])))
    for rank, zone in enumerate(ranked, start=1):
        zone["rank"] = rank
        zone["default_visible"] = rank <= config.visible_price_zones
    return ranked


__all__ = ["EIGHTHS", "FIBONACCI", "build_price_levels", "cluster_price_levels"]
