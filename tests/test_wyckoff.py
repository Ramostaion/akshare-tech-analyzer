from __future__ import annotations

import pandas as pd

from app.indicators import add_indicators
from app.wyckoff import analyze_wyckoff
from app.wyckoff.events import detect_wyckoff_structure
from app.wyckoff.projection import project_wyckoff


def test_wyckoff_builds_range_and_conditional_projection(market_frame) -> None:
    frame = add_indicators(market_frame)

    result = analyze_wyckoff(frame)

    assert result["status"] == "active"
    assert result["phase"] in {"B", "C", "D", "E"}
    assert result["range"]["support"] < result["range"]["resistance"]
    assert len(result["projection"]["target_zone"]) == 2
    assert "不预测到达时间" in result["projection"]["note"]


def test_wyckoff_prefix_does_not_change_when_future_rows_change(market_frame) -> None:
    frame = add_indicators(market_frame)
    cutoff = 220
    expected = detect_wyckoff_structure(frame.iloc[:cutoff])
    changed = frame.copy()
    changed.loc[cutoff:, ["open", "high", "low", "close", "volume"]] *= 10

    actual = detect_wyckoff_structure(changed.iloc[:cutoff])

    assert actual == expected


def test_wyckoff_rejects_unreliable_volume(market_frame) -> None:
    frame = add_indicators(market_frame)
    frame["volume"] = float("nan")

    result = analyze_wyckoff(frame)

    assert result["status"] == "volume_unavailable"
    assert "可靠成交量" in result["note"]


def test_wyckoff_rejects_missing_volume_column(market_frame) -> None:
    frame = add_indicators(market_frame).drop(columns="volume")

    result = analyze_wyckoff(frame)

    assert result["status"] == "volume_unavailable"
    assert "可靠成交量" in result["note"]


def test_wyckoff_projection_uses_range_width_and_direction(market_frame) -> None:
    frame = add_indicators(market_frame)
    structure = {
        "range": {"support": 10.0, "resistance": 14.0},
        "direction": "up",
    }

    result = project_wyckoff(frame, structure)

    assert result["confirmation"] == 14.0
    assert result["target_zone"] == [16.0, 18.0]
    assert result["invalidation"] < 10.0
    assert pd.notna(result["invalidation"])
