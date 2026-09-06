"""单一已确认锚点的 Price-Time 投影管线。"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.gann.confluence import build_confluence_zones
from app.gann.fan import build_fan, classify_state
from app.gann.models import GannAnchor, GannConfig, ScaleMode
from app.gann.pivots import confirmed_pivots
from app.gann.price_levels import build_price_levels
from app.gann.scale import build_scale
from app.gann.scenarios import build_scenarios, horizon_for_period
from app.gann.time_cycles import build_time_windows, future_bar_datetime


def project_gann(
    frame: pd.DataFrame,
    anchor: GannAnchor,
    period: str = "daily",
    horizontal_levels: dict[str, Any] | None = None,
    higher_timeframe: dict[str, Any] | None = None,
    config: GannConfig = GannConfig(),
    scale_mode: ScaleMode | None = None,
) -> dict[str, Any]:
    """从冻结锚点生成角线、时间窗、共振和条件情景。"""
    if frame.empty or anchor.pivot.confirmation_position >= len(frame):
        return {"status": "insufficient", "note": "锚点尚未完成右侧确认。"}
    main_horizon, hard_cap = horizon_for_period(period)
    scale = build_scale(anchor, config, scale_mode)
    fan = build_fan(frame, anchor, scale, main_horizon)
    latest_time = pd.Timestamp(frame["datetime"].iloc[-1])
    for item in fan:
        item["end_time"] = future_bar_datetime(latest_time, main_horizon, period).isoformat()
    pivots = confirmed_pivots(frame, config)
    levels = build_price_levels(frame, anchor, horizontal_levels)
    cycles, windows = build_time_windows(frame, anchor, pivots, hard_cap, period, config)
    zones = build_confluence_zones(frame, anchor, scale, levels, windows, higher_timeframe, config)
    state, state_label, relation = classify_state(frame, anchor, scale)
    scenarios = build_scenarios(anchor, scale, fan, levels, windows, zones, state, period, config)
    primary = scenarios[0]
    score_components = {
        "anchor_quality": round(anchor.score, 1),
        "angle_state": 85.0
        if state in {"STRONG_BULL", "STRONG_BEAR"}
        else 70.0
        if state in {"BULL", "BEAR"}
        else 50.0,
        "time_cycle": round(max((float(item["score"]) for item in windows), default=0.0), 1),
        "confluence": round(max((float(item["score"]) for item in zones), default=0.0), 1),
        "higher_timeframe": 80.0
        if higher_timeframe and higher_timeframe.get("direction") == anchor.direction
        else 50.0,
    }
    structural_fit = sum(score_components.values()) / len(score_components)
    return {
        "status": "active",
        "version": "3.0",
        "direction": anchor.direction,
        "anchor": anchor.as_dict(),
        "scale": scale.as_dict(),
        "fan_lines": fan,
        "price_levels": levels,
        "time_cycles": cycles,
        "time_windows": windows,
        "confluence_zones": zones,
        "resonance_zones": zones,
        "scenarios": scenarios,
        "confirmation": primary["trigger_price"],
        "confirmation_status": "conditional",
        "target_zone": primary["target_zones"][0],
        "invalidation": primary["invalidation_price"],
        "forecast_horizon": {
            "main_bars": main_horizon,
            "hard_cap_bars": hard_cap,
            "policy": "主预测只绘制有限角线；更远范围仅保留目标区与时间窗。",
        },
        "current_state": state,
        "current_state_label": state_label,
        "angle_relation": relation,
        "score_components": score_components,
        "structural_fit": round(structural_fit / 100, 3),
        "higher_timeframe": higher_timeframe or {},
        "snapshot_time": latest_time.isoformat(),
        "note": "角线是标准化动态支撑/阻力；情景置信度是未校准相对权重，不是上涨概率。",
    }


__all__ = ["project_gann"]
