"""交易记录绩效统计。"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np


def _distribution(values: np.ndarray) -> dict[str, float | None]:
    if values.size == 0:
        return {"median": None, "p25": None, "p75": None}
    return {
        "median": round(float(np.median(values)), 4),
        "p25": round(float(np.quantile(values, 0.25)), 4),
        "p75": round(float(np.quantile(values, 0.75)), 4),
    }


def calculate_metrics(trades: Iterable[Any]) -> dict[str, Any]:
    """计算以交易为单位的收益、R、回撤、期望与 MFE/MAE 分布。"""
    records = list(trades)
    if not records:
        return {
            "trade_count": 0,
            "win_rate": None,
            "average_win_r": None,
            "average_loss_r": None,
            "expectancy_r": None,
            "profit_factor": None,
            "average_holding_bars": None,
            "max_drawdown": None,
            "cumulative_return": None,
            "annualized_return": None,
            "sharpe": None,
            "mfe_distribution": _distribution(np.array([])),
            "mae_distribution": _distribution(np.array([])),
        }
    returns = np.array([float(item.return_pct) for item in records], dtype=float)
    r_values = np.array([float(item.r_multiple) for item in records], dtype=float)
    holding = np.array([int(item.holding_bars) for item in records], dtype=float)
    wins = r_values[r_values > 0]
    losses = r_values[r_values < 0]
    win_rate = float(np.mean(r_values > 0))
    average_win = float(np.mean(wins)) if wins.size else None
    average_loss = float(abs(np.mean(losses))) if losses.size else None
    expectancy = win_rate * (average_win or 0) - (1 - win_rate) * (average_loss or 0)
    gross_profit = float(wins.sum())
    gross_loss = float(abs(losses.sum()))
    equity = np.cumprod(1 + returns)
    peaks = np.maximum.accumulate(np.r_[1.0, equity])
    drawdown = np.r_[1.0, equity] / peaks - 1
    cumulative = float(equity[-1] - 1)
    total_bars = max(float(holding.sum()), 1.0)
    annualized = float((1 + cumulative) ** (252 / total_bars) - 1) if cumulative > -1 else -1.0
    std = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.0
    bars_per_trade = max(float(np.mean(holding)), 1.0)
    sharpe = float(np.mean(returns) / std * np.sqrt(252 / bars_per_trade)) if std > 0 else None
    return {
        "trade_count": len(records),
        "win_rate": round(win_rate * 100, 2),
        "average_win_r": round(average_win, 4) if average_win is not None else None,
        "average_loss_r": round(average_loss, 4) if average_loss is not None else None,
        "expectancy_r": round(expectancy, 4),
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else None,
        "average_holding_bars": round(float(np.mean(holding)), 2),
        "max_drawdown": round(float(np.min(drawdown)) * 100, 3),
        "cumulative_return": round(cumulative * 100, 3),
        "annualized_return": round(annualized * 100, 3),
        "sharpe": round(sharpe, 4) if sharpe is not None else None,
        "mfe_distribution": _distribution(
            np.array([float(item.mfe_r) for item in records], dtype=float)
        ),
        "mae_distribution": _distribution(
            np.array([float(item.mae_r) for item in records], dtype=float)
        ),
    }


def metrics_by_regime(trades: Iterable[Any]) -> dict[str, dict[str, Any]]:
    """按市场状态分组，始终包含 All。"""
    records = list(trades)
    result = {"ALL": calculate_metrics(records)}
    for regime in sorted({item.regime for item in records}):
        result[str(regime)] = calculate_metrics(item for item in records if item.regime == regime)
    return result
