from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal, assert_series_equal

from app.indicators import (
    add_indicators,
    atr,
    bollinger_bands,
    ema,
    kdj,
    macd,
    obv,
    rsi,
    sma,
    true_range,
)


def test_sma_and_ema_deterministic_values() -> None:
    values = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    expected_sma = pd.Series([np.nan, np.nan, 2.0, 3.0, 4.0])
    assert_series_equal(sma(values, 3), expected_sma)
    result_ema = ema(values, 3)
    assert result_ema.iloc[:2].isna().all()
    assert result_ema.iloc[2] == 2.25
    assert result_ema.iloc[-1] == 4.0625


def test_macd_formula_and_columns() -> None:
    close = pd.Series(np.arange(1, 80, dtype=float))
    result = macd(close)
    assert list(result.columns) == ["DIF", "DEA", "MACD"]
    assert len(result) == len(close)
    valid = result.dropna().iloc[-1]
    assert np.isclose(valid["MACD"], 2 * (valid["DIF"] - valid["DEA"]))


def test_rsi_handles_rising_and_flat_series() -> None:
    rising = pd.Series(np.arange(1, 40, dtype=float))
    flat = pd.Series(np.ones(40))
    assert rsi(rising, 6).iloc[:6].isna().all()
    assert rsi(rising, 6).iloc[-1] == 100
    assert rsi(flat, 6).iloc[-1] == 50


def test_kdj_zero_range_is_neutral() -> None:
    values = pd.Series(np.full(20, 10.0))
    result = kdj(values, values, values)
    assert list(result.columns) == ["K", "D", "J"]
    assert result.iloc[:8].isna().all().all()
    assert np.allclose(result.dropna().to_numpy(), 50.0)


def test_bollinger_uses_sample_standard_deviation() -> None:
    close = pd.Series(np.arange(1, 21, dtype=float))
    result = bollinger_bands(close)
    expected_std = close.std(ddof=1)
    assert result["BOLL_MID"].iloc[-1] == 10.5
    assert np.isclose(result["BOLL_UPPER"].iloc[-1], 10.5 + 2 * expected_std)
    assert np.isclose(result["BOLL_LOWER"].iloc[-1], 10.5 - 2 * expected_std)


def test_true_range_atr_and_obv_edges() -> None:
    high = pd.Series([11.0, 13.0, 12.0, 14.0])
    low = pd.Series([9.0, 10.0, 8.0, 12.0])
    close = pd.Series([10.0, 12.0, 9.0, 13.0])
    volume = pd.Series([100.0, 200.0, 300.0, 400.0])
    assert_series_equal(true_range(high, low, close), pd.Series([2.0, 3.0, 4.0, 5.0]))
    assert atr(high, low, close, 3).iloc[:2].isna().all()
    assert_series_equal(obv(close, volume), pd.Series([0.0, 200.0, -100.0, 300.0]))


def test_add_indicators_columns_lengths_and_no_future_data(market_frame: pd.DataFrame) -> None:
    complete = add_indicators(market_frame)
    expected = {
        "MA5",
        "MA10",
        "MA20",
        "MA60",
        "MA120",
        "MA250",
        "EMA12",
        "EMA26",
        "DIF",
        "DEA",
        "MACD",
        "RSI6",
        "RSI12",
        "RSI24",
        "K",
        "D",
        "J",
        "BOLL_MID",
        "BOLL_UPPER",
        "BOLL_LOWER",
        "ATR14",
        "ATR_PCT",
        "VOL_MA5",
        "VOL_MA10",
        "VOL_RATIO",
        "OBV",
    }
    assert expected.issubset(complete.columns)
    assert len(complete) == len(market_frame)
    prefix = add_indicators(market_frame.iloc[:100])
    assert_frame_equal(
        complete.iloc[:100][sorted(expected)].reset_index(drop=True),
        prefix[sorted(expected)].reset_index(drop=True),
    )


@pytest.mark.parametrize(
    ("function", "arguments"),
    [
        (sma, (pd.Series([1.0]), 0)),
        (ema, (pd.Series([1.0]), -1)),
        (rsi, (pd.Series([1.0]), 0)),
        (atr, (pd.Series([1.0]), pd.Series([1.0]), pd.Series([1.0]), 0)),
        (kdj, (pd.Series([1.0]), pd.Series([1.0]), pd.Series([1.0]), 0)),
    ],
)
def test_invalid_indicator_periods_raise_value_error(function, arguments) -> None:
    with pytest.raises(ValueError):
        function(*arguments)


def test_add_indicators_requires_ohlcv() -> None:
    with pytest.raises(ValueError, match="缺少指标计算列"):
        add_indicators(pd.DataFrame({"close": [1.0]}))
