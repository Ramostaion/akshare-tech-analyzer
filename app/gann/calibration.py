"""只按时间顺序选择参数并单独报告样本外结果。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from typing import Any

import pandas as pd

from app.gann.backtest import evaluate_gann_history
from app.gann.models import GannConfig


def _five_bar_accuracy(frame: pd.DataFrame, config: GannConfig) -> tuple[int, float | None]:
    result = evaluate_gann_history(frame, config)["angle_events"]["horizon_5"]
    return int(result["sample_count"]), result["direction_accuracy"]


def calibrate_gann_parameters(
    frame: pd.DataFrame,
    atr_multipliers: Iterable[float] = (0.125, 0.25, 0.5),
    base_config: GannConfig = GannConfig(),
) -> dict[str, Any]:
    """在训练段筛选、验证段择优，测试段只做最终报告。"""
    if len(frame) < 90:
        return {"available": False, "note": "少于 90 根 K 线，无法进行 60/20/20 校准。"}
    train_end = int(len(frame) * 0.6)
    validation_end = int(len(frame) * 0.8)
    train = frame.iloc[:train_end].copy()
    validation = frame.iloc[train_end:validation_end].reset_index(drop=True)
    test = frame.iloc[validation_end:].reset_index(drop=True)
    candidates: list[dict[str, Any]] = []
    for multiplier in atr_multipliers:
        config = replace(base_config, atr_multiplier=float(multiplier))
        train_sample, train_accuracy = _five_bar_accuracy(train, config)
        validation_sample, validation_accuracy = _five_bar_accuracy(validation, config)
        candidates.append(
            {
                "atr_multiplier": float(multiplier),
                "train_sample": train_sample,
                "train_accuracy": train_accuracy,
                "validation_sample": validation_sample,
                "validation_accuracy": validation_accuracy,
            }
        )
    eligible = [item for item in candidates if item["validation_accuracy"] is not None]
    if not eligible:
        return {"available": False, "candidates": candidates, "note": "验证段没有可评价角线事件。"}
    selected = max(
        eligible,
        key=lambda item: (float(item["validation_accuracy"]), int(item["validation_sample"])),
    )
    selected_config = replace(base_config, atr_multiplier=float(selected["atr_multiplier"]))
    test_sample, test_accuracy = _five_bar_accuracy(test, selected_config)
    return {
        "available": True,
        "split": "60% train / 20% validation / 20% out-of-sample",
        "selection_metric": "5 根 K 线方向准确率",
        "candidates": candidates,
        "selected": selected,
        "out_of_sample": {"sample_count": test_sample, "direction_accuracy": test_accuracy},
        "calibrated_probability_available": test_sample >= 30,
    }


__all__ = ["calibrate_gann_parameters"]
