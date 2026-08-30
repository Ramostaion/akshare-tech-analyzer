from __future__ import annotations

import pandas as pd

from app.factors import build_factors
from app.indicators import add_indicators
from app.setups import SETUP_NAMES, evaluate_setups


def test_setups_and_triggers_are_separate(market_frame) -> None:
    enriched = add_indicators(market_frame)
    factors = build_factors(enriched)
    regimes = pd.Series("UPTREND", index=enriched.index)
    setups = evaluate_setups(enriched, factors, regimes)

    for name in SETUP_NAMES:
        assert name in setups
        assert f"{name}_trigger" in setups
        assert setups[f"{name}_trigger"].dtype == bool


def test_breakout_trigger_uses_shifted_rolling_high(market_frame) -> None:
    frame = market_frame.iloc[:80].copy()
    prior_breakout = frame["high"].iloc[-22:-2].max()
    frame.loc[frame.index[-2], "close"] = prior_breakout - 0.02
    frame.loc[frame.index[-2], "high"] = prior_breakout
    frame.loc[frame.index[-2], "low"] = min(
        frame["low"].iloc[-2], frame["close"].iloc[-2] - 0.1
    )
    frame.loc[frame.index[-1], "close"] = frame["high"].iloc[-21:-1].max() + 1
    frame.loc[frame.index[-1], "high"] = frame["close"].iloc[-1] + 0.1
    frame.loc[frame.index[-1], "volume"] = frame["volume"].iloc[-21:-1].mean() * 3
    enriched = add_indicators(frame)
    factors = build_factors(enriched)
    factors.loc[factors.index[-2], "boll_width_percentile_250"] = 0.2
    factors.loc[factors.index[-1], "macd_hist_delta_3"] = 1.0
    regimes = pd.Series("UPTREND", index=enriched.index)

    setups = evaluate_setups(enriched, factors, regimes)

    assert bool(setups["breakout_trigger"].iloc[-1])


def test_appending_future_does_not_change_prior_trigger(market_frame) -> None:
    enriched = add_indicators(market_frame)
    factors = build_factors(enriched)
    regimes = pd.Series("RANGE", index=enriched.index)
    cutoff = 200
    prefix = evaluate_setups(
        enriched.iloc[:cutoff], factors.iloc[:cutoff], regimes.iloc[:cutoff]
    )
    complete = evaluate_setups(enriched, factors, regimes)

    pd.testing.assert_series_equal(prefix.iloc[-1], complete.iloc[cutoff - 1], check_names=False)
