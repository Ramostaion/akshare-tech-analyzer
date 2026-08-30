"""只使用当时及更早数据的单标的技术信号回测。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from app.execution import (
    ExecutionConfig,
    execute_order,
    exit_price_with_cost,
    order_from_signal,
)
from app.metrics import calculate_metrics, metrics_by_regime
from app.signals import TradingSignal


@dataclass(slots=True)
class TradeRecord:
    """从信号到退出的完整单笔交易审计记录。"""

    symbol: str
    setup: str
    signal_date: datetime
    entry_date: datetime
    entry_price: float
    exit_date: datetime
    exit_price: float
    stop_price: float
    target_price: float
    regime: str
    features_at_entry: dict[str, float | None]
    exit_reason: str
    return_pct: float
    r_multiple: float
    mfe_r: float
    mae_r: float
    holding_bars: int


@dataclass(slots=True)
class BarrierResult:
    """Triple Barrier 的逐根判定结果。"""

    label: str
    exit_position: int
    raw_exit_price: float
    exit_reason: str
    mfe_r: float
    mae_r: float
    holding_bars: int


def evaluate_triple_barrier(
    frame: pd.DataFrame,
    entry_position: int,
    entry_price: float,
    stop_price: float,
    target_price: float,
    max_holding_bars: int = 20,
    t_plus_one: bool = True,
    scheduled_exit_positions: set[int] | None = None,
) -> BarrierResult | None:
    """逐 bar 判断上下与时间障碍。

    同一根 High/Low 同时触及目标和止损时保守判为止损；T+1 模式从入场后一根
    才允许退出。MFE/MAE 也只聚合实际持有且已经按顺序遍历的 K 线。
    """
    if not (0 <= entry_position < len(frame)) or stop_price >= entry_price:
        return None
    risk = entry_price - stop_price
    if target_price <= entry_price or risk <= 0:
        return None
    first = entry_position + 1 if t_plus_one else entry_position
    last = min(len(frame) - 1, entry_position + max_holding_bars)
    if first > last:
        return None
    highest = entry_price
    lowest = entry_price
    for position in range(first, last + 1):
        bar = frame.iloc[position]
        if scheduled_exit_positions and position in scheduled_exit_positions:
            raw_exit = float(bar["open"])
            favorable = max(raw_exit - entry_price, 0.0) / risk
            adverse = max(entry_price - raw_exit, 0.0) / risk
            return BarrierResult(
                "WIN" if raw_exit > entry_price else "LOSS",
                position,
                raw_exit,
                "TREND_BREAKDOWN",
                max((highest - entry_price) / risk, favorable),
                max((entry_price - lowest) / risk, adverse),
                position - entry_position,
            )
        high = float(bar["high"])
        low = float(bar["low"])
        highest = max(highest, high)
        lowest = min(lowest, low)
        hit_stop = low <= stop_price
        hit_target = high >= target_price
        holding = position - entry_position
        mfe = (highest - entry_price) / risk
        mae = (entry_price - lowest) / risk
        if hit_stop:
            reason = "STOP_AND_TARGET_SAME_BAR_CONSERVATIVE" if hit_target else "STOP"
            return BarrierResult("LOSS", position, stop_price, reason, mfe, mae, holding)
        if hit_target:
            return BarrierResult("WIN", position, target_price, "TARGET", mfe, mae, holding)
        if position == last:
            return BarrierResult(
                "TIMEOUT", position, float(bar["close"]), "TIME_BARRIER", mfe, mae, holding
            )
    return None


def _locate_signal(frame: pd.DataFrame, signal: TradingSignal) -> int | None:
    timestamps = pd.to_datetime(frame["datetime"])
    matches = np.flatnonzero(timestamps.eq(pd.Timestamp(signal.timestamp)).to_numpy())
    return int(matches[-1]) if len(matches) else None


def _trade_payload(trade: TradeRecord) -> dict[str, Any]:
    """将交易记录转换为可直接写入 JSON/SQLite 的字典。"""
    payload = asdict(trade)
    for field_name in ("signal_date", "entry_date", "exit_date"):
        payload[field_name] = getattr(trade, field_name).isoformat()
    return payload


def run_strategy_backtest(
    frame: pd.DataFrame,
    signals: list[TradingSignal],
    config: ExecutionConfig | None = None,
) -> dict[str, Any]:
    """执行 Long 信号、逐根管理 Triple Barrier 并生成统计。"""
    execution = config or ExecutionConfig()
    trades: list[TradeRecord] = []
    rejected: dict[str, int] = {}
    last_exit = -1
    scheduled_exits = {
        position + 1
        for signal in signals
        if signal.direction == "exit"
        and (position := _locate_signal(frame, signal)) is not None
        and position + 1 < len(frame)
    }
    for signal in signals:
        if signal.direction != "long":
            continue
        signal_position = _locate_signal(frame, signal)
        if signal_position is None or signal_position < last_exit:
            continue
        order = order_from_signal(signal, signal_position)
        fill = execute_order(order, frame, execution)
        if not fill.filled or fill.position is None or fill.price is None:
            reason = fill.reason or "UNFILLED"
            rejected[reason] = rejected.get(reason, 0) + 1
            continue
        atr = float(frame["ATR14"].iloc[fill.position])
        if not np.isfinite(atr) or atr <= 0:
            rejected["INVALID_ATR"] = rejected.get("INVALID_ATR", 0) + 1
            continue
        proposed_stop = signal.stop_price
        stop = (
            float(proposed_stop)
            if proposed_stop is not None and proposed_stop < fill.price
            else fill.price - execution.atr_stop_multiple * atr
        )
        risk = fill.price - stop
        target = fill.price + execution.target_r_multiple * risk
        barrier = evaluate_triple_barrier(
            frame,
            fill.position,
            fill.price,
            stop,
            target,
            execution.max_holding_bars,
            execution.t_plus_one or execution.entry_price == "next_close",
            scheduled_exits,
        )
        if barrier is None:
            rejected["NO_EXIT_BAR"] = rejected.get("NO_EXIT_BAR", 0) + 1
            continue
        exit_price, exit_fee = exit_price_with_cost(barrier.raw_exit_price, execution)
        net_profit = exit_price - fill.price - fill.fee - exit_fee
        record = TradeRecord(
            symbol=signal.symbol,
            setup=signal.setup,
            signal_date=signal.timestamp,
            entry_date=pd.Timestamp(frame["datetime"].iloc[fill.position]).to_pydatetime(),
            entry_price=round(fill.price, 6),
            exit_date=pd.Timestamp(frame["datetime"].iloc[barrier.exit_position]).to_pydatetime(),
            exit_price=round(exit_price, 6),
            stop_price=round(stop, 6),
            target_price=round(target, 6),
            regime=signal.regime,
            features_at_entry=signal.factors,
            exit_reason=barrier.exit_reason,
            return_pct=net_profit / fill.price,
            r_multiple=net_profit / risk,
            mfe_r=barrier.mfe_r,
            mae_r=barrier.mae_r,
            holding_bars=barrier.holding_bars,
        )
        trades.append(record)
        last_exit = barrier.exit_position
    return {
        "status": "可用" if trades else "无已完成交易",
        "method": "Setup触发→下一根执行→逐根Triple Barrier",
        "execution": {
            "entry_price": execution.entry_price,
            "commission_rate": execution.commission_rate,
            "slippage_bps": execution.slippage_bps,
            "t_plus_one": execution.t_plus_one,
            "same_bar_rule": "止损与目标同根触及时按止损处理",
        },
        "metrics": calculate_metrics(trades),
        "by_regime": metrics_by_regime(trades),
        "rejected": rejected,
        "trades": [_trade_payload(item) for item in trades],
    }


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
