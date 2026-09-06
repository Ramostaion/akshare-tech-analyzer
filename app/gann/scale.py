"""与图表像素无关的江恩价格单位。"""

from __future__ import annotations

import math

from app.gann.models import GannAnchor, GannConfig, GannScale, ScaleMode


def build_scale(
    anchor: GannAnchor, config: GannConfig = GannConfig(), mode: ScaleMode | None = None
) -> GannScale:
    selected = mode or config.scale_mode
    if selected == "atr":
        unit = anchor.atr * config.atr_multiplier
        method = f"ATR(14) × {config.atr_multiplier:g} / bar"
    elif selected == "percent":
        unit = anchor.pivot.price * config.percent_unit
        method = f"锚点价格 × {config.percent_unit:.2%} / bar"
    elif selected == "log":
        unit = math.log1p(config.percent_unit)
        method = f"对数价格 {config.percent_unit:.2%} / bar"
    else:
        raise ValueError(f"不支持的江恩尺度: {selected}")
    if not math.isfinite(unit) or unit <= 0:
        raise ValueError("江恩价格单位必须为正数")
    return GannScale(selected, unit, anchor.atr, config.atr_multiplier, config.percent_unit, method)


__all__ = ["build_scale"]
