from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def market_frame() -> pd.DataFrame:
    size = 320
    positions = np.arange(size)
    close = 10 + positions * 0.025 + np.sin(positions / 5) * 0.35
    open_price = close - np.sin(positions / 3) * 0.08
    high = np.maximum(open_price, close) + 0.16
    low = np.minimum(open_price, close) - 0.16
    volume = 100_000 + (positions % 17) * 2_500
    dates = [datetime(2024, 1, 2) + timedelta(days=int(value)) for value in positions]
    frame = pd.DataFrame(
        {
            "datetime": dates,
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume.astype(float),
            "amount": volume * close * 100,
        }
    )
    frame["amplitude"] = (frame["high"] - frame["low"]) / frame["close"].shift(1) * 100
    frame["pct_change"] = frame["close"].pct_change() * 100
    frame["change"] = frame["close"].diff()
    frame["turnover"] = 1.2
    return frame
