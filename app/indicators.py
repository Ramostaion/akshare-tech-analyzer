"""纯 pandas/NumPy 技术指标。

所有函数要求输入按时间升序排列，只使用当前及更早的数据；滚动窗口均不居中。
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    """计算简单移动平均；窗口不足时返回 NaN。"""
    if period <= 0:
        raise ValueError("period 必须大于0")
    return series.astype(float).rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """计算指数移动平均，使用 adjust=False 的递归形式。"""
    if period <= 0:
        raise ValueError("period 必须大于0")
    return series.astype(float).ewm(span=period, adjust=False, min_periods=period).mean()


def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """计算 MACD：DIF=EMA12-EMA26，DEA=DIF 的 EMA9，柱=2*(DIF-DEA)。"""
    dif = ema(close, fast) - ema(close, slow)
    dea = dif.ewm(span=signal, adjust=False, min_periods=signal).mean()
    histogram = 2 * (dif - dea)
    return pd.DataFrame({"DIF": dif, "DEA": dea, "MACD": histogram}, index=close.index)


def rsi(close: pd.Series, period: int) -> pd.Series:
    """使用 Wilder(alpha=1/period) 平滑计算 RSI。

    上涨而无下跌时为100，完全无涨跌时为50；种子期保持 NaN。
    """
    if period <= 0:
        raise ValueError("period 必须大于0")
    delta = close.astype(float).diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    relative_strength = avg_gain / avg_loss.replace(0, np.nan)
    result = 100 - (100 / (1 + relative_strength))
    result = result.mask((avg_loss == 0) & (avg_gain > 0), 100.0)
    result = result.mask((avg_loss == 0) & (avg_gain == 0), 50.0)
    return result


def kdj(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 9,
    smooth_k: int = 3,
    smooth_d: int = 3,
) -> pd.DataFrame:
    """计算 KDJ(9,3,3)，K/D 从50开始按 alpha=1/3 递归平滑。"""
    if min(period, smooth_k, smooth_d) <= 0:
        raise ValueError("KDJ 周期必须大于0")
    lowest = low.astype(float).rolling(period, min_periods=period).min()
    highest = high.astype(float).rolling(period, min_periods=period).max()
    price_range = highest - lowest
    rsv = (close.astype(float) - lowest) / price_range.replace(0, np.nan) * 100
    rsv = rsv.mask(price_range == 0, 50.0)

    k_values = np.full(len(close), np.nan, dtype=float)
    d_values = np.full(len(close), np.nan, dtype=float)
    previous_k = 50.0
    previous_d = 50.0
    alpha_k = 1 / smooth_k
    alpha_d = 1 / smooth_d
    for position, value in enumerate(rsv.to_numpy(dtype=float)):
        if np.isnan(value):
            continue
        previous_k = (1 - alpha_k) * previous_k + alpha_k * value
        previous_d = (1 - alpha_d) * previous_d + alpha_d * previous_k
        k_values[position] = previous_k
        d_values[position] = previous_d
    k_series = pd.Series(k_values, index=close.index)
    d_series = pd.Series(d_values, index=close.index)
    return pd.DataFrame(
        {"K": k_series, "D": d_series, "J": 3 * k_series - 2 * d_series}, index=close.index
    )


def bollinger_bands(close: pd.Series, period: int = 20, width: float = 2.0) -> pd.DataFrame:
    """计算布林带；标准差固定使用样本标准差 ddof=1。"""
    middle = sma(close, period)
    deviation = close.astype(float).rolling(period, min_periods=period).std(ddof=1)
    return pd.DataFrame(
        {
            "BOLL_MID": middle,
            "BOLL_UPPER": middle + width * deviation,
            "BOLL_LOWER": middle - width * deviation,
        },
        index=close.index,
    )


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """计算 True Range，首根使用当根最高价减最低价。"""
    previous_close = close.astype(float).shift(1)
    ranges = pd.concat(
        [
            high.astype(float) - low.astype(float),
            (high.astype(float) - previous_close).abs(),
            (low.astype(float) - previous_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1, skipna=True)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """以 Wilder(alpha=1/period) 平滑 True Range 得到 ATR。"""
    if period <= 0:
        raise ValueError("period 必须大于0")
    return (
        true_range(high, low, close).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    )


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """计算能量潮 OBV；首根从0开始，平盘成交量不计入。"""
    direction = np.sign(close.astype(float).diff()).fillna(0)
    return (direction * volume.astype(float).fillna(0)).cumsum()


def add_indicators(
    frame: pd.DataFrame,
    ma_periods: Iterable[int] = (5, 10, 20, 60, 120, 250),
) -> pd.DataFrame:
    """返回包含全部项目指标的新 DataFrame，不修改输入。"""
    required = {"open", "high", "low", "close", "volume"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"缺少指标计算列: {', '.join(sorted(missing))}")
    result = frame.copy()
    for period in ma_periods:
        result[f"MA{period}"] = sma(result["close"], period)
    result["EMA12"] = ema(result["close"], 12)
    result["EMA26"] = ema(result["close"], 26)
    result = result.join(macd(result["close"]))
    for period in (6, 12, 24):
        result[f"RSI{period}"] = rsi(result["close"], period)
    result = result.join(kdj(result["high"], result["low"], result["close"]))
    result = result.join(bollinger_bands(result["close"]))
    result["ATR14"] = atr(result["high"], result["low"], result["close"], 14)
    result["ATR_PCT"] = result["ATR14"] / result["close"].replace(0, np.nan) * 100
    result["VOL_MA5"] = sma(result["volume"], 5)
    result["VOL_MA10"] = sma(result["volume"], 10)
    prior_volume_average = result["volume"].shift(1).rolling(5, min_periods=5).mean()
    result["VOL_RATIO"] = result["volume"] / prior_volume_average.replace(0, np.nan)
    result["OBV"] = obv(result["close"], result["volume"])
    return result
