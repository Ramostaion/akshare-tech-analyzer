from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.metrics import calculate_metrics, metrics_by_regime


def _trade(r_value: float, regime: str = "UPTREND") -> SimpleNamespace:
    return SimpleNamespace(
        return_pct=r_value * 0.02,
        r_multiple=r_value,
        holding_bars=5,
        mfe_r=max(r_value, 0) + 0.5,
        mae_r=0.4 if r_value > 0 else 1.0,
        regime=regime,
    )


def test_metrics_calculate_expectancy_not_only_win_rate() -> None:
    metrics = calculate_metrics([_trade(2), _trade(1), _trade(-1), _trade(-1)])

    assert metrics["win_rate"] == 50
    assert metrics["average_win_r"] == 1.5
    assert metrics["average_loss_r"] == 1
    assert metrics["expectancy_r"] == pytest.approx(0.25)
    assert metrics["profit_factor"] == 1.5


def test_metrics_group_by_regime() -> None:
    grouped = metrics_by_regime([_trade(2, "UPTREND"), _trade(-1, "RANGE")])

    assert grouped["ALL"]["trade_count"] == 2
    assert grouped["UPTREND"]["trade_count"] == 1
    assert grouped["RANGE"]["trade_count"] == 1
