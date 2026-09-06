"""价格因素与时间窗口的共振区评分。"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.gann.fan import angle_price
from app.gann.models import GannAnchor, GannConfig, GannScale


def build_confluence_zones(
    frame: pd.DataFrame,
    anchor: GannAnchor,
    scale: GannScale,
    price_levels: list[dict[str, Any]],
    time_windows: list[dict[str, Any]],
    higher_timeframe: dict[str, Any] | None = None,
    config: GannConfig = GannConfig(),
) -> list[dict[str, Any]]:
    """只有角线、价格因子和时间窗同时存在时才生成共振区。"""
    tolerance = max(anchor.atr * config.confluence_tolerance_atr, anchor.pivot.price * 0.001)
    zones: list[dict[str, Any]] = []
    for window in time_windows:
        position = int(window["center_position"])
        for angle, ratio in (("2×1", 2.0), ("1×1", 1.0), ("1×2", 0.5)):
            projected = angle_price(anchor, scale, ratio, position)
            nearby = [
                item for item in price_levels if abs(float(item["price"]) - projected) <= tolerance
            ]
            if not nearby:
                continue
            center = (projected + sum(float(item["price"]) for item in nearby)) / (len(nearby) + 1)
            sources = [
                f"Gann {angle}",
                f"时间窗 {window['label']}",
                *[str(item["label"]) for item in nearby],
            ]
            horizontal = any(item["source"] == "horizontal_sr" for item in nearby)
            fibonacci = any(item["source"] == "fibonacci" for item in nearby)
            indicator = any(item["source"] == "indicator" for item in nearby)
            score = 20 + 20 + (15 if horizontal else 0) + (15 if fibonacci else 0)
            score += 10 if indicator else 0
            if higher_timeframe and higher_timeframe.get("direction") == anchor.direction:
                score += 10
                sources.append("高周期方向同向")
            latest = frame.iloc[-1]
            momentum = float(latest.get("DIF", 0) or 0) - float(latest.get("DEA", 0) or 0)
            if momentum * (1 if anchor.direction == "up" else -1) > 0:
                score += 10
                sources.append("动量确认")
            volume_ratio = float(latest.get("VOL_RATIO", 0) or 0)
            if volume_ratio >= 1:
                score += 10
                sources.append("量能确认")
            zones.append(
                {
                    "lower": round(center - tolerance, 6),
                    "upper": round(center + tolerance, 6),
                    "center": round(center, 6),
                    "angle": angle,
                    "time_window": window,
                    "datetime": window["center_datetime"],
                    "score": min(100.0, round(score, 1)),
                    "sources": sources,
                }
            )
    return sorted(
        zones, key=lambda item: (-float(item["score"]), int(item["time_window"]["center_position"]))
    )[:5]


__all__ = ["build_confluence_zones"]
