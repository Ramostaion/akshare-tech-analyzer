from __future__ import annotations

import pandas as pd

from app.research import parameter_sweep, time_series_split, walk_forward_splits


def test_time_split_is_ordered_without_shuffle() -> None:
    split = time_series_split(100)

    assert split.train == (0, 60)
    assert split.validation == (60, 80)
    assert split.out_of_sample == (80, 100)


def test_walk_forward_never_crosses_time_boundaries() -> None:
    splits = walk_forward_splits(120, 60, 20, 20, step=10)

    assert splits
    for split in splits:
        assert split.train[1] == split.validation[0]
        assert split.validation[1] == split.out_of_sample[0]
        assert split.out_of_sample[1] <= 120


def test_parameter_sweep_receives_only_training_copy() -> None:
    data = pd.DataFrame({"value": range(10)})
    seen = []

    def evaluator(training: pd.DataFrame, threshold: float):
        seen.append((len(training), int(training["value"].max())))
        training.loc[:, "value"] = -1
        return {"sample": len(training), "expectancy_r": threshold}

    result = parameter_sweep(data.iloc[:6], "threshold", [1.0, 1.5], evaluator)

    assert seen == [(6, 5), (6, 5)]
    assert data["value"].iloc[-1] == 9
    assert result[1]["value"] == 1.5
