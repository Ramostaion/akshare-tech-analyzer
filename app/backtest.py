"""只使用当时及更早数据的单标的技术信号回测。"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _metrics(returns: pd.Series) -> dict[str, Any]:
    clean = returns.replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        return {
            "samples": 0,
            "win_rate": None,
            "average_return": None,
            "median_return": None,
            "payoff_ratio": None,
        }
    wins = clean[clean > 0]
    losses = clean[clean < 0]
    payoff = None
    if not wins.empty and not losses.empty and losses.mean() != 0:
        payoff = float(wins.mean() / abs(losses.mean()))
    return {
        "samples": len(clean),
        "win_rate": round(float((clean > 0).mean() * 100), 2),
        "average_return": round(float(clean.mean() * 100), 3),
        "median_return": round(float(clean.median() * 100), 3),
        "payoff_ratio": round(payoff, 3) if payoff is not None else None,
    }


def run_signal_backtest(
    frame: pd.DataFrame,
    horizons: tuple[int, ...] = (5, 10, 20),
    round_trip_cost: float = 0.001,
) -> dict[str, Any]:
    """回测均线排列过滤后的 MACD 交叉，信号在当根收盘确认。"""
    required = {"datetime", "close", "MA20", "MA60", "DIF", "DEA"}
    if len(frame) < 80 or not required.issubset(frame.columns):
        return {
            "status": "数据不足",
            "method": "MA20/MA60趋势过滤 + MACD收盘确认交叉",
            "cost_rate": round_trip_cost * 100,
            "signals": 0,
            "results": {},
            "note": "至少需要80根K线才能生成具有趋势过滤的回测结果。",
        }

    previous_dif = frame["DIF"].shift(1)
    previous_dea = frame["DEA"].shift(1)
    bullish = (
        (frame["close"] > frame["MA20"])
        & (frame["MA20"] > frame["MA60"])
        & (previous_dif <= previous_dea)
        & (frame["DIF"] > frame["DEA"])
    )
    bearish = (
        (frame["close"] < frame["MA20"])
        & (frame["MA20"] < frame["MA60"])
        & (previous_dif >= previous_dea)
        & (frame["DIF"] < frame["DEA"])
    )
    direction = pd.Series(0.0, index=frame.index)
    direction.loc[bullish] = 1.0
    direction.loc[bearish] = -1.0
    signal_count = int((direction != 0).sum())
    results: dict[str, Any] = {}
    for horizon in horizons:
        raw_return = frame["close"].shift(-horizon) / frame["close"] - 1
        strategy_return = raw_return * direction - round_trip_cost
        selected = strategy_return[direction != 0]
        side_results = {
            "all": _metrics(selected),
            "bullish": _metrics(strategy_return[bullish]),
            "bearish": _metrics(strategy_return[bearish]),
        }
        results[str(horizon)] = side_results

    equity_returns = (
        (frame["close"].shift(-10) / frame["close"] - 1) * direction - round_trip_cost
    )[direction != 0].dropna()
    equity = (1 + equity_returns).cumprod()
    drawdown = equity / equity.cummax() - 1 if not equity.empty else pd.Series(dtype=float)
    benchmark = frame["close"].iloc[-1] / frame["close"].iloc[0] - 1
    return {
        "status": "可用" if signal_count else "无信号",
        "method": "MA20/MA60趋势过滤 + MACD收盘确认交叉",
        "cost_rate": round(round_trip_cost * 100, 3),
        "signals": signal_count,
        "bullish_signals": int(bullish.sum()),
        "bearish_signals": int(bearish.sum()),
        "results": results,
        "ten_bar_max_drawdown": (
            round(float(drawdown.min() * 100), 3) if not drawdown.empty else None
        ),
        "benchmark_return": round(float(benchmark * 100), 3),
        "note": "信号按当根收盘确认，收益从该收盘价计算；结果未使用未来数据。",
    }
