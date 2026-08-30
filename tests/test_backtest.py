from __future__ import annotations

import json

import numpy as np
import pandas as pd

from app.analysis import analyze_technical_state
from app.backtest import evaluate_triple_barrier, run_signal_backtest, run_strategy_backtest
from app.execution import ExecutionConfig
from app.indicators import add_indicators
from app.signals import TradingSignal


def _oscillating_trend(size: int = 320) -> pd.DataFrame:
    position = np.arange(size)
    close = 100 + position * 0.03 + np.sin(position / 4) * 2
    open_price = close + np.sin(position / 3) * 0.2
    return add_indicators(
        pd.DataFrame(
            {
                "datetime": pd.date_range("2024-01-01", periods=size),
                "open": open_price,
                "high": np.maximum(open_price, close) + 0.5,
                "low": np.minimum(open_price, close) - 0.5,
                "close": close,
                "volume": 100_000.0,
            }
        )
    )


def test_backtest_reports_confirmed_signals_and_costs() -> None:
    result = run_signal_backtest(_oscillating_trend())

    assert result["status"] == "可用"
    assert result["signals"] > 0
    assert result["cost_rate"] == 0.1
    assert set(result["results"]) == {"5", "10", "20"}
    assert result["results"]["10"]["all"]["samples"] > 0
    assert "未使用未来数据" in result["note"]


def test_backtest_does_not_emit_unfinished_forward_samples() -> None:
    frame = _oscillating_trend(120)
    result = run_signal_backtest(frame, horizons=(20,))
    metric = result["results"]["20"]["all"]

    assert metric["samples"] <= result["signals"]


def test_market_regime_has_auditable_dynamic_weights() -> None:
    analysis = analyze_technical_state(_oscillating_trend())
    regime = analysis["market_regime"]

    assert regime["label"] in {"上升趋势", "区间震荡", "高波动", "低波动蓄势"}
    assert sum(regime["weights"].values()) == 1
    assert regime["rationale"]
    assert analysis["latest"]["ADX14"] is not None


def test_triple_barrier_checks_first_touch_in_bar_order() -> None:
    frame = pd.DataFrame(
        {
            "high": [100, 101, 103, 106],
            "low": [99, 98, 97, 104],
            "close": [100, 99, 102, 105],
        }
    )
    result = evaluate_triple_barrier(frame, 0, 100, 98, 104, t_plus_one=True)

    assert result.label == "LOSS"
    assert result.exit_position == 1
    assert result.exit_reason == "STOP"


def test_same_bar_stop_and_target_uses_conservative_stop() -> None:
    frame = pd.DataFrame({"high": [100, 106], "low": [99, 97], "close": [100, 103]})
    result = evaluate_triple_barrier(frame, 0, 100, 98, 105, t_plus_one=True)

    assert result.label == "LOSS"
    assert result.exit_reason == "STOP_AND_TARGET_SAME_BAR_CONSERVATIVE"


def test_t_plus_one_skips_entry_bar_barriers() -> None:
    frame = pd.DataFrame({"high": [106, 101], "low": [97, 99], "close": [100, 100]})
    result = evaluate_triple_barrier(
        frame, 0, 100, 98, 105, max_holding_bars=1, t_plus_one=True
    )

    assert result.label == "TIMEOUT"
    assert result.exit_position == 1


def test_scheduled_breakdown_exits_at_next_open_before_intraday_barriers() -> None:
    frame = pd.DataFrame(
        {"open": [100, 99], "high": [100, 106], "low": [99, 97], "close": [100, 103]}
    )
    result = evaluate_triple_barrier(
        frame,
        0,
        100,
        98,
        105,
        t_plus_one=True,
        scheduled_exit_positions={1},
    )

    assert result.exit_reason == "TREND_BREAKDOWN"
    assert result.raw_exit_price == 99


def test_completed_trade_result_is_json_serializable() -> None:
    frame = pd.DataFrame(
        {
            "datetime": pd.date_range("2024-01-01", periods=4),
            "open": [100.0, 100.0, 102.0, 104.0],
            "high": [101.0, 102.0, 105.0, 106.0],
            "low": [99.0, 99.0, 101.0, 103.0],
            "close": [100.0, 101.0, 104.0, 105.0],
            "volume": [1000.0] * 4,
            "ATR14": [2.0] * 4,
        }
    )
    signal = TradingSignal(
        symbol="600011",
        timestamp=frame["datetime"].iloc[0].to_pydatetime(),
        direction="long",
        setup="breakout",
        regime="UPTREND",
        score=70,
        confidence=0.7,
        entry_reference=100,
        stop_price=98,
        target_1=103,
        target_2=104,
        risk_per_share=2,
        reward_risk_ratio=1.5,
    )

    result = run_strategy_backtest(
        frame,
        [signal],
        ExecutionConfig(
            commission_rate=0,
            slippage_bps=0,
            t_plus_one=True,
            target_r_multiple=2,
        ),
    )

    assert result["metrics"]["trade_count"] == 1
    assert result["trades"][0]["signal_date"] == "2024-01-01T00:00:00"
    json.dumps(result)
