from __future__ import annotations

import pandas as pd
import pytest

from app.gann import analyze_gann, gann_decision_context
from app.gann.anchors import GannAnchor, confirmed_gann_anchor, confirmed_gann_anchors
from app.gann.evaluation import _evaluate_lifecycle, evaluate_gann_history
from app.gann.projection import project_gann
from app.indicators import add_indicators
from app.wave.pivots import WavePivot, confirmed_zigzag_pivots


def test_gann_uses_promoted_right_confirmed_pivot(market_frame) -> None:
    frame = add_indicators(market_frame)

    result = analyze_gann(frame)

    assert result["status"] == "active"
    anchor = result["anchor"]
    assert anchor["confirmation_position"] > anchor["position"]
    assert pd.Timestamp(anchor["confirmed_at"]) == pd.Timestamp(
        frame["datetime"].iloc[anchor["confirmation_position"]]
    )
    assert result["anchor_mode"] == "promoted_confirmed_pivot"
    assert result["version"] == "2.1"
    assert len(result["alternatives"]) == 2


def test_gann_promotes_latest_same_direction_pivot_and_keeps_reference(market_frame) -> None:
    frame = add_indicators(market_frame)
    pivots = confirmed_zigzag_pivots(frame, swing_window=3, atr_threshold=1.0)
    anchors = confirmed_gann_anchors(frame)

    for direction in ("up", "down"):
        expected = max(
            (
                pivot
                for pivot in pivots
                if ("up" if pivot.kind == "low" else "down") == direction
            ),
            key=lambda pivot: pivot.confirmation_position,
        )
        anchor = next(item for item in anchors if item.direction == direction)
        assert anchor.pivot.timestamp == expected.timestamp
        assert anchor.promotion_reason == "newer_confirmed_pivot"
    assert any(anchor.reference_pivot is not None for anchor in anchors)


def test_gann_projection_uses_fixed_anchor_ratios(market_frame) -> None:
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
    one = next(item for item in result["fan_lines"] if item["label"] == "1×1")
    elapsed = len(frame) - 1 - anchor.pivot.position
    expected = anchor.pivot.price + (1 if anchor.direction == "up" else -1) * (
        float(result["scale"]["unit_per_bar"]) * elapsed
    )
    assert float(one["current_price"]) == pytest.approx(expected, rel=1e-5)
    assert result["scale"]["key"] in {
        "atr14_eighth",
        "swing_velocity",
        "long_atr_eighth",
    }


def test_gann_prefix_does_not_change_when_future_rows_change(market_frame) -> None:
    frame = add_indicators(market_frame)
    cutoff = 240
    expected = analyze_gann(frame.iloc[:cutoff])
    changed = frame.copy()
    changed.loc[cutoff:, ["open", "high", "low", "close", "volume"]] *= 8

    actual = analyze_gann(changed.iloc[:cutoff])

    assert actual == expected


def test_gann_anchor_lifecycle_survives_one_close_excursion(market_frame) -> None:
    frame = add_indicators(market_frame).iloc[:260].copy()
    anchors = confirmed_gann_anchors(frame)
    up = next(item for item in anchors if item.direction == "up")
    extra = frame.iloc[-1].copy()
    extra["datetime"] = frame["datetime"].iloc[-1] + pd.Timedelta(days=1)
    extra["close"] = up.pivot.price - up.atr * 0.2
    extra["low"] = extra["close"] - 0.05
    extra["high"] = extra["close"] + 0.05
    extended = pd.concat([frame, extra.to_frame().T], ignore_index=True)
    after = confirmed_gann_anchors(extended)
    after_up = next(item for item in after if item.direction == "up")

    assert after_up.pivot.timestamp == up.pivot.timestamp


def test_gann_decision_context_does_not_override_trigger() -> None:
    ambiguous = gann_decision_context(
        {"status": "active", "ambiguous": True, "direction": "up"},
        "long_trigger",
    )
    conflict = gann_decision_context(
        {
            "status": "active",
            "ambiguous": False,
            "direction": "down",
            "current_state": "holding_one_by_one",
            "current_state_label": "价格保持在 1×1 有利侧",
        },
        "long_trigger",
    )

    assert ambiguous["alignment"] == "neutral"
    assert conflict["alignment"] == "conflicting"
    assert "降低执行信心" in conflict["note"]


def test_gann_same_bar_target_and_invalidation_is_conservative(monkeypatch) -> None:
    dates = pd.date_range("2024-01-01", periods=33, freq="D")
    frame = pd.DataFrame(
        {
            "datetime": dates,
            "open": [10.0] * 33,
            "high": [10.5] * 31 + [12.5, 10.5],
            "low": [9.5] * 31 + [8.5, 9.5],
            "close": [10.0] * 31 + [8.5, 10.0],
            "ATR14": [1.0] * 33,
        }
    )
    previous = WavePivot("high", 20, 23, dates[20], 12.0, 2.0)
    pivot = WavePivot("low", 27, 30, dates[27], 9.0, 3.0)
    anchor = GannAnchor("up", pivot, previous, 1.0)

    monkeypatch.setattr("app.gann.evaluation.confirmed_gann_anchors", lambda _frame: [anchor])

    result = evaluate_gann_history(frame, "up")

    assert result["resolved_count"] == 1
    assert result["target_first_count"] == 0
    assert result["invalidation_first_count"] == 1


def test_gann_angle_same_bar_invalidation_precedes_target() -> None:
    projection = {
        "confirmation": 12.0,
        "invalidation": 9.0,
        "confirmation_status": "waiting",
        "target_zone": [12.0, 13.0],
        "scale": {"unit_per_bar": 0.125, "atr": 1.0},
        "anchor": {"position": 27, "price": 9.0},
        "history_end_position": 30,
    }
    future = pd.DataFrame([{"high": 12.5, "low": 8.5, "close": 8.8}])

    outcome = _evaluate_lifecycle(future, projection, "up")

    assert outcome["resolved"] is True
    assert outcome["target_reached"] is False
