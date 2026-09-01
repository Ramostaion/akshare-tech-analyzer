"""有限范围的 Elliott Wave 候选匹配。"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.wave.pivots import WavePivot
from app.wave.projection import project_candidate
from app.wave.scoring import fib_closeness, impulse_fib_score, momentum_volume_score


def _candidate_payload(
    pattern: str,
    current_wave: int | str,
    pivots: list[WavePivot],
    hard_rules: list[str],
    fib_score: float,
    momentum_score: float,
    direction: int,
    status: str,
    ratios: dict[str, float] | None = None,
) -> dict[str, Any]:
    structural_fit = float(np.clip(0.35 + 0.4 * fib_score + 0.25 * momentum_score, 0, 0.95))
    return {
        "pattern": pattern,
        "current_wave": current_wave,
        "status": status,
        "direction": "up" if direction > 0 else "down",
        "structural_fit": round(structural_fit, 3),
        # 保留旧字段，避免已有 API 消费方立即失效；界面不再称其为概率置信度。
        "confidence": round(structural_fit, 3),
        "pivots": [item.as_dict() for item in pivots],
        "hard_rules_passed": hard_rules,
        "fib_score": round(fib_score, 3),
        "fib_ratios": ratios or {},
        "momentum_score": round(momentum_score, 3),
        "projection": project_candidate(pattern, pivots, direction),
    }


def _impulse(frame: pd.DataFrame, sequence: list[WavePivot]) -> dict[str, Any] | None:
    kinds = [item.kind for item in sequence]
    if len(sequence) != 6 or kinds not in (
        ["low", "high", "low", "high", "low", "high"],
        ["high", "low", "high", "low", "high", "low"],
    ):
        return None
    direction = 1 if kinds[0] == "low" else -1
    p = [item.price for item in sequence]
    w1, w3, w5 = (
        direction * (p[1] - p[0]),
        direction * (p[3] - p[2]),
        direction * (p[5] - p[4]),
    )
    if min(w1, w3, w5) <= 0:
        return None
    rules = []
    if direction * (p[2] - p[0]) <= 0:
        return None
    rules.append("Wave2未越过Wave1起点")
    if w3 < min(w1, w5):
        return None
    rules.append("Wave3不是1/3/5中最短推动浪")
    if direction * (p[4] - p[1]) <= 0:
        return None
    rules.append("普通Impulse中Wave4未进入Wave1价格区间")
    fib_score, ratios = impulse_fib_score(sequence)
    momentum = momentum_volume_score(frame, sequence, direction)
    return _candidate_payload(
        "impulse", 5, sequence, rules, fib_score, momentum, direction, "completed", ratios
    )


def _abc_candidate(sequence: list[WavePivot]) -> dict[str, Any] | None:
    if len(sequence) != 4 or [item.kind for item in sequence] not in (
        ["high", "low", "high", "low"],
        ["low", "high", "low", "high"],
    ):
        return None
    p = [item.price for item in sequence]
    a = abs(p[1] - p[0])
    b = abs(p[2] - p[1])
    c = abs(p[3] - p[2])
    if min(a, c) <= 0 or b >= a:
        return None
    direction = 1 if p[1] > p[0] else -1
    fib_score = float(np.clip(1 - abs(c / a - 1) / 0.7, 0, 1))
    return _candidate_payload(
        "abc_zigzag",
        "C",
        sequence,
        ["B浪未完全反向吞没A浪", "A/C方向一致"],
        fib_score,
        0.5,
        direction,
        "completed",
    )


def _unfinished_abc(sequence: list[WavePivot]) -> dict[str, Any] | None:
    if len(sequence) != 3 or [item.kind for item in sequence] not in (
        ["high", "low", "high"],
        ["low", "high", "low"],
    ):
        return None
    p = [item.price for item in sequence]
    a = abs(p[1] - p[0])
    b = abs(p[2] - p[1])
    if a <= 0 or b >= a:
        return None
    direction = 1 if p[1] > p[0] else -1
    fib_score = fib_closeness(b / a, (0.382, 0.5, 0.618, 0.786))
    return _candidate_payload(
        "unfinished_abc",
        "C",
        sequence,
        ["B浪未完全反向吞没A浪", "C浪尚未形成已确认终点"],
        fib_score,
        0.5,
        direction,
        "developing",
        {"wave_b_retracement": round(b / a, 3)},
    )


def _unfinished_impulse(
    frame: pd.DataFrame,
    sequence: list[WavePivot],
) -> dict[str, Any] | None:
    kinds = [item.kind for item in sequence]
    if len(sequence) != 5 or kinds not in (
        ["low", "high", "low", "high", "low"],
        ["high", "low", "high", "low", "high"],
    ):
        return None
    direction = 1 if kinds[0] == "low" else -1
    p = [item.price for item in sequence]
    if direction * (p[2] - p[0]) <= 0 or direction * (p[4] - p[1]) <= 0:
        return None
    move = max(abs(p[1] - p[0]), 1e-12)
    wave3 = max(abs(p[3] - p[2]), 1e-12)
    retracement = abs(p[3] - p[4]) / wave3
    fib_score = fib_closeness(retracement, (0.236, 0.382, 0.5))
    return _candidate_payload(
        "unfinished_impulse",
        5,
        sequence,
        ["Wave2未越过Wave1起点", "已确认Wave4未进入Wave1价格区间"],
        fib_score,
        momentum_volume_score(frame, sequence, direction),
        direction,
        "developing",
        {"wave4_retracement": round(retracement, 3), "wave1_length": round(move, 3)},
    )


def find_wave_candidates(
    frame: pd.DataFrame,
    pivots: list[WavePivot],
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """输出合法结构的 Top-N 竞争候选，不输出非法硬规则结构。"""
    candidates: list[dict[str, Any]] = []
    if len(pivots) >= 6:
        impulse = _impulse(frame, pivots[-6:])
        if impulse:
            candidates.append(impulse)
    if len(pivots) >= 4:
        abc = _abc_candidate(pivots[-4:])
        if abc:
            candidates.append(abc)
    if len(pivots) >= 5:
        unfinished_impulse = _unfinished_impulse(frame, pivots[-5:])
        if unfinished_impulse:
            candidates.append(unfinished_impulse)
    if len(pivots) >= 3:
        unfinished_abc = _unfinished_abc(pivots[-3:])
        if unfinished_abc:
            candidates.append(unfinished_abc)
    candidates.sort(key=lambda item: item["structural_fit"], reverse=True)
    return candidates[: max(0, top_n)]
