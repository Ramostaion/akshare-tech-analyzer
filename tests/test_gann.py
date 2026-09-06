from __future__ import annotations

import pandas as pd
import pytest

from app.cache import SQLiteCache
from app.gann import (
    GannConfig,
    analyze_gann,
    calibrate_gann_parameters,
    gann_decision_context,
)
from app.gann.anchors import anchor_score, confirmed_gann_anchor, confirmed_gann_anchors
from app.gann.backtest import evaluate_gann_history
from app.gann.confluence import build_confluence_zones
from app.gann.fan import angle_price, build_fan
from app.gann.multitimeframe import resample_weekly
from app.gann.pivots import confirmed_pivots
from app.gann.scale import build_scale
from app.gann.snapshots import build_snapshot
from app.gann.time_cycles import CYCLE_MULTIPLES, build_time_windows
from app.indicators import add_indicators


def _enriched(market_frame: pd.DataFrame) -> pd.DataFrame:
    return add_indicators(market_frame)


def test_pivots_are_right_confirmed_and_never_publish_tail(market_frame) -> None:
    frame = _enriched(market_frame)
    pivots = confirmed_pivots(frame)

    assert pivots
    assert all(item.confirmation_position == item.position + 3 for item in pivots)
    assert all(
        item.confirmed_at == pd.Timestamp(frame["datetime"].iloc[item.confirmation_position])
        for item in pivots
    )
    assert max(item.position for item in pivots) < len(frame) - 3


def test_confirmed_pivot_history_is_not_repainted_by_future_rows(market_frame) -> None:
    frame = _enriched(market_frame)
    cutoff = 220
    before = confirmed_pivots(frame.iloc[:cutoff])
    after = confirmed_pivots(frame)

    preserved = [item for item in after if item.confirmation_position < cutoff]
    assert [item.as_dict() for item in preserved] == [item.as_dict() for item in before]


def test_anchor_score_has_seven_weighted_components(market_frame) -> None:
    frame = _enriched(market_frame)
    pivots = confirmed_pivots(frame)
    pivot, previous = pivots[-1], pivots[-2]

    score, components = anchor_score(frame.iloc[: pivot.confirmation_position + 1], pivot, previous)

    assert set(components) == {
        "pivot_strength",
        "swing_magnitude",
        "atr_significance",
        "support_resistance",
        "volume_confirmation",
        "momentum_reversal",
        "time_persistence",
    }
    assert score == pytest.approx(sum(components.values()), abs=0.1)
    assert 0 <= score <= 100


def test_competing_anchors_use_latest_confirmed_pivot_per_direction(market_frame) -> None:
    frame = _enriched(market_frame)
    pivots = confirmed_pivots(frame)
    anchors = confirmed_gann_anchors(frame)

    assert {item.direction for item in anchors} == {"up", "down"}
    for anchor in anchors:
        kind = "low" if anchor.direction == "up" else "high"
        expected = max(item.confirmation_position for item in pivots if item.kind == kind)
        assert anchor.pivot.confirmation_position == expected
        assert anchor.lifecycle_id


@pytest.mark.parametrize("mode", ["atr", "percent", "log"])
def test_price_scale_modes_are_positive_and_pixel_independent(market_frame, mode) -> None:
    frame = _enriched(market_frame)
    anchor = confirmed_gann_anchor(frame)
    assert anchor is not None

    scale = build_scale(anchor, GannConfig(scale_mode=mode))

    assert scale.price_unit > 0
    assert "pixel" not in scale.as_dict()
    if mode == "atr":
        assert scale.price_unit == pytest.approx(anchor.atr * 0.25)


def test_fan_math_uses_fixed_anchor_and_bar_index(market_frame) -> None:
    frame = _enriched(market_frame)
    anchor = confirmed_gann_anchor(frame)
    assert anchor is not None
    scale = build_scale(anchor)
    fan = build_fan(frame, anchor, scale, 15)
    latest = len(frame) - 1
    elapsed = latest - anchor.pivot.position
    one = next(item for item in fan if item["label"] == "1×1")
    two = next(item for item in fan if item["label"] == "2×1")
    half = next(item for item in fan if item["label"] == "1×2")
    sign = 1 if anchor.direction == "up" else -1

    assert float(one["current_price"]) == pytest.approx(
        anchor.pivot.price + sign * scale.price_unit * elapsed, rel=1e-5
    )
    assert abs(float(two["current_price"]) - anchor.pivot.price) == pytest.approx(
        abs(float(one["current_price"]) - anchor.pivot.price) * 2, rel=1e-5
    )
    assert abs(float(half["current_price"]) - anchor.pivot.price) == pytest.approx(
        abs(float(one["current_price"]) - anchor.pivot.price) * 0.5, rel=1e-5
    )


