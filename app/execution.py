"""与策略判断解耦的订单和成交模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

from app.signals import TradingSignal


@dataclass(frozen=True, slots=True)
class ExecutionConfig:
    """可配置执行假设，费率均为单边。"""

    entry_price: Literal["next_open", "next_close"] = "next_open"
    commission_rate: float = 0.0003
    slippage_bps: float = 5.0
    t_plus_one: bool = True
    max_holding_bars: int = 20
    target_r_multiple: float = 2.0
    atr_stop_multiple: float = 2.0

    def __post_init__(self) -> None:
        if self.commission_rate < 0 or self.slippage_bps < 0:
            raise ValueError("手续费和滑点不能为负")
        if self.max_holding_bars < 1 or self.target_r_multiple <= 0:
            raise ValueError("持有周期与目标R必须为正数")


@dataclass(slots=True)
class Order:
    """由信号产生、等待下一根执行的订单。"""

    symbol: str
    signal_position: int
    side: Literal["buy", "sell"]
    setup: str


@dataclass(slots=True)
class Fill:
    """成交结果；未成交时 price 与 position 为空。"""

    filled: bool
    position: int | None = None
    price: float | None = None
    fee: float = 0.0
    reason: str | None = None
    warnings: list[str] = field(default_factory=list)


def order_from_signal(signal: TradingSignal, signal_position: int) -> Order:
    """把结构化信号转换为订单。"""
    return Order(
        symbol=signal.symbol,
        signal_position=signal_position,
        side="buy" if signal.direction == "long" else "sell",
        setup=signal.setup,
    )


def execute_order(order: Order, frame: pd.DataFrame, config: ExecutionConfig) -> Fill:
    """在信号后一根执行订单，处理缺失、停牌和价格不可用状态。"""
    position = order.signal_position + 1
    if position >= len(frame):
        return Fill(False, reason="NO_NEXT_BAR")
    bar = frame.iloc[position]
    price_column = "open" if config.entry_price == "next_open" else "close"
    raw_price = bar.get(price_column)
    if raw_price is None or not np.isfinite(float(raw_price)) or float(raw_price) <= 0:
        return Fill(False, reason="INVALID_PRICE")
    volume = bar.get("volume")
    if volume is not None and np.isfinite(float(volume)) and float(volume) <= 0:
        return Fill(False, reason="SUSPENDED_OR_NO_VOLUME")
    slippage = config.slippage_bps / 10_000
    price = float(raw_price) * (1 + slippage if order.side == "buy" else 1 - slippage)
    warning = "涨跌停可成交性未可靠识别，未伪造涨跌停成交规则。"
    return Fill(
        True,
        position=position,
        price=price,
        fee=price * config.commission_rate,
        warnings=[warning],
    )


def exit_price_with_cost(raw_price: float, config: ExecutionConfig) -> tuple[float, float]:
    """对卖出价应用不利滑点并返回单股手续费。"""
    price = raw_price * (1 - config.slippage_bps / 10_000)
    return price, price * config.commission_rate
