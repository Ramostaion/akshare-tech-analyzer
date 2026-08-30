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
