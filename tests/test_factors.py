from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.factors import FACTOR_COLUMNS, build_factors
from app.indicators import add_indicators


def test_factor_layer_contains_required_continuous_features(market_frame) -> None:
    factors = build_factors(add_indicators(market_frame))

    assert tuple(factors.columns) == FACTOR_COLUMNS
    assert factors["return_20"].iloc[:20].isna().all()
    assert factors["return_20"].iloc[20] == pytest.approx(
        market_frame["close"].iloc[20] / market_frame["close"].iloc[0] - 1
    )
    assert factors.replace([np.inf, -np.inf], np.nan).notna().sum().sum() > 0


def test_factors_do_not_change_when_future_rows_are_appended(market_frame) -> None:
    enriched = add_indicators(market_frame)
    cutoff = 220
    prefix = build_factors(enriched.iloc[:cutoff].copy())
    complete = build_factors(enriched)

    pd.testing.assert_series_equal(prefix.iloc[-1], complete.iloc[cutoff - 1], check_names=False)


def test_volume_factor_uses_only_prior_volume(market_frame) -> None:
    enriched = add_indicators(market_frame)
    factors = build_factors(enriched)
    position = 40
    expected = enriched["volume"].iloc[position] / enriched["volume"].iloc[
        position - 20 : position
    ].mean()

    assert factors["volume_ratio_20"].iloc[position] == pytest.approx(expected)
