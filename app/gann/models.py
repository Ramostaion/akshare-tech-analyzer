"""江恩 Price-Time 引擎的领域模型与默认参数。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import pandas as pd

Direction = Literal["up", "down"]
PivotKind = Literal["high", "low"]
ScaleMode = Literal["atr", "percent", "log"]


@dataclass(frozen=True, slots=True)
class GannConfig:
    """可在 walk-forward 中校准的江恩参数。"""

    pivot_window: int = 3
    pivot_atr_factor: float = 1.0
    pivot_percent_threshold: float = 0.01
    atr_multiplier: float = 0.25
    percent_unit: float = 0.005
    scale_mode: ScaleMode = "atr"
    cycle_lookback: int = 7
    window_tolerance: float = 0.10
    scenario_confirmation_bars: int = 2
    confluence_tolerance_atr: float = 0.35
    minimum_anchor_score: float = 35.0


@dataclass(frozen=True, slots=True)
class GannPivot:
    kind: PivotKind
    position: int
    confirmation_position: int
    timestamp: pd.Timestamp
    confirmed_at: pd.Timestamp
    price: float
    swing_size: float
    duration: int
    atr_at_confirmation: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "direction": self.kind,
            "position": self.position,
            "bar_index": self.position,
            "confirmation_position": self.confirmation_position,
            "timestamp": self.timestamp.isoformat(),
            "pivot_time": self.timestamp.isoformat(),
            "confirmed_at": self.confirmed_at.isoformat(),
            "price": round(self.price, 6),
            "swing_size": round(self.swing_size, 6),
            "duration": self.duration,
            "atr_at_confirmation": round(self.atr_at_confirmation, 6),
        }


@dataclass(frozen=True, slots=True)
class GannAnchor:
    direction: Direction
    pivot: GannPivot
    previous_pivot: GannPivot
    score: float
    score_components: dict[str, float]
    lifecycle_id: str
    reference_pivot: GannPivot | None = None

    @property
    def atr(self) -> float:
        return self.pivot.atr_at_confirmation

    @property
    def quality(self) -> float:
        return self.score / 100

    def as_dict(self) -> dict[str, Any]:
        result = self.pivot.as_dict()
        result.update(
            {
                "direction": self.direction,
                "previous_price": round(self.previous_pivot.price, 6),
                "atr": round(self.atr, 6),
                "score": round(self.score, 1),
                "quality": round(self.quality, 3),
                "score_components": self.score_components,
                "lifecycle_id": self.lifecycle_id,
                "promotion_reason": "newer_confirmed_atr_significant_pivot",
                "reference_anchor": self.reference_pivot.as_dict()
                if self.reference_pivot
                else None,
            }
        )
        return result


@dataclass(frozen=True, slots=True)
class GannScale:
    mode: ScaleMode
    price_unit: float
    atr: float
    atr_multiplier: float
    percent_unit: float
    method: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "price_unit": round(self.price_unit, 8),
            "unit_per_bar": round(self.price_unit, 8),
            "atr": round(self.atr, 8),
            "atr_multiplier": self.atr_multiplier,
            "percent_unit": self.percent_unit,
            "time_unit": "1 bar",
            "method": self.method,
        }


@dataclass(frozen=True, slots=True)
class GannScenario:
    scenario_id: str
    name: str
    direction: Direction
    raw_score: float
    confidence: float
    effective_confidence: float
    trigger: str
    trigger_price: float
    confirmation: str
    target_zones: list[list[float]]
    time_windows: list[dict[str, Any]]
    invalidation: str
    invalidation_price: float
    rationale: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for key in ("trigger_price", "invalidation_price"):
            result[key] = round(float(result[key]), 6)
        return result


__all__ = [
    "Direction",
    "GannAnchor",
    "GannConfig",
    "GannPivot",
    "GannScale",
    "GannScenario",
    "PivotKind",
    "ScaleMode",
]
