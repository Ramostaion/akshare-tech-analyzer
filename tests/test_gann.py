from __future__ import annotations

import pandas as pd
import pytest

from app.gann import analyze_gann
from app.gann.anchors import GannAnchor, confirmed_gann_anchor
from app.gann.evaluation import evaluate_gann_history
from app.gann.projection import project_gann
from app.indicators import add_indicators
from app.wave.pivots import WavePivot


def test_gann_uses_latest_right_confirmed_pivot(market_frame) -> None:
    frame = add_indicators(market_frame)

    result = analyze_gann(frame)

    assert result["status"] == "active"
    anchor = result["anchor"]
    assert anchor["confirmation_position"] > anchor["position"]
    assert pd.Timestamp(anchor["confirmed_at"]) == pd.Timestamp(
        frame["datetime"].iloc[anchor["confirmation_position"]]
    )
    assert result["anchor_mode"] == "auto_confirmed_pivot"


def test_gann_projection_uses_atr_normalized_ratios(market_frame) -> None:
    frame = add_indicators(market_frame)
    anchor = confirmed_gann_anchor(frame)
    assert anchor is not None

    result = project_gann(frame, anchor)
    moves = {
        item["label"]: abs(float(item["end_price"]) - float(item["current_price"]))
        for item in result["fan_lines"]
    }

    assert moves["2×1"] == pytest.approx(moves["1×1"] * 2, rel=1e-5)
    assert moves["1×2"] == pytest.approx(moves["1×1"] * 0.5, rel=1e-5)
    assert all(
        float(item["current_price"]) == pytest.approx(float(frame["close"].iloc[-1]))
        for item in result["fan_lines"]
    )
    assert result["scale"]["method"] == "ATR14/8 每根 K 线"


def test_gann_same_bar_target_and_invalidation_is_conservative(monkeypatch) -> None:
    dates = pd.date_range("2024-01-01", periods=33, freq="D")
    frame = pd.DataFrame(
        {
            "datetime": dates,
            "open": [10.0] * 33,
            "high": [10.5] * 31 + [12.5, 10.5],
            "low": [9.5] * 31 + [8.5, 9.5],
            "close": [10.0] * 33,
            "ATR14": [1.0] * 33,
        }
    )
    previous = WavePivot("high", 20, 23, dates[20], 12.0, 2.0)
    pivot = WavePivot("low", 27, 30, dates[27], 9.0, 3.0)
    anchor = GannAnchor("up", pivot, previous, 1.0)

    monkeypatch.setattr(
        "app.gann.evaluation.confirmed_gann_anchor",
        lambda _frame: anchor,
    )

    result = evaluate_gann_history(frame, "up")

    assert result["resolved_count"] == 1
    assert result["target_first_count"] == 0
    assert result["invalidation_first_count"] == 1
