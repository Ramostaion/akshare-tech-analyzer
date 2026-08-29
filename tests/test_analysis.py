from __future__ import annotations

import numpy as np
import pandas as pd

from app.analysis import analyze_technical_state
from app.indicators import add_indicators


def _trend_frame(direction: float) -> pd.DataFrame:
    size = 300
    close = 10 + direction * np.arange(size) * 0.03
    open_price = close - direction * 0.01
    frame = pd.DataFrame(
        {
            "datetime": pd.date_range("2024-01-01", periods=size),
            "open": open_price,
            "high": np.maximum(open_price, close) + 0.08,
            "low": np.minimum(open_price, close) - 0.08,
            "close": close,
            "volume": np.full(size, 100_000.0),
            "amount": close * 10_000_000,
            "amplitude": np.nan,
            "pct_change": pd.Series(close).pct_change() * 100,
            "change": pd.Series(close).diff(),
            "turnover": 1.0,
        }
    )
    return add_indicators(frame)


def test_bullish_and_bearish_state_are_deterministic() -> None:
    bullish = analyze_technical_state(_trend_frame(1))
    bearish = analyze_technical_state(_trend_frame(-1))
    assert bullish["score"] > 50
    assert bullish["state"] in {"震荡偏强", "偏强趋势"}
    assert bearish["score"] < 50
    assert bearish["state"] in {"震荡偏弱", "偏弱趋势"}
    assert bullish["components"]["trend"]["reasons"]
    assert bullish["evidence"]["bullish"]


def test_scores_are_clipped_and_components_are_explained() -> None:
    result = analyze_technical_state(_trend_frame(1))
    assert 0 <= result["score"] <= 100
    assert set(result["components"]) == {"trend", "momentum", "volume", "risk"}
    assert all(0 <= value["score"] <= 100 for value in result["components"].values())
    assert all("reasons" in value for value in result["components"].values())


def test_insufficient_data_state() -> None:
    result = analyze_technical_state(_trend_frame(1).head(10))
    assert result["state"] == "数据不足"
    assert any("少于20根" in warning for warning in result["warning"])
