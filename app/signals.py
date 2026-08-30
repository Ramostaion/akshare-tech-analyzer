"""结构化交易信号与规则质量评分。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from app.factors import factor_snapshot


class TradingSignal(BaseModel):
    """收盘后确认的可审计交易事件；不是上涨概率。"""

    symbol: str
    timestamp: datetime
    direction: Literal["long", "exit"]
    setup: str
    regime: str
    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    entry_reference: float | None = None
    entry_zone_lower: float | None = None
    entry_zone_upper: float | None = None
    stop_price: float | None = None
    target_1: float | None = None
    target_2: float | None = None
    risk_per_share: float | None = None
    reward_risk_ratio: float | None = None
    evidence: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    factors: dict[str, float | None] = Field(default_factory=dict)
    score_type: Literal["RULE_SCORE"] = "RULE_SCORE"
    historical_probability: float | None = None


def _finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _quality_score(setup: str, row: pd.Series, regime: str, reward_risk: float) -> float:
    """合成规则质量分；该分数明确不表示概率。"""
    score = 45.0
    if (setup == "trend_pullback" and regime == "UPTREND") or (
        setup == "support_reversal" and regime in {"RANGE", "UPTREND"}
    ):
        score += 15
    if setup == "breakout" and regime in {"UPTREND", "LOW_VOLATILITY"}:
        score += 15
    if setup == "trend_breakdown" and regime in {"DOWNTREND", "HIGH_VOLATILITY"}:
        score += 15
    support_distance = _finite(row.get("distance_to_support_atr"))
    if support_distance is not None and 0 <= support_distance <= 0.75:
        score += 8
    volume = _finite(row.get("volume_ratio_20"))
    if volume is not None and volume >= (1.2 if setup == "breakout" else 0.8):
        score += 8
    momentum = _finite(row.get("macd_hist_delta_3"))
    if momentum is not None and ((setup == "trend_breakdown" and momentum < 0) or momentum > 0):
        score += 8
    score += min(12.0, max(-8.0, (reward_risk - 1.0) * 6))
    return round(float(np.clip(score, 0, 100)), 1)


def create_signal(
    symbol: str,
    frame: pd.DataFrame,
    factors: pd.DataFrame,
    position: int,
    setup: str,
    regime: str,
) -> TradingSignal:
    """从已触发 Setup 创建信号，成交仍由 Execution 层在下一根处理。"""
    bar = frame.iloc[position]
    factor_row = factors.iloc[position]
    close = float(bar["close"])
    atr = _finite(bar.get("ATR14"))
    direction: Literal["long", "exit"] = "exit" if setup == "trend_breakdown" else "long"
    warnings = ["信号按收盘确认，默认最早在下一交易日开盘执行。"]
    stop = target_1 = target_2 = risk = reward_risk = None
    entry_zone_lower = entry_zone_upper = None
    evidence = [f"{setup} 已满足确定性触发条件", f"市场状态={regime}"]
    if direction == "long" and atr is not None and atr > 0:
        distance = _finite(factor_row.get("distance_to_support_atr"))
        support = close - distance * atr if distance is not None and distance >= 0 else None
        stop = (support - 0.25 * atr) if support is not None else close - 2 * atr
        if setup == "breakout":
            entry_zone_lower = close - 0.1 * atr
            entry_zone_upper = close + 0.15 * atr
        else:
            entry_zone_lower = max(support or -np.inf, close - 0.25 * atr)
            entry_zone_upper = close + 0.1 * atr
        risk = close - stop
        if risk > 0:
            target_1 = close + 1.5 * risk
            resistance_distance = _finite(factor_row.get("distance_to_resistance_atr"))
            resistance = (
                close + resistance_distance * atr
                if resistance_distance is not None and resistance_distance > 0
                else None
            )
            target_2 = max(close + 2 * risk, resistance or -np.inf)
            reward_risk = (target_1 - close) / risk
    elif direction == "exit":
        evidence.append("趋势结构破坏，信号仅用于退出已有多头")
    else:
        warnings.append("ATR不可用，无法生成可靠止损与目标位。")
    score = _quality_score(setup, factor_row, regime, reward_risk or 0)
    timestamp = pd.Timestamp(bar["datetime"]).to_pydatetime()
    return TradingSignal(
        symbol=symbol,
        timestamp=timestamp,
        direction=direction,
        setup=setup,
        regime=regime,
        score=score,
        confidence=round(score / 100, 3),
        entry_reference=round(close, 6),
        entry_zone_lower=(round(entry_zone_lower, 6) if entry_zone_lower is not None else None),
        entry_zone_upper=(round(entry_zone_upper, 6) if entry_zone_upper is not None else None),
        stop_price=round(stop, 6) if stop is not None else None,
        target_1=round(target_1, 6) if target_1 is not None else None,
        target_2=round(target_2, 6) if target_2 is not None else None,
        risk_per_share=round(risk, 6) if risk is not None else None,
        reward_risk_ratio=round(reward_risk, 3) if reward_risk is not None else None,
        evidence=evidence,
        warnings=warnings,
        factors=factor_snapshot(factors, position),
    )


def generate_signals(
    symbol: str,
    frame: pd.DataFrame,
    factors: pd.DataFrame,
    regimes: pd.Series,
    setups: pd.DataFrame,
) -> list[TradingSignal]:
    """将所有 Trigger 行转换为统一 TradingSignal 列表。"""
    signals: list[TradingSignal] = []
    for position in range(len(frame)):
        for setup in ("trend_pullback", "breakout", "support_reversal", "trend_breakdown"):
            if bool(setups[f"{setup}_trigger"].iloc[position]):
                signals.append(
                    create_signal(
                        symbol, frame, factors, position, setup, str(regimes.iloc[position])
                    )
                )
    return signals