def test_time_windows_derive_from_swing_durations_and_bar_positions(market_frame) -> None:
    frame = _enriched(market_frame)
    pivots = confirmed_pivots(frame)
    anchor = confirmed_gann_anchor(frame)
    assert anchor is not None

    cycles, windows = build_time_windows(frame, anchor, pivots, 30, "daily")

    assert cycles
    assert windows
    assert set(CYCLE_MULTIPLES) >= {float(item["multiple"]) for item in windows}
    assert all(
        item["center_position"] - (len(frame) - 1) == item["bars_from_now"] for item in windows
    )
    assert all(
        item["start_position"] <= item["center_position"] <= item["end_position"]
        for item in windows
    )


def test_confluence_score_increases_with_more_price_factors(market_frame) -> None:
    frame = _enriched(market_frame)
    anchor = confirmed_gann_anchor(frame)
    assert anchor is not None
    scale = build_scale(anchor)
    position = len(frame) + 4
    projected = angle_price(anchor, scale, 1.0, position)
    window = {
        "label": "1T",
        "center_position": position,
        "center_datetime": pd.Timestamp(frame["datetime"].iloc[-1]).isoformat(),
    }
    basic = build_confluence_zones(
        frame,
        anchor,
        scale,
        [{"price": projected, "label": "1/2", "source": "gann_eighth"}],
        [window],
    )
    rich = build_confluence_zones(
        frame,
        anchor,
        scale,
        [
            {"price": projected, "label": "水平阻力", "source": "horizontal_sr"},
            {"price": projected, "label": "Fib 0.618", "source": "fibonacci"},
        ],
        [window],
        {"direction": anchor.direction},
    )

    assert basic and rich
    assert rich[0]["score"] > basic[0]["score"]


def test_scenarios_contain_trigger_target_window_invalidation_and_decay(market_frame) -> None:
    frame = _enriched(market_frame)
    result = analyze_gann(frame, "daily", include_backtest=False)

    assert result["forecast_horizon"]["main_bars"] == 15
    assert len(result["scenarios"]) == 2
    assert sum(item["confidence"] for item in result["scenarios"]) == pytest.approx(1.0)
    for item in result["scenarios"]:
        assert item["trigger"] and item["confirmation"] and item["target_zones"]
        assert item["time_windows"] and item["invalidation"]
        assert item["effective_confidence"] < item["confidence"]


def test_prefix_result_does_not_change_when_later_rows_change(market_frame) -> None:
    frame = _enriched(market_frame)
    cutoff = 240
    expected = analyze_gann(frame.iloc[:cutoff], include_backtest=False)
    changed = frame.copy()
    changed.loc[cutoff:, ["open", "high", "low", "close", "volume"]] *= 8

    actual = analyze_gann(changed.iloc[:cutoff], include_backtest=False)

    assert actual == expected


def test_daily_and_weekly_find_independent_anchors(market_frame) -> None:
    frame = _enriched(market_frame)
    weekly = resample_weekly(frame)
    daily_anchor = confirmed_gann_anchor(frame)
    weekly_config = GannConfig(pivot_window=2, pivot_atr_factor=0.2, pivot_percent_threshold=0.001)
    weekly_anchor = confirmed_gann_anchor(weekly, weekly_config)

    assert daily_anchor is not None and weekly_anchor is not None
    assert daily_anchor.pivot.timestamp != weekly_anchor.pivot.timestamp


def test_backtest_reports_random_baseline_and_ordered_oos(market_frame) -> None:
    result = evaluate_gann_history(_enriched(market_frame))

    assert result["no_lookahead"] is True
    assert "random_baseline_reversal_rate" in result["time_windows"]
    assert result["time_windows"]["baseline_policy"]
    assert "walk_forward" in result


def test_parameter_calibration_rejects_too_short_series(market_frame) -> None:
    result = calibrate_gann_parameters(_enriched(market_frame).iloc[:80])

    assert result["available"] is False
    assert "60/20/20" in result["note"]


def test_snapshot_is_insert_only(tmp_path, market_frame) -> None:
    result = analyze_gann(_enriched(market_frame), include_backtest=False)
    snapshot = build_snapshot("600011", "daily", result)
    cache = SQLiteCache(tmp_path / "cache.sqlite3")

    assert cache.save_gann_snapshot(snapshot) is True
    changed = dict(snapshot)
    changed["scenarios"] = []
    assert cache.save_gann_snapshot(changed) is False
    assert cache.get_gann_snapshot(snapshot["snapshot_id"])["scenarios"]
    cache.close()


def test_gann_context_never_overrides_trigger(market_frame) -> None:
    result = analyze_gann(_enriched(market_frame), include_backtest=False)
    context = gann_decision_context(result, "long_trigger")

    assert context["alignment"] in {"supportive", "conflicting", "neutral"}
    assert "order" not in context
