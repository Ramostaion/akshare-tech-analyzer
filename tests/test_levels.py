from __future__ import annotations

import numpy as np
import pandas as pd

from app.indicators import add_indicators
from app.levels import confirmed_swings, identify_levels


def _range_frame(size: int = 220) -> pd.DataFrame:
    x = np.arange(size)
    close = 20 + np.sin(x * np.pi / 10) * 2
    open_price = close + np.sin(x / 3) * 0.08
    frame = pd.DataFrame(
        {
            "datetime": pd.date_range("2025-01-01", periods=size),
            "open": open_price,
            "high": np.maximum(open_price, close) + 0.2,
            "low": np.minimum(open_price, close) - 0.2,
            "close": close,
            "volume": 100_000 + (x % 10) * 2_000,
            "amount": close * 10_000_000,
            "amplitude": np.nan,
            "pct_change": pd.Series(close).pct_change() * 100,
            "change": pd.Series(close).diff(),
            "turnover": 1.0,
        }
    )
    return add_indicators(frame)


def test_swings_require_complete_right_window() -> None:
    frame = _range_frame(60)
    pivots = confirmed_swings(frame, window=4)
    assert pivots
    assert all(4 <= pivot.position < len(frame) - 4 for pivot in pivots)


def test_levels_cluster_repeated_touches() -> None:
    result = identify_levels(_range_frame())
    assert result["supports"]
    assert result["resistances"]
    assert result["supports"][0]["price"] < 20
    assert result["resistances"][0]["price"] > 20
    assert result["supports"][0]["touches"] >= 2
    assert result["supports"][0]["confidence"] in {"中", "高"}
    assert result["scenario"] is not None


def test_levels_report_insufficient_data() -> None:
    result = identify_levels(_range_frame(8))
    assert result["supports"] == []
    assert result["resistances"] == []
    assert "样本不足" in result["message"]
