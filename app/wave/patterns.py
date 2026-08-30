"""有限范围的 Elliott Wave 候选匹配。"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.wave.pivots import WavePivot
from app.wave.projection import project_candidate
from app.wave.scoring import impulse_fib_score, momentum_volume_score


def _candidate_payload(
    pattern: str,
    current_wave: int | str,
    pivots: list[WavePivot],
    hard_rules: list[str],
    fib_score: float,
    momentum_score: float,
    ratios: dict[str, float] | None = None,
) -> dict[str, Any]:
    confidence = float(np.clip(0.45 + 0.3 * fib_score + 0.25 * momentum_score, 0, 0.95))
    return {
        "pattern": pattern,
        "current_wave": current_wave,
        "confidence": round(confidence, 3),
        "pivots": [item.as_dict() for item in pivots],
        "hard_rules_passed": hard_rules,
        "fib_score": round(fib_score, 3),
        "fib_ratios": ratios or {},
        "momentum_score": round(momentum_score, 3),
        "projection": project_candidate(pattern, pivots),
    }


def _up_impulse(frame: pd.DataFrame, sequence: list[WavePivot]) -> dict[str, Any] | None:
    if len(sequence) != 6 or [item.kind for item in sequence] != [
        "low", "high", "low", "high", "low", "high"
    ]:
        return None
    p = [item.price for item in sequence]
    w1, w3, w5 = p[1] - p[0], p[3] - p[2], p[5] - p[4]
    if min(w1, w3, w5) <= 0:
        return None
    rules = []
    if p[2] <= p[0]:
        return None
    rules.append("Wave2未跌破Wave1起点")
    if w3 < min(w1, w5):
        return None
    rules.append("Wave3不是1/3/5中最短推动浪")
    if p[4] <= p[1]:
        return None
    rules.append("普通Impulse中Wave4未进入Wave1价格区间")
    fib_score, ratios = impulse_fib_score(sequence)
    momentum = momentum_volume_score(frame, sequence)
    return _candidate_payload("impulse", 5, sequence, rules, fib_score, momentum, ratios)


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
    if min(a, c) <= 0 or b >= a * 1.1:
        return None
    fib_score = float(np.clip(1 - abs(c / a - 1) / 0.7, 0, 1))
    return _candidate_payload(
        "abc_zigzag", "C", sequence, ["B浪未完全反向吞没A浪", "A/C方向一致"], fib_score, 0.5
    )


def find_wave_candidates(
    frame: pd.DataFrame,
    pivots: list[WavePivot],
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """输出合法结构的 Top-N 竞争候选，不输出非法硬规则结构。"""
    candidates: list[dict[str, Any]] = []
    if len(pivots) >= 6:
        impulse = _up_impulse(frame, pivots[-6:])
        if impulse:
            candidates.append(impulse)
    if len(pivots) >= 4:
        abc = _abc_candidate(pivots[-4:])
        if abc:
            candidates.append(abc)
    if len(pivots) >= 5 and [item.kind for item in pivots[-5:]] == [
        "low", "high", "low", "high", "low"
    ]:
        p = [item.price for item in pivots[-5:]]
        if p[2] > p[0] and p[4] > p[1] and p[3] > p[1]:
            move = max(p[1] - p[0], 1e-12)
            retracement = (p[3] - p[4]) / max(p[3] - p[2], 1e-12)
            fib_score = float(np.clip(1 - abs(retracement - 0.382) / 0.5, 0, 1))
            candidates.append(
                _candidate_payload(
                    "unfinished_impulse",
                    5,
                    pivots[-5:],
                    ["Wave2未跌破Wave1起点", "已确认Wave4保持在Wave1高点上方"],
                    fib_score,
                    momentum_volume_score(frame, pivots[-5:]),
                    {"wave4_retracement": round(retracement, 3), "wave1_length": round(move, 3)},
                )
            )
    candidates.sort(key=lambda item: item["confidence"], reverse=True)
    return candidates[: max(0, top_n)]
