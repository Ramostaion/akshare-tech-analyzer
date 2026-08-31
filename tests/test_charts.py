from __future__ import annotations

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from app.charts import (
    BUY_TRIGGER_COLOR,
    WAVE_COLOR,
    _add_buy_signal_markers,
    _add_wave_overlay,
    _add_wave_scenarios,
)
from app.factors import build_factors
from app.indicators import add_indicators
from app.signals import create_signal


def test_buy_triggers_are_marked_and_exit_signals_are_excluded(market_frame) -> None:
    enriched = add_indicators(market_frame)
    factors = build_factors(enriched)
    position = len(enriched) - 1
    buy_signal = create_signal(
        "600011", enriched, factors, position, "trend_pullback", "UPTREND"
    )
    exit_signal = create_signal(
        "600011", enriched, factors, position, "trend_breakdown", "DOWNTREND"
    )
    figure = make_subplots(rows=1, cols=1)

    _add_buy_signal_markers(figure, enriched, [buy_signal, exit_signal])

    assert len(figure.data) == 1
    trace = figure.data[0]
    assert isinstance(trace, go.Scatter)
    assert trace.name == "历史买入 Trigger"
    assert trace.marker.color == BUY_TRIGGER_COLOR
    assert trace.marker.symbol == "triangle-up"
    assert len(trace.x) == 1
    assert "趋势回踩" in trace.text[0]
    assert "下一根 K 线执行" in trace.text[0]


def test_top_wave_candidate_is_connected_and_labeled() -> None:
    figure = make_subplots(rows=1, cols=1)
    pivots = [
        {
            "kind": kind,
            "position": position,
            "confirmation_position": position + 3,
            "timestamp": f"2024-01-{position + 1:02d}T00:00:00",
            "price": price,
        }
        for kind, position, price in (
            ("low", 0, 10),
            ("high", 2, 14),
            ("low", 4, 12),
            ("high", 7, 20),
            ("low", 9, 15),
            ("high", 12, 22),
        )
    ]
    wave = {
        "candidates": [
            {"pattern": "impulse", "confidence": 0.82, "pivots": pivots},
            {"pattern": "abc_zigzag", "confidence": 0.6, "pivots": pivots[:4]},
        ]
    }

    _add_wave_overlay(figure, wave)

    assert len(figure.data) == 1
    trace = figure.data[0]
    assert trace.name == "浪形候选 Top-1"
    assert trace.line.color == WAVE_COLOR
    assert list(trace.text) == ["0", "1", "2", "3", "4", "5"]
    assert "推动五浪 · 3浪" in trace.customdata[3]
    assert "右侧确认滞后：3根 K 线" in trace.customdata[3]


def test_wave_scenarios_show_continuation_zone_and_invalidation(market_frame) -> None:
    figure = make_subplots(rows=1, cols=1)
    wave = {
        "candidates": [
            {
                "projection": {
                    "primary_zone": [18.5, 20.0],
                    "invalidation": 13.2,
                }
            }
        ]
    }

    _add_wave_scenarios(figure, market_frame, wave)

    assert [trace.name for trace in figure.data] == [
        "浪形情景 A：延续",
        "浪形情景 B：失效",
    ]
    assert list(figure.data[0].y)[-1] == 19.25
    assert list(figure.data[1].y)[-1] == 13.2
    assert "不预测到达时间" in figure.data[0].hovertemplate
    assert len(figure.layout.shapes) == 1
    assert figure.layout.shapes[0].y0 == 18.5
    assert figure.layout.shapes[0].y1 == 20.0
