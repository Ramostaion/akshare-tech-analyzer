from __future__ import annotations

import pandas as pd
import pytest

from app.execution import ExecutionConfig, execute_order, order_from_signal
from app.factors import build_factors
from app.indicators import add_indicators
from app.signals import create_signal


def _signal_and_frame(market_frame, position: int = 100):
    enriched = add_indicators(market_frame)
    factors = build_factors(enriched)
    signal = create_signal("600011", enriched, factors, position, "breakout", "UPTREND")
    return signal, enriched


def test_order_executes_at_next_bar_open_with_cost_and_slippage(market_frame) -> None:
    signal, frame = _signal_and_frame(market_frame)
    config = ExecutionConfig(commission_rate=0.001, slippage_bps=10)
    order = order_from_signal(signal, 100)
    fill = execute_order(order, frame, config)

    assert fill.filled
    assert fill.position == 101
    assert fill.price == pytest.approx(frame["open"].iloc[101] * 1.001)
    assert fill.fee == pytest.approx(fill.price * 0.001)


def test_order_never_executes_on_signal_bar(market_frame) -> None:
    signal, frame = _signal_and_frame(market_frame)
    fill = execute_order(order_from_signal(signal, 100), frame, ExecutionConfig())

    assert pd.Timestamp(frame["datetime"].iloc[fill.position]) > pd.Timestamp(signal.timestamp)


def test_zero_volume_bar_is_not_fillable(market_frame) -> None:
    signal, frame = _signal_and_frame(market_frame)
    frame.loc[frame.index[101], "volume"] = 0
    fill = execute_order(order_from_signal(signal, 100), frame, ExecutionConfig())

    assert not fill.filled
    assert fill.reason == "SUSPENDED_OR_NO_VOLUME"
