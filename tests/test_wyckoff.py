from __future__ import annotations

import numpy as np
import pandas as pd

from app.indicators import add_indicators
from app.wyckoff import analyze_wyckoff, wyckoff_decision_context
from app.wyckoff.evaluation import _evaluate_lifecycle, evaluate_wyckoff_history
from app.wyckoff.events import detect_wyckoff_structure
from app.wyckoff.projection import project_wyckoff


def test_wyckoff_builds_range_and_conditional_projection(market_frame) -> None:
    frame = add_indicators(market_frame)

    result = analyze_wyckoff(frame)

    assert result["status"] == "active"
    assert result["phase"] in {"B", "C", "D", "E"}
    assert result["version"] == "2.0"
    assert len(result["alternatives"]) == 2
    assert "range_stability" in result["score_components"]
    assert result["range"]["age_bars"] > 0
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


def _wyckoff_sequence_frame() -> pd.DataFrame:
    rows = 100
    dates = pd.date_range("2025-01-01", periods=rows, freq="D")
    close = np.full(rows, 11.0)
    frame = pd.DataFrame(
        {
            "datetime": dates,
            "open": close - 0.05,
            "high": np.full(rows, 12.1),
            "low": np.full(rows, 9.9),
            "close": close,
            "volume": np.full(rows, 100.0),
            "ATR14": np.full(rows, 0.5),
            "OBV": np.arange(rows, dtype=float),
        }
    )
    frame.loc[70, ["open", "high", "low", "close", "volume"]] = [
        10.0, 10.5, 9.7, 10.35, 120.0
    ]
    frame.loc[73, ["open", "high", "low", "close", "volume"]] = [
        10.1, 10.35, 9.95, 10.25, 70.0
    ]
    frame.loc[76, ["open", "high", "low", "close", "volume"]] = [
        11.6, 12.45, 11.55, 12.35, 160.0
    ]
    frame.loc[78, ["open", "high", "low", "close", "volume"]] = [
        12.05, 12.3, 11.95, 12.18, 70.0
    ]
    return frame


def test_wyckoff_state_machine_requires_order_and_marks_follow_through() -> None:
    result = detect_wyckoff_structure(_wyckoff_sequence_frame())
    accumulation = next(
        item for item in result["alternatives"] if item["structure"] == "accumulation"
    )
    labels = [item["event"] for item in accumulation["events"]]

    assert labels.index("Spring") < labels.index("Test") < labels.index("SOS") < labels.index("LPS")
    spring = next(item for item in accumulation["events"] if item["event"] == "Spring")
    sos = next(item for item in accumulation["events"] if item["event"] == "SOS")
    assert spring["confirmation_state"] == "follow_through_confirmed"
    assert sos["confirmation_state"] == "follow_through_confirmed"
    assert accumulation["phase"] in {"D", "E"}


def test_wyckoff_does_not_label_lps_before_sos() -> None:
    frame = _wyckoff_sequence_frame()
    frame.loc[76, ["open", "high", "low", "close", "volume"]] = [
        11.0, 11.5, 10.6, 11.1, 100.0
    ]
    result = detect_wyckoff_structure(frame)
    accumulation = next(
        item for item in result["alternatives"] if item["structure"] == "accumulation"
    )

    assert "LPS" not in [item["event"] for item in accumulation["events"]]


def test_distribution_state_machine_mirrors_ordered_events() -> None:
    source = _wyckoff_sequence_frame()
    frame = source.copy()
    frame["open"] = 22 - source["open"]
    frame["high"] = 22 - source["low"]
    frame["low"] = 22 - source["high"]
    frame["close"] = 22 - source["close"]
    frame["OBV"] = -source["OBV"]

    result = detect_wyckoff_structure(frame)
    distribution = next(
        item for item in result["alternatives"] if item["structure"] == "distribution"
    )
    labels = [item["event"] for item in distribution["events"]]

    assert labels.index("UTAD") < labels.index("Test") < labels.index("SOW")
    assert labels.index("SOW") < labels.index("LPSY")
    utad = next(item for item in distribution["events"] if item["event"] == "UTAD")
    sow = next(item for item in distribution["events"] if item["event"] == "SOW")
    assert utad["confirmation_state"] == "follow_through_confirmed"
    assert sow["confirmation_state"] == "follow_through_confirmed"


