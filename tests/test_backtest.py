from __future__ import annotations

import numpy as np
import pandas as pd

from app.analysis import analyze_technical_state
from app.backtest import run_signal_backtest
from app.indicators import add_indicators


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
