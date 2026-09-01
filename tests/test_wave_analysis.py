from __future__ import annotations

from copy import deepcopy

import pandas as pd

import app.wave as wave_module


def test_completed_candidate_advances_zone_instead_of_disappearing(monkeypatch) -> None:
    candidate = {
        "pattern": "impulse",
        "current_wave": 5,
        "status": "completed",
        "direction": "up",
        "structural_fit": 0.8,
        "confidence": 0.8,
        "pivots": [{"position": 1, "timestamp": "2024-01-02T00:00:00"}],
        "projection": {
            "primary_zone": [9.0, 10.0],
            "target_zones": [
                {"label": "第一观察区", "zone": [9.0, 10.0]},
                {"label": "第二观察区", "zone": [8.0, 9.0]},
            ],
            "path_direction": "down",
            "confirmation": 10.5,
            "invalidation": 12.0,
        },
    }
    monkeypatch.setattr(wave_module, "confirmed_zigzag_pivots", lambda *_args: [object()])
    monkeypatch.setattr(
        wave_module,
        "find_wave_candidates",
        lambda *_args, **_kwargs: [deepcopy(candidate)],
    )
    monkeypatch.setattr(wave_module, "evaluate_candidate_history", lambda *_args: {})
    frame = pd.DataFrame({"close": [8.5]})

    result = wave_module.analyze_wave_candidates(frame)

    assert len(result["candidates"]) == 1
    retained = result["candidates"][0]
    assert retained["projection"]["zone_stage"] == 2
    assert retained["projection"]["primary_zone"] == [8.0, 9.0]
    assert retained["current_state"] == "in_target_zone"
