"""时间序列研究工具：分桶、参数扫描、分层统计与 Walk Forward。"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from app.metrics import calculate_metrics, metrics_by_regime


@dataclass(frozen=True, slots=True)
class TimeSplit:
    """严格按位置递增且互不重叠的时间切分。"""

    train: tuple[int, int]
    validation: tuple[int, int]
    out_of_sample: tuple[int, int]


def time_series_split(
    size: int,
    train_fraction: float = 0.6,
    validation_fraction: float = 0.2,
) -> TimeSplit:
    """创建 train/validation/out-of-sample 连续切分，禁止随机打乱。"""
    if size < 10 or not (0 < train_fraction < 1) or not (0 < validation_fraction < 1):
        raise ValueError("样本数或切分比例无效")
    train_end = int(size * train_fraction)
    validation_end = train_end + int(size * validation_fraction)
    if train_end < 1 or validation_end >= size:
        raise ValueError("切分后每个区间必须至少包含一个样本")
    return TimeSplit((0, train_end), (train_end, validation_end), (validation_end, size))


def walk_forward_splits(
    size: int,
    train_size: int,
    validation_size: int,
    test_size: int,
    step: int | None = None,
) -> list[TimeSplit]:
    """生成扩展训练窗的 Walk Forward 切分；验证和测试始终晚于训练。"""
    if min(size, train_size, validation_size, test_size) <= 0:
        raise ValueError("窗口长度必须为正数")
    stride = step or test_size
    if stride <= 0:
        raise ValueError("step 必须为正数")
    splits: list[TimeSplit] = []
    train_end = train_size
    while train_end + validation_size + test_size <= size:
        validation_end = train_end + validation_size
        test_end = validation_end + test_size
        splits.append(
            TimeSplit((0, train_end), (train_end, validation_end), (validation_end, test_end))
        )
        train_end += stride
    return splits


def factor_bucket_study(
    factor: pd.Series,
    outcome_r: pd.Series,
    buckets: int = 5,
) -> list[dict[str, Any]]:
    """按 Factor 分位分桶并报告样本、胜率和 Expected R。"""
    aligned = pd.concat([factor.rename("factor"), outcome_r.rename("outcome")], axis=1).dropna()
    if aligned.empty or buckets < 2:
        return []
    bucket = pd.qcut(aligned["factor"], q=buckets, duplicates="drop")
    results = []
    for interval, group in aligned.groupby(bucket, observed=True):
        values = group["outcome"]
        results.append(
            {
                "bucket": str(interval),
                "sample": len(group),
                "win_rate": round(float(values.gt(0).mean() * 100), 2),
                "expectancy_r": round(float(values.mean()), 4),
            }
        )
    return results


def parameter_sweep(
    training_data: pd.DataFrame,
    parameter_name: str,
    values: Iterable[float],
    evaluator: Callable[[pd.DataFrame, float], dict[str, Any]],
) -> list[dict[str, Any]]:
    """仅在显式传入的训练数据上评估参数，不接触验证或样本外数据。"""
    results = []
    for value in values:
        metrics = evaluator(training_data.copy(), float(value))
        results.append({"parameter": parameter_name, "value": float(value), **metrics})
    return results


def select_on_validation(
    sweep_results: list[dict[str, Any]],
    validation_evaluator: Callable[[float], dict[str, Any]],
    key: str = "expectancy_r",
) -> dict[str, Any] | None:
    """先按训练结果取候选，再单独返回验证表现；不读取样本外区间。"""
    candidates = [item for item in sweep_results if item.get(key) is not None]
    if not candidates:
        return None
    best = max(candidates, key=lambda item: float(item[key]))
    return {"training": best, "validation": validation_evaluator(float(best["value"]))}


def trade_statistics_by_regime(trades: Iterable[Any]) -> dict[str, dict[str, Any]]:
    """研究层统一的 Regime 分组统计入口。"""
    return metrics_by_regime(trades)


def summarize_r_outcomes(values: pd.Series) -> dict[str, Any]:
    """为参数扫描提供不依赖 TradeRecord 的轻量 R 指标。"""
    clean = values.replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        return {"sample": 0, "win_rate": None, "expectancy_r": None, "profit_factor": None}
    gains = clean[clean > 0].sum()
    losses = abs(clean[clean < 0].sum())
    return {
        "sample": len(clean),
        "win_rate": round(float(clean.gt(0).mean() * 100), 2),
        "expectancy_r": round(float(clean.mean()), 4),
        "profit_factor": round(float(gains / losses), 4) if losses else None,
    }


__all__ = [
    "TimeSplit",
    "calculate_metrics",
    "factor_bucket_study",
    "parameter_sweep",
    "select_on_validation",
    "summarize_r_outcomes",
    "time_series_split",
    "trade_statistics_by_regime",
    "walk_forward_splits",
]
