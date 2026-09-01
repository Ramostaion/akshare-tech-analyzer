from __future__ import annotations

import pandas as pd

from app.wave.evaluation import _evaluate_projection, scenario_state


def _projection() -> dict[str, object]:
    return {
        "primary_zone": [12.0, 13.0],
        "confirmation": 11.0,
        "invalidation": 9.0,
        "path_direction": "up",
    }


def test_projection_replay_confirms_before_target() -> None:
    future = pd.DataFrame(
        {
            "open": [10.2, 11.3],
            "high": [11.2, 12.2],
            "low": [10.0, 11.1],
            "close": [11.1, 12.0],
        }
    )

    outcome, bars = _evaluate_projection(future, 10.0, _projection())

    assert outcome == "target_first"
    assert bars == 2


def test_projection_replay_uses_conservative_same_bar_order() -> None:
    future = pd.DataFrame(
        {
            "open": [10.2],
            "high": [12.4],
            "low": [8.6],
            "close": [8.8],
        }
    )

    outcome, bars = _evaluate_projection(future, 11.2, _projection())

    assert outcome == "invalidation_first"
    assert bars == 1


def test_close_confirmation_cannot_use_same_bar_target_touch() -> None:
    future = pd.DataFrame(
        {
            "open": [10.2],
            "high": [12.4],
            "low": [10.0],
            "close": [11.2],
        }
    )

    outcome, bars = _evaluate_projection(future, 10.0, _projection())

    assert outcome == "unresolved"
    assert bars is None


def test_scenario_state_uses_close_only() -> None:
    projection = _projection()

    assert scenario_state(10.5, projection) == "waiting"
    assert scenario_state(11.2, projection) == "confirmed"
    assert scenario_state(12.1, projection) == "in_target_zone"
    assert scenario_state(13.1, projection) == "target_reached"
    assert scenario_state(8.9, projection) == "invalidated"