def test_single_excursion_does_not_reset_frozen_range() -> None:
    frame = _wyckoff_sequence_frame().iloc[:80].copy()
    before = detect_wyckoff_structure(frame)
    extra = frame.iloc[-1].copy()
    extra["datetime"] = frame["datetime"].iloc[-1] + pd.Timedelta(days=1)
    extra[["open", "high", "low", "close"]] = [12.2, 12.8, 12.1, 12.6]
    after = detect_wyckoff_structure(pd.concat([frame, extra.to_frame().T], ignore_index=True))

    assert after["range"]["start_timestamp"] == before["range"]["start_timestamp"]
    assert after["range"]["support"] == before["range"]["support"]
    assert after["range"]["resistance"] == before["range"]["resistance"]


def test_wyckoff_history_samples_each_range_lifecycle_once(monkeypatch) -> None:
    frame = _wyckoff_sequence_frame().copy()

    def fake_detect(history: pd.DataFrame) -> dict[str, object]:
        candidate = {
            "structure": "accumulation",
            "direction": "up",
            "phase": "C",
            "current_event": "Spring",
            "events": [],
        }
        return {
            "status": "active",
            "range": {
                "support": 10.0,
                "resistance": 12.0,
                "start_timestamp": "2025-01-01T00:00:00",
            },
            "alternatives": [candidate],
        }

    def fake_projection(*_args) -> dict[str, object]:
        return {
            "confirmation": 12.0,
            "invalidation": 9.0,
            "target_zone": [12.5, 13.0],
            "confirmation_status": "waiting",
        }

    monkeypatch.setattr("app.wyckoff.evaluation.detect_wyckoff_structure", fake_detect)
    monkeypatch.setattr("app.wyckoff.evaluation.project_wyckoff", fake_projection)

    result = evaluate_wyckoff_history(frame, "up", lookahead_bars=10)

    assert result["sample_count"] == 1
    assert "每个冻结交易区间" in result["sampling_policy"]


def test_phase_c_projection_uses_spring_extreme_for_invalidation() -> None:
    frame = _wyckoff_sequence_frame().iloc[:80].copy()
    frame.loc[76, ["open", "high", "low", "close", "volume"]] = [
        10.8, 11.4, 10.5, 11.0, 100.0
    ]
    frame.loc[78, ["open", "high", "low", "close", "volume"]] = [
        10.8, 11.4, 10.5, 11.0, 100.0
    ]
    structure = detect_wyckoff_structure(frame)
    accumulation = next(
        item for item in structure["alternatives"] if item["structure"] == "accumulation"
    )

    projection = project_wyckoff(frame, structure | accumulation)
    spring = next(item for item in accumulation["events"] if item["event"] == "Spring")

    assert projection["confirmation_status"] == "waiting"
    assert projection["invalidation_basis"] == "Spring 低点"
    assert projection["invalidation"] < spring["low"]


def test_wyckoff_same_bar_target_and_invalidation_is_conservative() -> None:
    future = pd.DataFrame(
        [{"close": 8.8, "low": 8.5, "high": 13.5}]
    )
    projection = {
        "confirmation": 11.0,
        "invalidation": 9.0,
        "target_zone": [12.0, 13.0],
        "confirmation_status": "confirmed",
    }

    outcome = _evaluate_lifecycle(future, projection, "up")

    assert outcome["resolved"] is True
    assert outcome["target_reached"] is False


def test_wyckoff_decision_context_stays_neutral_until_candidate_is_clear() -> None:
    ambiguous = wyckoff_decision_context(
        {"status": "active", "direction": "up", "phase": "D", "ambiguous": True},
        "long_trigger",
    )
    conflicting = wyckoff_decision_context(
        {"status": "active", "direction": "down", "phase": "D", "ambiguous": False},
        "long_trigger",
    )

    assert ambiguous["alignment"] == "neutral"
    assert conflicting["alignment"] == "conflicting"
    assert "降低执行信心" in conflicting["note"]
