"""把严格 Trigger 转换为每次分析都可读的当前决策状态。"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.signals import TradingSignal

SETUP_LABELS = {
    "trend_pullback": "趋势回踩",
    "breakout": "突破蓄势",
    "support_reversal": "支撑反转",
    "trend_breakdown": "趋势破位",
}


def _finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def resolve_current_signal(
    signals: list[TradingSignal],
) -> tuple[TradingSignal | None, bool]:
    """同向信号取规则分最高者，方向冲突时拒绝给出可执行信号。"""
    if not signals:
        return None, False
    if len({signal.direction for signal in signals}) > 1:
        return None, True
    return max(signals, key=lambda signal: signal.score), False


def _latest_levels(
    frame: pd.DataFrame,
    factors: pd.DataFrame,
) -> dict[str, float | None]:
    close = float(frame["close"].iloc[-1])
    atr = _finite(frame["ATR14"].iloc[-1]) if "ATR14" in frame else None
    previous_high = _finite(frame["high"].iloc[-2]) if len(frame) >= 2 else None
    prior_high_20 = (
        _finite(frame["high"].iloc[-21:-1].max()) if len(frame) >= 21 else None
    )
    prior_low_20 = _finite(frame["low"].iloc[-21:-1].min()) if len(frame) >= 21 else None
    ma20 = _finite(frame["MA20"].iloc[-1]) if "MA20" in frame else None
    support = None
    if atr is not None and atr > 0 and not factors.empty:
        distance = _finite(factors["distance_to_support_atr"].iloc[-1])
        if distance is not None and distance >= 0:
            support = close - distance * atr
    return {
        "close": close,
        "atr": atr,
        "previous_high": previous_high,
        "prior_high_20": prior_high_20,
        "prior_low_20": prior_low_20,
        "ma20": ma20,
        "support": support,
    }


def _watch_conditions(
    setup_names: list[str],
    levels: dict[str, float | None],
) -> tuple[list[str], list[str], float | None, float | None]:
    triggers: list[str] = []
    invalidations: list[str] = []
    trigger_prices: list[float] = []
    invalidation_prices: list[float] = []
    for setup in setup_names:
        if setup == "trend_pullback":
            triggers.append("收盘站上上一根 K 线高点")
            if levels["previous_high"] is not None:
                trigger_prices.append(levels["previous_high"])
            invalidations.append("回踩结构或上升趋势条件不再成立")
        elif setup == "breakout":
            triggers.append("收盘突破此前 20 根高点，且量能与 MACD 动能同时确认")
            if levels["prior_high_20"] is not None:
                trigger_prices.append(levels["prior_high_20"])
            invalidations.append("波动收缩或突破准备结构消失")
        elif setup == "support_reversal":
            triggers.append("支撑附近收阳并收盘站上上一根 K 线高点")
            if levels["previous_high"] is not None:
                trigger_prices.append(levels["previous_high"])
            invalidations.append("收盘有效跌破当前支撑观察位")
            if levels["support"] is not None:
                invalidation_prices.append(levels["support"])
        elif setup == "trend_breakdown":
            triggers.append("收盘跌破此前 20 根低点，或上探 MA20 后重新收于其下")
            candidates = [levels["prior_low_20"], levels["ma20"]]
            trigger_prices.extend(value for value in candidates if value is not None)
            invalidations.append("价格重新站稳 MA20 且趋势破坏条件解除")
    trigger_price = trigger_prices[0] if len(set(trigger_prices)) == 1 else None
    invalidation_price = (
        invalidation_prices[0] if len(set(invalidation_prices)) == 1 else None
    )
    return triggers, invalidations, trigger_price, invalidation_price


def build_current_decision(
    frame: pd.DataFrame,
    factors: pd.DataFrame,
    setup_items: list[dict[str, object]],
    current_signals: list[TradingSignal],
    selected_signal: TradingSignal | None,
    *,
    conflict: bool,
) -> dict[str, Any]:
    """生成状态结论；未触发时只给条件计划，不伪造执行价格。"""
    levels = _latest_levels(frame, factors)
    setup_names = [str(item["setup"]) for item in setup_items]
    setup_text = "、".join(SETUP_LABELS.get(name, name) for name in setup_names)
    base: dict[str, Any] = {
        "is_executable": False,
        "selected_setup": selected_signal.setup if selected_signal else None,
        "trigger_condition": None,
        "invalidation_condition": None,
        "trigger_price": None,
        "invalidation_price": None,
        "validity_note": "条件只按最新一根已收盘 K 线判断。",
    }
    if conflict:
        directions = {signal.direction for signal in current_signals}
        return base | {
            "status": "conflict",
            "headline": "信号冲突，暂缓执行",
            "summary": "同一根 K 线同时出现做多与退出 Trigger，系统不自动选择方向。",
            "flat_action": "空仓：不入场，等待下一根收盘解除冲突。",
            "holding_action": "持仓：优先控制风险，并人工复核趋势破位条件。",
            "validity_note": (
                f"检测到 {len(current_signals)} 个 Trigger，方向包括 {sorted(directions)}。"
            ),
        }
    if selected_signal is not None and selected_signal.direction == "long":
        return base | {
            "status": "long_trigger",
            "headline": "做多 Trigger 已收盘确认",
            "summary": "严格规则已满足；这仍是确认事件，不是已成交记录。",
            "flat_action": "空仓：仅考虑下一根 K 线在计划区间内执行，跳空超出则放弃追价。",
            "holding_action": "持仓：继续按失效位管理，不因同一 Setup 重复加仓。",
            "is_executable": True,
            "validity_note": "默认仅对下一根 K 线有效；未按计划成交则重新分析。",
        }
    if selected_signal is not None:
        return base | {
            "status": "exit_trigger",
            "headline": "退出 Trigger 已收盘确认",
            "summary": "趋势结构已满足破位规则，该信号只用于管理已有多头。",
            "flat_action": "空仓：不操作，不将退出信号解释为做空建议。",
            "holding_action": "持仓：按下一根 K 线执行规则考虑退出或降低风险。",
            "is_executable": True,
            "validity_note": "退出优先于新增做多；下一根 K 线前需关注跳空风险。",
        }
    if any(bool(item.get("triggered")) for item in setup_items):
        return base | {
            "status": "active_after_trigger",
            "headline": "同一交易结构仍活跃，不重复入场",
            "summary": "本根再次满足 Trigger，但该 Setup 生命周期此前已经确认过一次。",
            "flat_action": "空仓：本次不追认旧信号，等待结构失效后出现新的首次 Trigger。",
            "holding_action": "持仓：继续管理原信号，不因重复 Trigger 自动加仓。",
            "trigger_condition": "等待当前 Setup 先失效，再观察新的首次收盘 Trigger",
            "invalidation_condition": "当前 Setup 条件不再成立时结束本轮信号生命周期",
            "validity_note": "图表、当前结论和回测统一采用每个 Setup 生命周期首次触发口径。",
        }
    if setup_names:
        triggers, invalidations, trigger_price, invalidation_price = _watch_conditions(
            setup_names, levels
        )
        return base | {
            "status": "watch",
            "headline": "交易结构观察中，尚未触发",
            "summary": f"当前识别到{setup_text}；只有收盘确认后才生成执行计划。",
            "flat_action": "空仓：继续等待，不提前买入，也不追逐盘中短暂突破。",
            "holding_action": "持仓：维持原有风控，触发退出条件时优先处理风险。",
            "trigger_condition": "；".join(triggers),
            "invalidation_condition": "；".join(invalidations),
            "trigger_price": trigger_price,
            "invalidation_price": invalidation_price,
        }
    return base | {
        "status": "no_setup",
        "headline": "暂无可执行交易结构",
        "summary": "最新收盘未形成四类 Setup；当前结论是等待，而不是缺少分析结果。",
        "flat_action": "空仓：暂不入场，等待新的结构与收盘 Trigger。",
        "holding_action": "持仓：依据既有止损和最近支撑管理，不新增仓位。",
        "invalidation_condition": "出现新的 Setup 后重新评估；已有仓位仍按原计划止损。",
    }
