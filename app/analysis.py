"""确定性、可解释的技术状态规则系统。"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _finite(value: Any) -> bool:
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False


def _latest(frame: pd.DataFrame, column: str) -> float | None:
    if column not in frame or not _finite(frame[column].iloc[-1]):
        return None
    return float(frame[column].iloc[-1])


def _component(name: str) -> dict[str, Any]:
    return {"name": name, "score": 50.0, "reasons": []}


def _adjust(
    component: dict[str, Any],
    points: float,
    reason: str,
    evidence: dict[str, list[str]],
) -> None:
    component["score"] += points
    component["reasons"].append({"points": points, "reason": reason})
    if points > 0:
        evidence["bullish"].append(reason)
    elif points < 0:
        evidence["bearish"].append(reason)
    else:
        evidence["neutral"].append(reason)


def _slope(values: pd.Series, count: int = 5) -> float | None:
    clean = values.dropna().tail(count)
    if len(clean) < count or clean.iloc[0] == 0:
        return None
    return float((clean.iloc[-1] - clean.iloc[0]) / abs(clean.iloc[0]) * 100)


def _price_structure(frame: pd.DataFrame) -> int:
    """最近20根前后半区间高低点结构：1抬高，-1降低，0混合。"""
    recent = frame.tail(20)
    if len(recent) < 20:
        return 0
    first, second = recent.iloc[:10], recent.iloc[10:]
    higher_high = second["high"].max() > first["high"].max()
    higher_low = second["low"].min() > first["low"].min()
    lower_high = second["high"].max() < first["high"].max()
    lower_low = second["low"].min() < first["low"].min()
    if higher_high and higher_low:
        return 1
    if lower_high and lower_low:
        return -1
    return 0


def _confirmed_divergence(frame: pd.DataFrame) -> str | None:
    """仅在30根内两个已确认三根摆动点与 RSI12 同时反向时确认背离。"""
    if "RSI12" not in frame or len(frame) < 20:
        return None
    recent = frame.tail(30).reset_index(drop=True)
    low_positions: list[int] = []
    high_positions: list[int] = []
    for position in range(3, len(recent) - 3):
        lows = recent["low"].iloc[position - 3 : position + 4]
        highs = recent["high"].iloc[position - 3 : position + 4]
        if recent["low"].iloc[position] == lows.min() and lows.eq(lows.min()).sum() == 1:
            low_positions.append(position)
        if recent["high"].iloc[position] == highs.max() and highs.eq(highs.max()).sum() == 1:
            high_positions.append(position)
    if len(low_positions) >= 2:
        first, second = low_positions[-2:]
        first_rsi, second_rsi = recent["RSI12"].iloc[[first, second]]
        if (
            pd.notna(first_rsi)
            and pd.notna(second_rsi)
            and recent["low"].iloc[second] < recent["low"].iloc[first] * 0.995
            and second_rsi > first_rsi + 3
        ):
            return "bullish"
    if len(high_positions) >= 2:
        first, second = high_positions[-2:]
        first_rsi, second_rsi = recent["RSI12"].iloc[[first, second]]
        if (
            pd.notna(first_rsi)
            and pd.notna(second_rsi)
            and recent["high"].iloc[second] > recent["high"].iloc[first] * 1.005
            and second_rsi < first_rsi - 3
        ):
            return "bearish"
    return None


def _market_regime(frame: pd.DataFrame) -> dict[str, Any]:
    """依据趋势强度和自身波动率分位识别当前市场状态。"""
    adx_value = _latest(frame, "ADX14")
    atr_value = _latest(frame, "ATR_PCT")
    atr_history = frame.get("ATR_PCT", pd.Series(dtype=float)).dropna().tail(120)
    atr_percentile = None
    if atr_value is not None and not atr_history.empty:
        atr_percentile = float((atr_history <= atr_value).mean() * 100)
    ma20_slope = _slope(frame["MA20"], 5) if "MA20" in frame else None
    close = _latest(frame, "close")
    ma60 = _latest(frame, "MA60")

    key = "range"
    label = "区间震荡"
    rationale = "趋势强度有限，动量指标权重提高。"
    weights = {"trend": 0.25, "momentum": 0.40, "volume": 0.15, "risk": 0.20}
    if atr_percentile is not None and atr_percentile >= 80:
        key, label = "high_volatility", "高波动"
        rationale = "ATR%处于近120根K线高分位，风险权重提高。"
        weights = {"trend": 0.30, "momentum": 0.20, "volume": 0.10, "risk": 0.40}
    elif (
        atr_percentile is not None
        and atr_percentile <= 20
        and (adx_value is None or adx_value < 22)
    ):
        key, label = "low_volatility", "低波动蓄势"
        rationale = "波动率处于低分位且趋势尚未增强，量能确认权重提高。"
        weights = {"trend": 0.25, "momentum": 0.30, "volume": 0.25, "risk": 0.20}
    elif (
        adx_value is not None
        and adx_value >= 23
        and ma20_slope is not None
        and close is not None
        and ma60 is not None
    ):
        if ma20_slope > 0 and close > ma60:
            key, label = "uptrend", "上升趋势"
            rationale = "ADX确认趋势强度，价格位于MA60上方且MA20斜率向上。"
        elif ma20_slope < 0 and close < ma60:
            key, label = "downtrend", "下降趋势"
            rationale = "ADX确认趋势强度，价格位于MA60下方且MA20斜率向下。"
        if key in {"uptrend", "downtrend"}:
            weights = {"trend": 0.50, "momentum": 0.25, "volume": 0.10, "risk": 0.15}

    return {
        "key": key,
        "label": label,
        "adx14": round(adx_value, 2) if adx_value is not None else None,
        "atr_percentile": round(atr_percentile, 1) if atr_percentile is not None else None,
        "rationale": rationale,
        "weights": weights,
    }


def analyze_technical_state(frame: pd.DataFrame) -> dict[str, Any]:
    """综合趋势、动量、量能和波动风险，输出0至100的结构化评分。"""
    if frame.empty or "close" not in frame:
        return {
            "state": "数据不足",
            "score": 50,
            "evidence": {"bullish": [], "bearish": [], "neutral": ["没有可分析的行情"]},
            "warning": ["数据不足，无法形成技术状态判断。"],
            "components": {},
            "summary": "数据不足，暂不形成技术结论。",
            "latest": {},
            "market_regime": {
                "key": "insufficient",
                "label": "数据不足",
                "rationale": "没有足够行情识别市场状态。",
                "weights": {},
            },
        }

    evidence: dict[str, list[str]] = {"bullish": [], "bearish": [], "neutral": []}
    warnings: list[str] = []
    components = {
        "trend": _component("趋势"),
        "momentum": _component("动量"),
        "volume": _component("量能"),
        "risk": _component("波动/风险"),
    }
    close = float(frame["close"].iloc[-1])

    for moving_average, points in (("MA20", 7), ("MA60", 7), ("MA120", 5)):
        value = _latest(frame, moving_average)
        if value is None:
            components["trend"]["reasons"].append(
                {"points": 0, "reason": f"{moving_average} 样本不足，未计分"}
            )
        elif close > value:
            _adjust(components["trend"], points, f"收盘价位于{moving_average}上方", evidence)
        elif close < value:
            _adjust(components["trend"], -points, f"收盘价位于{moving_average}下方", evidence)

    ma20, ma60, ma120 = (_latest(frame, column) for column in ("MA20", "MA60", "MA120"))
    if all(value is not None for value in (ma20, ma60, ma120)):
        if ma20 > ma60 > ma120:
            _adjust(components["trend"], 8, "MA20、MA60、MA120 呈多头排列", evidence)
        elif ma20 < ma60 < ma120:
            _adjust(components["trend"], -8, "MA20、MA60、MA120 呈空头排列", evidence)

    for moving_average in ("MA20", "MA60"):
        if moving_average in frame and (slope := _slope(frame[moving_average])) is not None:
            if slope > 0.3:
                _adjust(
                    components["trend"], 4, f"{moving_average}近5根斜率向上({slope:.2f}%)", evidence
                )
            elif slope < -0.3:
                _adjust(
                    components["trend"],
                    -4,
                    f"{moving_average}近5根斜率向下({slope:.2f}%)",
                    evidence,
                )

    structure = _price_structure(frame)
    if structure > 0:
        _adjust(components["trend"], 6, "最近20根K线高点与低点同步抬高", evidence)
    elif structure < 0:
        _adjust(components["trend"], -6, "最近20根K线高点与低点同步降低", evidence)
    else:
        evidence["neutral"].append("最近20根K线高低点结构混合")

    dif, dea, histogram = (_latest(frame, column) for column in ("DIF", "DEA", "MACD"))
    if dif is not None and dea is not None:
        if dif > 0:
            _adjust(components["momentum"], 6, "MACD DIF位于零轴上方", evidence)
        elif dif < 0:
            _adjust(components["momentum"], -6, "MACD DIF位于零轴下方", evidence)
        if dif > dea:
            _adjust(components["momentum"], 7, "MACD处于金叉状态(DIF>DEA)", evidence)
        elif dif < dea:
            _adjust(components["momentum"], -7, "MACD处于死叉状态(DIF<DEA)", evidence)
        if len(frame) >= 2 and {"DIF", "DEA"}.issubset(frame.columns):
            previous = frame.iloc[-2]
            if previous["DIF"] <= previous["DEA"] and dif > dea:
                _adjust(components["momentum"], 5, "最新一根出现MACD金叉", evidence)
            elif previous["DIF"] >= previous["DEA"] and dif < dea:
                _adjust(components["momentum"], -5, "最新一根出现MACD死叉", evidence)
    if histogram is not None and "MACD" in frame and frame["MACD"].tail(3).notna().all():
        recent_histogram = frame["MACD"].tail(3)
        if recent_histogram.is_monotonic_increasing:
            _adjust(components["momentum"], 4, "MACD柱连续3根增强", evidence)
        elif recent_histogram.is_monotonic_decreasing:
            _adjust(components["momentum"], -4, "MACD柱连续3根减弱", evidence)

    rsi12 = _latest(frame, "RSI12")
    if rsi12 is not None:
        if rsi12 >= 70:
            _adjust(components["momentum"], -4, f"RSI12={rsi12:.1f}，进入超买区", evidence)
            warnings.append("RSI 已进入超买区，短期回撤风险上升。")
        elif rsi12 <= 30:
            _adjust(components["momentum"], 3, f"RSI12={rsi12:.1f}，进入超卖区", evidence)
            warnings.append("RSI 已进入超卖区，但超卖不等同于立即反转。")
        elif 50 < rsi12 < 70:
            _adjust(components["momentum"], 4, f"RSI12={rsi12:.1f}，处于偏强区间", evidence)
        elif 30 < rsi12 < 50:
            _adjust(components["momentum"], -3, f"RSI12={rsi12:.1f}，处于偏弱区间", evidence)

    divergence = _confirmed_divergence(frame)
    if divergence == "bullish":
        _adjust(components["momentum"], 6, "价格新低但RSI12未创新低，确认底背离", evidence)
    elif divergence == "bearish":
        _adjust(components["momentum"], -6, "价格新高但RSI12未创新高，确认顶背离", evidence)

    volume = _latest(frame, "volume")
    volume_ma5 = _latest(frame, "VOL_MA5")
    volume_ma10 = _latest(frame, "VOL_MA10")
    change = frame["close"].iloc[-1] - frame["close"].iloc[-2] if len(frame) >= 2 else 0
    if volume is not None and volume_ma5 and volume_ma10:
        baseline = (volume_ma5 + volume_ma10) / 2
        ratio = volume / baseline if baseline else 1
        if ratio >= 1.5 and change > 0:
            _adjust(components["volume"], 12, f"上涨且成交量放大至均量的{ratio:.2f}倍", evidence)
        elif ratio >= 1.5 and change < 0:
            _adjust(components["volume"], -12, f"下跌且成交量放大至均量的{ratio:.2f}倍", evidence)
        elif ratio <= 0.65:
            _adjust(
                components["volume"], -3, f"成交量缩至均量的{ratio:.2f}倍，趋势确认不足", evidence
            )
        else:
            evidence["neutral"].append(f"成交量为近期均量的{ratio:.2f}倍")
    else:
        components["volume"]["reasons"].append({"points": 0, "reason": "量均线样本不足，未计分"})

    if "OBV" in frame and (obv_slope := _slope(frame["OBV"], 5)) is not None:
        if obv_slope > 1:
            _adjust(components["volume"], 5, "OBV近5根上行，资金量价配合偏强", evidence)
        elif obv_slope < -1:
            _adjust(components["volume"], -5, "OBV近5根下行，资金量价配合偏弱", evidence)

    atr_pct = _latest(frame, "ATR_PCT")
    if atr_pct is None:
        components["risk"]["reasons"].append({"points": 0, "reason": "ATR14 样本不足，未计分"})
        warnings.append("ATR14 尚无有效值，波动风险未纳入评分。")
    elif atr_pct <= 1.5:
        _adjust(components["risk"], 8, f"ATR%={atr_pct:.2f}%，波动相对温和", evidence)
    elif atr_pct <= 3:
        components["risk"]["reasons"].append(
            {"points": 0, "reason": f"ATR%={atr_pct:.2f}%，波动处于常见区间"}
        )
    elif atr_pct <= 5:
        _adjust(components["risk"], -8, f"ATR%={atr_pct:.2f}%，波动偏高", evidence)
        warnings.append("ATR% 显示波动偏高，应留意价格跳动与止损空间。")
    else:
        _adjust(components["risk"], -15, f"ATR%={atr_pct:.2f}%，波动风险较高", evidence)
        warnings.append("ATR% 显示高波动风险，技术信号稳定性可能下降。")

    for component in components.values():
        component["score"] = round(float(np.clip(component["score"], 0, 100)), 1)
    market_regime = _market_regime(frame)
    weights = market_regime["weights"]
    total = round(sum(components[key]["score"] * weights[key] for key in components))
    total = int(np.clip(total, 0, 100))
    if len(frame) < 20:
        state = "数据不足"
        warnings.insert(0, "少于20根K线，趋势结构不足以形成稳定判断。")
    elif total >= 70:
        state = "偏强趋势"
    elif total >= 58:
        state = "震荡偏强"
    elif total >= 43:
        state = "中性震荡"
    elif total >= 30:
        state = "震荡偏弱"
    else:
        state = "偏弱趋势"

    if not warnings:
        warnings.append("技术指标存在滞后性，仍需关注市场与数据源风险。")
    latest_columns = [
        "close",
        "pct_change",
        "MA5",
        "MA10",
        "MA20",
        "MA60",
        "MA120",
        "MA250",
        "DIF",
        "DEA",
        "MACD",
        "RSI6",
        "RSI12",
        "RSI24",
        "K",
        "D",
        "J",
        "BOLL_MID",
        "BOLL_UPPER",
        "BOLL_LOWER",
        "ATR14",
        "ATR_PCT",
        "ADX14",
        "PLUS_DI14",
        "MINUS_DI14",
        "VOL_MA5",
        "VOL_MA10",
        "VOL_RATIO",
        "OBV",
    ]
    latest = {column: _latest(frame, column) for column in latest_columns}
    summary = (
        f"当前市场状态为{market_regime['label']}，技术方向为{state}，综合评分{total}/100。"
        f"趋势{components['trend']['score']:.0f}、动量{components['momentum']['score']:.0f}、"
        f"量能{components['volume']['score']:.0f}、波动/风险{components['risk']['score']:.0f}。"
    )
    return {
        "state": state,
        "score": total,
        "evidence": evidence,
        "warning": warnings,
        "components": components,
        "summary": summary,
        "latest": latest,
        "market_regime": market_regime,
        "formula_notes": [
            "MACD柱=2×(DIF-DEA)，DIF=EMA12-EMA26，DEA为DIF的9周期EMA。",
            "BOLL使用20周期样本标准差(ddof=1)，上下轨=MID±2σ。",
            "RSI与ATR使用Wilder平滑(alpha=1/周期)。",
            "量比=当前成交量/此前5根K线平均成交量。",
            "ADX14用于识别趋势强度；评分权重随趋势、震荡和波动状态动态调整。",
        ],
    }
