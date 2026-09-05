from __future__ import annotations

import pandas as pd

from app.factors import build_factors
from app.indicators import add_indicators
from app.signals import create_signal, generate_signals


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


def test_repeated_triggers_are_deduplicated_within_setup_lifecycle(market_frame) -> None:
    enriched = add_indicators(market_frame)
    factors = build_factors(enriched)
    regimes = pd.Series("RANGE", index=enriched.index)
    columns = [
        name
        for setup in ("trend_pullback", "breakout", "support_reversal", "trend_breakdown")
        for name in (setup, f"{setup}_trigger")
    ]
    setups = pd.DataFrame(False, index=enriched.index, columns=columns)
    setups.loc[10:14, "support_reversal"] = True
    setups.loc[[11, 13], "support_reversal_trigger"] = True
    setups.loc[16:18, "support_reversal"] = True
    setups.loc[17, "support_reversal_trigger"] = True

    signals = generate_signals("600011", enriched, factors, regimes, setups)

    assert [signal.timestamp for signal in signals] == [
        pd.Timestamp(enriched.loc[11, "datetime"]).to_pydatetime(),
        pd.Timestamp(enriched.loc[17, "datetime"]).to_pydatetime(),
    ]


def test_signal_deduplication_does_not_change_past_when_future_is_appended(
    market_frame,
) -> None:
    enriched = add_indicators(market_frame)
    factors = build_factors(enriched)
    regimes = pd.Series("RANGE", index=enriched.index)
    columns = [
        name
        for setup in ("trend_pullback", "breakout", "support_reversal", "trend_breakdown")
        for name in (setup, f"{setup}_trigger")
    ]
    setups = pd.DataFrame(False, index=enriched.index, columns=columns)
    setups.loc[10:20, "support_reversal"] = True
    setups.loc[[11, 18], "support_reversal_trigger"] = True
    cutoff = 15

    prefix = generate_signals(
        "600011",
        enriched.iloc[:cutoff],
        factors.iloc[:cutoff],
        regimes.iloc[:cutoff],
        setups.iloc[:cutoff],
    )
    full = generate_signals("600011", enriched, factors, regimes, setups)

    assert [signal.timestamp for signal in prefix] == [
        signal.timestamp for signal in full if signal.timestamp <= prefix[-1].timestamp
    ]
