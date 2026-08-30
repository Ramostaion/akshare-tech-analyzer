from __future__ import annotations

import numpy as np
import pandas as pd

from app.wave.pivots import confirmed_zigzag_pivots


def _pivot_frame() -> pd.DataFrame:
    close = np.array([10, 11, 13, 11, 9, 11, 14, 12, 10, 12, 15, 13], dtype=float)
    return pd.DataFrame(
        {
            "datetime": pd.date_range("2024-01-01", periods=len(close)),
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close,
            "ATR14": 1.0,
        }
    )


def test_wave_pivot_is_published_only_after_right_confirmation() -> None:
    frame = _pivot_frame()
    pivots = confirmed_zigzag_pivots(frame, swing_window=1, atr_threshold=0.5)

    assert pivots
    assert all(item.confirmation_position == item.position + 1 for item in pivots)
    assert all(item.confirmation_position < len(frame) for item in pivots)


def test_appending_future_does_not_change_already_confirmed_pivots() -> None:
    frame = _pivot_frame()
    prefix = confirmed_zigzag_pivots(frame.iloc[:9], swing_window=1, atr_threshold=0.5)
    complete = confirmed_zigzag_pivots(frame, swing_window=1, atr_threshold=0.5)
    comparable = [item for item in complete if item.confirmation_position < 9]

    assert [(item.kind, item.position) for item in prefix] == [
        (item.kind, item.position) for item in comparable
    ]


def test_unconfirmed_last_swing_is_not_output() -> None:
    frame = _pivot_frame()
    frame.loc[frame.index[-1], "high"] = 100
    pivots = confirmed_zigzag_pivots(frame, swing_window=2, atr_threshold=0.5)

    assert all(item.position < len(frame) - 2 for item in pivots)
