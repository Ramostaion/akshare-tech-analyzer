from __future__ import annotations

from app.decision import build_current_decision, resolve_current_signal
from app.factors import build_factors
from app.indicators import add_indicators
from app.signals import create_signal


def test_no_setup_still_returns_explicit_waiting_plan(market_frame) -> None:
    enriched = add_indicators(market_frame)
    factors = build_factors(enriched)

    decision = build_current_decision(
        enriched, factors, [], [], None, conflict=False
    )

    assert decision["status"] == "no_setup"
    assert "等待" in decision["summary"]
    assert decision["flat_action"].startswith("空仓：")
    assert decision["holding_action"].startswith("持仓：")
    assert decision["is_executable"] is False


def test_pending_setup_returns_condition_plan_without_execution_prices(market_frame) -> None:
    enriched = add_indicators(market_frame)
    factors = build_factors(enriched)

    decision = build_current_decision(
        enriched,
        factors,
        [{"setup": "support_reversal", "triggered": False}],
        [],
        None,
        conflict=False,
    )

    assert decision["status"] == "watch"
    assert "收盘站上上一根" in decision["trigger_condition"]
    assert decision["trigger_price"] == enriched["high"].iloc[-2]
    assert decision["is_executable"] is False


def test_opposite_current_signals_are_reported_as_conflict(market_frame) -> None:
    enriched = add_indicators(market_frame)
    factors = build_factors(enriched)
    position = len(enriched) - 1
    long_signal = create_signal(
        "600011", enriched, factors, position, "support_reversal", "RANGE"
    )
    exit_signal = create_signal(
        "600011", enriched, factors, position, "trend_breakdown", "DOWNTREND"
    )

    selected, conflict = resolve_current_signal([long_signal, exit_signal])
    decision = build_current_decision(
        enriched,
        factors,
        [
            {"setup": "support_reversal", "triggered": True},
            {"setup": "trend_breakdown", "triggered": True},
        ],
        [long_signal, exit_signal],
        selected,
        conflict=conflict,
    )

    assert selected is None
    assert conflict is True
    assert decision["status"] == "conflict"
    assert decision["is_executable"] is False


def test_repeated_trigger_becomes_position_management_state(market_frame) -> None:
    enriched = add_indicators(market_frame)
    factors = build_factors(enriched)

    decision = build_current_decision(
        enriched,
        factors,
        [{"setup": "support_reversal", "triggered": True}],
        [],
        None,
        conflict=False,
    )

    assert decision["status"] == "active_after_trigger"
    assert "不重复入场" in decision["headline"]
    assert "不因重复 Trigger 自动加仓" in decision["holding_action"]
