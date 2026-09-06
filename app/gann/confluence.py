"""江恩价格与时间的多因子共振排名。"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.gann.fan import angle_price
from app.gann.models import GannAnchor, GannConfig, GannScale

FACTOR_WEIGHTS = {
    "gann_angle": 20.0,
    "time_window": 20.0,
    "gann_price_level": 15.0,
    "horizontal_sr": 15.0,
    "fibonacci": 10.0,
    "higher_timeframe": 10.0,
    "momentum": 5.0,
    "volume": 5.0,
}


def horizon_decay(bars_from_now: int) -> float:
    if bars_from_now <= 5:
        return 1.0
    if bars_from_now <= 10:
        return 0.85
    if bars_from_now <= 15:
        return 0.65
    return 0.45


def _zone_type(center: float, close: float) -> str:
    return "resistance" if center >= close else "support"


def build_confluence_zones(
    frame: pd.DataFrame,
    anchor: GannAnchor,
    scale: GannScale,
    price_levels: list[dict[str, Any]],
    time_windows: list[dict[str, Any]],
    higher_timeframe: dict[str, Any] | None = None,
    config: GannConfig = GannConfig(),
    price_zones: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """计算价格区 × 时间窗的共振分数，并保留完整因子解释。"""
    tolerance = max(anchor.atr * config.confluence_tolerance_atr, anchor.pivot.price * 0.001)
    close = float(frame["close"].iloc[-1])
    latest = frame.iloc[-1]
    momentum = float(latest.get("DIF", 0) or 0) - float(latest.get("DEA", 0) or 0)
    volume_ratio = float(latest.get("VOL_RATIO", 0) or 0)
    zones: list[dict[str, Any]] = []
    clustered = price_zones or [
        {
            "price_low": float(item["price"]),
            "price_high": float(item["price"]),
            "center": float(item["price"]),
            "members": [item],
            "strength": float(item.get("weight", 10)),
        }
        for item in price_levels
    ]
    for window in time_windows:
        position = int(window["center_position"])
        for angle, ratio in (("2×1", 2.0), ("1×1", 1.0), ("1×2", 0.5)):
            projected = angle_price(anchor, scale, ratio, position)
            nearby_zones = [
                item
                for item in clustered
                if float(item["price_low"]) - tolerance
                <= projected
                <= float(item["price_high"]) + tolerance
            ]
            if not nearby_zones:
                continue
            for price_zone in nearby_zones:
                members = list(price_zone.get("members", []))
                has_gann = any(
                    item.get("source") in {"gann_eighth", "prior_pivot"} for item in members
                )
                has_horizontal = any(item.get("source") == "horizontal_sr" for item in members)
                has_fib = any(item.get("source") == "fibonacci" for item in members)
                htf_aligned = bool(
                    higher_timeframe and higher_timeframe.get("direction") == anchor.direction
                )
                momentum_aligned = momentum * (1 if anchor.direction == "up" else -1) > 0
                factor_scores = {
                    "gann_angle": FACTOR_WEIGHTS["gann_angle"],
                    "time_window": FACTOR_WEIGHTS["time_window"]
                    * min(1.0, float(window.get("score", 0)) / 70),
                    "gann_price_level": FACTOR_WEIGHTS["gann_price_level"] if has_gann else 0.0,
                    "horizontal_sr": FACTOR_WEIGHTS["horizontal_sr"] if has_horizontal else 0.0,
                    "fibonacci": FACTOR_WEIGHTS["fibonacci"] if has_fib else 0.0,
                    "higher_timeframe": FACTOR_WEIGHTS["higher_timeframe"] if htf_aligned else 0.0,
                    "momentum": FACTOR_WEIGHTS["momentum"] if momentum_aligned else 0.0,
                    "volume": FACTOR_WEIGHTS["volume"] if volume_ratio >= 1 else 0.0,
                }
                raw_score = min(100.0, sum(factor_scores.values()))
                bars_from_now = int(
                    window.get("bars_from_now", position - (len(frame) - 1))
                )
                start_position = int(window.get("start_position", position))
                end_position = int(window.get("end_position", position))
                decay = horizon_decay(bars_from_now)
                effective_score = round(raw_score * decay, 1)
                center = (projected + float(price_zone["center"])) / 2
                factors = [f"Gann {angle}", f"Gann {window['label']}"]
                factors.extend(str(item.get("label", item.get("source"))) for item in members)
                if htf_aligned:
                    factors.append("周线江恩同向")
                if momentum_aligned:
                    factors.append("动量确认")
                if volume_ratio >= 1:
                    factors.append("量能确认")
                price_low = min(float(price_zone["price_low"]), center - tolerance * 0.3)
                price_high = max(float(price_zone["price_high"]), center + tolerance * 0.3)
                zones.append(
                    {
                        "price_low": round(price_low, 6),
                        "price_high": round(price_high, 6),
                        "lower": round(price_low, 6),
                        "upper": round(price_high, 6),
                        "center": round(center, 6),
                        "time_start_bar": start_position - (len(frame) - 1),
                        "time_end_bar": end_position - (len(frame) - 1),
                        "angle": angle,
                        "time_window": window,
                        "datetime": window["center_datetime"],
                        "raw_score": round(raw_score, 1),
                        "horizon_decay": decay,
                        "score": effective_score,
                        "type": _zone_type(center, close),
                        "support_or_resistance": _zone_type(center, close),
                        "factors": list(dict.fromkeys(factors)),
                        "sources": list(dict.fromkeys(factors)),
                        "dominant_factors": [
                            name for name, value in factor_scores.items() if value >= 10
                        ],
                        "factor_scores": factor_scores,
                        "confidence": (
                            "high"
                            if effective_score >= 80
                            else "medium"
                            if effective_score >= 65
                            else "low"
                        ),
                    }
                )
    ranked = sorted(
        zones,
        key=lambda item: (-float(item["score"]), int(item["time_window"]["center_position"])),
    )
    deduped: list[dict[str, Any]] = []
    for item in ranked:
        if any(
            abs(float(item["center"]) - float(existing["center"])) <= tolerance * 0.5
            and abs(int(item["time_start_bar"]) - int(existing["time_start_bar"])) <= 1
            for existing in deduped
        ):
            continue
        deduped.append(item)
    for rank, item in enumerate(deduped, start=1):
        item["rank"] = rank
        item["default_visible"] = (
            rank <= config.visible_confluence_zones and float(item["score"]) >= 65
        )
        item["visibility"] = (
            "highlight"
            if float(item["score"]) >= 80
            else "faded"
            if float(item["score"]) >= 65
            else "hidden"
        )
    return deduped


__all__ = ["FACTOR_WEIGHTS", "build_confluence_zones", "horizon_decay"]
