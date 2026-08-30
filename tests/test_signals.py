from __future__ import annotations

from app.factors import build_factors
from app.indicators import add_indicators
from app.signals import create_signal


def test_trading_signal_is_structured_and_rule_score_is_not_probability(market_frame) -> None:
    enriched = add_indicators(market_frame)
    factors = build_factors(enriched)
    signal = create_signal(
        "600011", enriched, factors, len(enriched) - 1, "trend_pullback", "UPTREND"
    )

    assert signal.direction == "long"
    assert signal.score_type == "RULE_SCORE"
    assert signal.historical_probability is None
    assert 0 <= signal.score <= 100
    assert signal.entry_zone_lower < signal.entry_reference < signal.entry_zone_upper
    assert "下一交易日" in signal.warnings[0]
    assert set(signal.factors) == set(factors.columns)


def test_breakdown_signal_is_exit_without_fabricated_target(market_frame) -> None:
    enriched = add_indicators(market_frame)
    factors = build_factors(enriched)
    signal = create_signal(
        "600011", enriched, factors, len(enriched) - 1, "trend_breakdown", "DOWNTREND"
    )

    assert signal.direction == "exit"
    assert signal.stop_price is None
    assert signal.target_1 is None
