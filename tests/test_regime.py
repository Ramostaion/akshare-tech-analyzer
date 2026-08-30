from __future__ import annotations

from app.factors import build_factors
from app.indicators import add_indicators
from app.regime import REGIMES, classify_regime, regime_series


def test_regime_has_deterministic_contract(market_frame) -> None:
    enriched = add_indicators(market_frame)
    factors = build_factors(enriched)
    result = classify_regime(enriched, factors)

    assert result["regime"] in REGIMES
    assert 0 <= result["confidence"] <= 1
    assert result["evidence"]


def test_regime_series_does_not_look_ahead(market_frame) -> None:
    enriched = add_indicators(market_frame)
    factors = build_factors(enriched)
    cutoff = 180
    prefix = regime_series(enriched.iloc[:cutoff], factors.iloc[:cutoff])
    complete = regime_series(enriched, factors)

    assert prefix.iloc[-1] == complete.iloc[cutoff - 1]


def test_regime_reports_insufficient_data(market_frame) -> None:
    enriched = add_indicators(market_frame.iloc[:30])
    result = classify_regime(enriched, build_factors(enriched))

    assert result["regime"] == "INSUFFICIENT_DATA"
