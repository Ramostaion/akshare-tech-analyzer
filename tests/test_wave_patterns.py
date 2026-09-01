from __future__ import annotations

import pandas as pd

from app.wave.patterns import find_wave_candidates
from app.wave.pivots import WavePivot


def _pivot(kind: str, position: int, price: float) -> WavePivot:
    return WavePivot(
        kind,
        position,
        position + 1,
        pd.Timestamp("2024-01-01") + pd.Timedelta(days=position),
        price,
        2,
    )


def _frame() -> pd.DataFrame:
    return pd.DataFrame({"MACD": range(20), "volume": [100.0] * 20})


def test_valid_impulse_passes_hard_rules() -> None:
    pivots = [
        _pivot("low", 0, 10),
        _pivot("high", 2, 14),
        _pivot("low", 4, 12),
        _pivot("high", 7, 20),
        _pivot("low", 9, 15),
        _pivot("high", 12, 22),
    ]
    candidates = find_wave_candidates(_frame(), pivots)

    impulse = next(item for item in candidates if item["pattern"] == "impulse")
    assert len(impulse["hard_rules_passed"]) == 3
    assert 0 <= impulse["confidence"] <= 1
    assert impulse["status"] == "completed"
    assert impulse["structural_fit"] == impulse["confidence"]
    assert max(impulse["projection"]["primary_zone"]) < pivots[-1].price


def test_valid_down_impulse_and_reversal_zone() -> None:
    pivots = [
        _pivot("high", 0, 22),
        _pivot("low", 2, 18),
        _pivot("high", 4, 20),
        _pivot("low", 7, 12),
        _pivot("high", 9, 17),
        _pivot("low", 12, 10),
    ]

    impulse = next(
        item for item in find_wave_candidates(_frame(), pivots) if item["pattern"] == "impulse"
    )

    assert impulse["direction"] == "down"
    assert impulse["projection"]["path_direction"] == "up"
    assert min(impulse["projection"]["primary_zone"]) > pivots[-1].price


def test_unfinished_impulse_uses_wave4_as_invalidation() -> None:
    pivots = [
        _pivot("low", 0, 10),
        _pivot("high", 2, 14),
        _pivot("low", 4, 12),
        _pivot("high", 7, 20),
        _pivot("low", 9, 15),
    ]

    candidate = next(
        item
        for item in find_wave_candidates(_frame(), pivots)
        if item["pattern"] == "unfinished_impulse"
    )

    assert candidate["status"] == "developing"
    assert candidate["projection"]["confirmation"] == 20
    assert candidate["projection"]["invalidation"] == 15
    assert min(candidate["projection"]["primary_zone"]) > 15


def test_completed_abc_projects_opposite_to_c_direction() -> None:
    upward = [
        _pivot("low", 0, 10),
        _pivot("high", 2, 14),
        _pivot("low", 4, 12),
        _pivot("high", 7, 16),
    ]
    downward = [
        _pivot("high", 0, 20),
        _pivot("low", 2, 16),
        _pivot("high", 4, 18),
        _pivot("low", 7, 14),
    ]

    up_candidate = next(
        item
        for item in find_wave_candidates(_frame(), upward)
        if item["pattern"] == "abc_zigzag"
    )
    down_candidate = next(
        item
        for item in find_wave_candidates(_frame(), downward)
        if item["pattern"] == "abc_zigzag"
    )

    assert max(up_candidate["projection"]["primary_zone"]) < 16
    assert min(down_candidate["projection"]["primary_zone"]) > 14


def test_wave2_below_origin_is_rejected() -> None:
    pivots = [
        _pivot("low", 0, 10),
        _pivot("high", 2, 14),
        _pivot("low", 4, 9),
        _pivot("high", 7, 20),
        _pivot("low", 9, 15),
        _pivot("high", 12, 22),
    ]

    assert not any(item["pattern"] == "impulse" for item in find_wave_candidates(_frame(), pivots))


def test_wave3_shortest_is_rejected() -> None:
    pivots = [
        _pivot("low", 0, 10),
        _pivot("high", 2, 15),
        _pivot("low", 4, 13),
        _pivot("high", 7, 15),
        _pivot("low", 9, 15.5),
        _pivot("high", 12, 20),
    ]

    assert not any(item["pattern"] == "impulse" for item in find_wave_candidates(_frame(), pivots))
