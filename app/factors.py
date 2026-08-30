"""无未来函数的连续量化特征层。"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

FACTOR_COLUMNS = (
    "close_vs_ma20_atr",
    "close_vs_ma60_atr",
    "close_vs_ma120_atr",
    "ma20_slope_5",
    "ma60_slope_5",
    "ma120_slope_10",
    "ma20_ma60_spread_atr",
    "ma60_ma120_spread_atr",
    "return_5",
    "return_20",
    "return_60",
    "return_120",
    "rsi6",
    "rsi12",
    "rsi24",
    "rsi12_delta_3",
    "macd_dif",
    "macd_dea",
    "macd_hist",
    "macd_hist_delta_3",
    "price_momentum_20",
    "volume_ratio_5",
    "volume_ratio_20",
    "up_volume_ratio_20",
    "down_volume_ratio_20",
    "breakout_volume_ratio",
    "atr_pct",
    "atr_percentile_250",
    "boll_width",
    "boll_width_percentile_250",
    "realized_volatility_20",
    "max_drawdown_20",
    "max_drawdown_60",
    "distance_to_support_atr",
    "distance_to_resistance_atr",
    "nearest_support_strength",
    "nearest_resistance_strength",
    "distance_20d_high",
    "distance_60d_high",
    "distance_120d_high",
    "higher_high_count_20",
    "higher_low_count_20",
    "lower_high_count_20",
    "lower_low_count_20",
)


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """安全相除；零或非有限分母产生 NaN。"""
    clean = denominator.astype(float).where(np.isfinite(denominator) & denominator.ne(0))
    return numerator.astype(float) / clean


def _rolling_percentile(series: pd.Series, window: int) -> pd.Series:
    """计算当前值在包含当前、仅含历史窗口中的经验分位，样本不足为 NaN。"""

    def percentile(values: np.ndarray) -> float:
        current = values[-1]
        return float(np.count_nonzero(values <= current) / len(values))

    minimum = min(20, window)
    return series.rolling(window, min_periods=minimum).apply(percentile, raw=True)


def _rolling_max_drawdown(series: pd.Series, window: int) -> pd.Series:
    """返回各历史窗口内部从峰值到随后谷值的最大回撤（负数）。"""

    def drawdown(values: np.ndarray) -> float:
        peaks = np.maximum.accumulate(values)
        ratios = values / np.where(peaks == 0, np.nan, peaks) - 1
        return float(np.nanmin(ratios))

    return series.rolling(window, min_periods=window).apply(drawdown, raw=True)


def _causal_level_factors(frame: pd.DataFrame, window: int = 4) -> pd.DataFrame:
    """逐根生成关键位距离。

    位于 ``pivot_position`` 的摆动点只在 ``pivot_position + window`` 时加入可用集合，
    因而在任一行都不会读取当时尚未出现的右侧 K 线。强度是相近已确认 Pivot 数量。
    """
    result = pd.DataFrame(index=frame.index)
    columns = (
        "distance_to_support_atr",
        "distance_to_resistance_atr",
        "nearest_support_strength",
        "nearest_resistance_strength",
    )
    for column in columns:
        result[column] = np.nan
    if len(frame) < window * 2 + 1:
        return result

    highs = frame["high"].to_numpy(dtype=float)
    lows = frame["low"].to_numpy(dtype=float)
    closes = frame["close"].to_numpy(dtype=float)
    atrs = frame["ATR14"].to_numpy(dtype=float)
    published: dict[int, list[tuple[str, float]]] = {}
    for pivot in range(window, len(frame) - window):
        high_slice = highs[pivot - window : pivot + window + 1]
        low_slice = lows[pivot - window : pivot + window + 1]
        publication = pivot + window
        if highs[pivot] == np.max(high_slice) and np.count_nonzero(
            high_slice == highs[pivot]
        ) == 1:
            published.setdefault(publication, []).append(("high", highs[pivot]))
        if lows[pivot] == np.min(low_slice) and np.count_nonzero(
            low_slice == lows[pivot]
        ) == 1:
            published.setdefault(publication, []).append(("low", lows[pivot]))

    known_highs: list[float] = []
    known_lows: list[float] = []
    for position in range(len(frame)):
        for kind, price in published.get(position, []):
            (known_highs if kind == "high" else known_lows).append(price)
        close = closes[position]
        atr = atrs[position]
        if not np.isfinite(close) or not np.isfinite(atr) or atr <= 0:
            continue
        band = max(close * 0.008, atr * 0.5)
        supports = [price for price in known_lows if price < close]
        resistances = [price for price in known_highs if price > close]
        row_index = frame.index[position]
        if supports:
            support = max(supports)
            result.at[row_index, "distance_to_support_atr"] = (close - support) / atr
            result.at[row_index, "nearest_support_strength"] = sum(
                abs(price - support) <= band for price in known_lows
            )
        if resistances:
            resistance = min(resistances)
            result.at[row_index, "distance_to_resistance_atr"] = (resistance - close) / atr
            result.at[row_index, "nearest_resistance_strength"] = sum(
                abs(price - resistance) <= band for price in known_highs
            )
    return result


def build_factors(frame: pd.DataFrame, levels: dict[str, Any] | None = None) -> pd.DataFrame:
    """返回与输入同索引的连续 Factor DataFrame。

    输入必须按时间升序并已由 :func:`app.indicators.add_indicators` 增强。滚动窗口
    只包含当前及更早数据；成交量基准显式 ``shift(1)``，突破高点由 Signal 层使用
    ``rolling(...).max().shift(1)``。窗口不足、分母为零或缺少可靠关键位时为 NaN。
    ``levels`` 仅用于调用方兼容，历史关键位始终在本函数内按时点因果计算。
    """
    del levels
    required = {"open", "high", "low", "close", "volume", "ATR14"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"缺少 Factor 计算列: {', '.join(sorted(missing))}")
    if "datetime" in frame and not frame["datetime"].is_monotonic_increasing:
        raise ValueError("Factor 输入必须按时间升序排列")

    factors = pd.DataFrame(index=frame.index)
    close = frame["close"].astype(float)
    atr = frame["ATR14"].astype(float)
    for period in (20, 60, 120):
        ma = frame.get(f"MA{period}", pd.Series(np.nan, index=frame.index)).astype(float)
        factors[f"close_vs_ma{period}_atr"] = _safe_divide(close - ma, atr)
    for period, lag in ((20, 5), (60, 5), (120, 10)):
        ma = frame.get(f"MA{period}", pd.Series(np.nan, index=frame.index)).astype(float)
        factors[f"ma{period}_slope_{lag}"] = ma.pct_change(lag)
    factors["ma20_ma60_spread_atr"] = _safe_divide(frame["MA20"] - frame["MA60"], atr)
    factors["ma60_ma120_spread_atr"] = _safe_divide(frame["MA60"] - frame["MA120"], atr)
    for period in (5, 20, 60, 120):
        factors[f"return_{period}"] = close.pct_change(period)

    for period in (6, 12, 24):
        factors[f"rsi{period}"] = frame[f"RSI{period}"].astype(float)
    factors["rsi12_delta_3"] = factors["rsi12"].diff(3)
    factors["macd_dif"] = frame["DIF"].astype(float)
    factors["macd_dea"] = frame["DEA"].astype(float)
    factors["macd_hist"] = frame["MACD"].astype(float)
    factors["macd_hist_delta_3"] = factors["macd_hist"].diff(3)
    factors["price_momentum_20"] = close / close.shift(20) - 1

    volume = frame["volume"].astype(float).where(frame["volume"].astype(float).ge(0))
    for period in (5, 20):
        prior_average = volume.shift(1).rolling(period, min_periods=period).mean()
        factors[f"volume_ratio_{period}"] = _safe_divide(volume, prior_average)
    direction = close.diff()
    total_volume = volume.rolling(20, min_periods=20).sum()
    factors["up_volume_ratio_20"] = _safe_divide(
        volume.where(direction > 0, 0).rolling(20, min_periods=20).sum(), total_volume
    )
    factors["down_volume_ratio_20"] = _safe_divide(
        volume.where(direction < 0, 0).rolling(20, min_periods=20).sum(), total_volume
    )
    factors["breakout_volume_ratio"] = factors["volume_ratio_20"]

    factors["atr_pct"] = _safe_divide(atr, close)
    factors["atr_percentile_250"] = _rolling_percentile(factors["atr_pct"], 250)
    boll_mid = frame["BOLL_MID"].astype(float)
    factors["boll_width"] = _safe_divide(
        frame["BOLL_UPPER"].astype(float) - frame["BOLL_LOWER"].astype(float), boll_mid
    )
    factors["boll_width_percentile_250"] = _rolling_percentile(factors["boll_width"], 250)
    log_return = np.log(close / close.shift(1))
    factors["realized_volatility_20"] = log_return.rolling(20, min_periods=20).std() * np.sqrt(252)
    factors["max_drawdown_20"] = _rolling_max_drawdown(close, 20)
    factors["max_drawdown_60"] = _rolling_max_drawdown(close, 60)

    factors = factors.join(_causal_level_factors(frame))
    for period in (20, 60, 120):
        prior_high = frame["high"].astype(float).rolling(period, min_periods=period).max()
        factors[f"distance_{period}d_high"] = _safe_divide(close - prior_high, atr)
    high_change = frame["high"].astype(float).diff()
    low_change = frame["low"].astype(float).diff()
    factors["higher_high_count_20"] = (high_change > 0).rolling(20, min_periods=20).sum()
    factors["higher_low_count_20"] = (low_change > 0).rolling(20, min_periods=20).sum()
    factors["lower_high_count_20"] = (high_change < 0).rolling(20, min_periods=20).sum()
    factors["lower_low_count_20"] = (low_change < 0).rolling(20, min_periods=20).sum()
    return factors.loc[:, FACTOR_COLUMNS].replace([np.inf, -np.inf], np.nan)


def factor_snapshot(factors: pd.DataFrame, position: int = -1) -> dict[str, float | None]:
    """将指定行转换为 JSON 安全的 Factor 快照。"""
    if factors.empty:
        return {column: None for column in FACTOR_COLUMNS}
    row = factors.iloc[position]
    return {
        column: round(float(value), 6) if pd.notna(value) and np.isfinite(value) else None
        for column, value in row.items()
    }
