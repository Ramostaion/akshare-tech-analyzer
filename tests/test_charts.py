from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from app.charts import (
    BUY_TRIGGER_COLOR,
    WAVE_COLOR,
    _add_buy_signal_markers,
    _add_gann_overlay,
    _add_wave_overlay,
    _add_wave_scenarios,
    _add_wyckoff_overlay,
    _default_chart_x_range,
    _default_price_y_range,
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
    assert trace.meta["algorithm"] == "wave"


def test_missing_wave_candidate_adds_grouped_chart_note() -> None:
    figure = make_subplots(rows=1, cols=1)

    _add_wave_overlay(figure, {"candidates": []})

    note = figure.layout.annotations[-1]
    assert note.name == "algorithm-wave-empty-note"
    assert "没有满足硬规则" in note.text


def test_wave_scenarios_show_continuation_zone_and_invalidation(market_frame) -> None:
    figure = make_subplots(rows=1, cols=1)
    wave = {
        "candidates": [
            {
                "projection": {
                    "primary_zone": [18.5, 20.0],
                    "confirmation": 16.8,
                    "invalidation": 13.2,
                }
            }
        ]
    }

    _add_wave_scenarios(figure, market_frame, wave)

    assert [trace.name for trace in figure.data] == [
        "浪形情景 1：确认后延续",
        "浪形情景 2：尝试失败后失效",
        "浪形确认位",
        "浪形失效位",
    ]
    assert list(figure.data[0].y)[-1] == 19.25
    assert figure.data[0].line.width == 4
    assert figure.data[0].line.dash == "solid"
    assert figure.data[0].marker.size == 8
    assert len(figure.data[0].y) >= 3
    assert list(figure.data[1].y)[-1] == 13.2
    assert list(figure.data[2].y)[-1] == 16.8
    assert list(figure.data[3].y)[-1] == 13.2
    assert "不预测具体价格或时间" in figure.data[0].hovertemplate
    assert len(figure.layout.shapes) == 1
    assert figure.layout.shapes[0].y0 == 18.5
    assert figure.layout.shapes[0].y1 == 20.0
    assert "不代表时间" in figure.layout.annotations[-1].text
    assert figure.layout.shapes[0].name.startswith("algorithm-wave")
    latest = pd.Timestamp(market_frame["datetime"].iloc[-1])
    visible_start = pd.Timestamp(market_frame["datetime"].iloc[-220])
    minimum_end = latest + (latest - visible_start) * 0.15
    assert pd.Timestamp(figure.data[0].x[-1]) >= minimum_end


def test_waiting_wave_adds_atr_corridor_and_neutral_scenario(market_frame) -> None:
    frame = market_frame.copy()
    current = float(frame["close"].iloc[-1])
    frame["ATR14"] = 0.5
    figure = make_subplots(rows=1, cols=1)
    wave = {
        "candidates": [
            {
                "current_state": "waiting",
                "projection": {
                    "primary_zone": [current + 2, current + 3],
                    "confirmation": current + 1,
                    "invalidation": current - 1,
                    "path_direction": "up",
                },
            }
        ]
    }

    _add_wave_scenarios(figure, frame, wave)

    names = [trace.name for trace in figure.data]
    assert "情景 1 ATR 不确定性走廊" in names
    assert "浪形情景 3：确认前震荡等待" in names
    corridor = next(trace for trace in figure.data if trace.name == "情景 1 ATR 不确定性走廊")
    assert corridor.fill == "tonexty"


def test_gann_overlay_is_grouped_and_hidden_by_default(market_frame) -> None:
    frame = add_indicators(market_frame)
    latest = frame["datetime"].iloc[-1]
    anchor_time = frame["datetime"].iloc[-20]
    gann = {
        "status": "active",
        "direction": "up",
        "anchor": {
            "timestamp": anchor_time,
            "confirmed_at": frame["datetime"].iloc[-17],
            "price": 16.0,
        },
        "fan_lines": [
            {
                "label": label,
                "start_time": anchor_time,
                "start_price": 16.0,
                "current_time": latest,
                "current_price": float(frame["close"].iloc[-1]),
                "end_time": latest + pd.Timedelta(days=24),
                "end_price": end_price,
            }
            for label, end_price in (("2×1", 20.0), ("1×1", 18.0), ("1×2", 17.0))
        ],
        "price_levels": [
            {"label": "50.0%", "price": 18.0},
            {"label": "100.0%", "price": 20.0},
        ],
        "time_cycles": [{"bars": 24, "datetime": latest + pd.Timedelta(days=8)}],
        "confirmation": 18.0,
        "invalidation": 16.0,
    }
    figure = make_subplots(rows=1, cols=1)

    _add_gann_overlay(figure, frame, gann)

    names = [trace.name for trace in figure.data]
    assert "江恩自动确认锚点" in names
    assert "江恩后续趋势 1×1" in names
    assert "江恩价格分割" in names
    assert "江恩时间观察窗" in names
    gann_traces = [
        trace for trace in figure.data if trace.meta and trace.meta["algorithm"] == "gann"
    ]
    assert all(trace.visible is False for trace in gann_traces)
    trends = [trace for trace in gann_traces if str(trace.name).startswith("江恩后续趋势")]
    assert all(pd.Timestamp(trace.x[0]) == pd.Timestamp(latest) for trace in trends)
    assert all(float(trace.y[0]) == float(frame["close"].iloc[-1]) for trace in trends)
    minimum_end = pd.Timestamp(latest) + (
        pd.Timestamp(latest) - pd.Timestamp(frame["datetime"].iloc[-220])
    ) * 0.15
    assert all(pd.Timestamp(trace.x[-1]) >= minimum_end for trace in trends)
    assert all(float(trace.y[-1]) == end_price for trace, end_price in zip(
        trends,
        (20.0, 18.0, 17.0),
        strict=True,
    ))
    padding = next(trace for trace in figure.data if trace.name == "江恩未来显示空间")
    assert padding.opacity == 0
    assert padding.meta is None


def test_default_daily_view_focuses_recent_bars_and_reserves_projection_space(
    market_frame,
) -> None:
    start, end = _default_chart_x_range(market_frame, "daily")
    latest = pd.Timestamp(market_frame["datetime"].iloc[-1])

    assert start == pd.Timestamp(market_frame["datetime"].iloc[-220])
    assert end > latest


def test_default_price_range_ignores_old_extremes_but_includes_scenarios(
    market_frame,
) -> None:
    frame = market_frame.copy()
    frame.loc[:50, "low"] = 1.0
    frame.loc[:50, "high"] = 100.0
    wave = {
        "candidates": [
            {
                "pivots": [],
                "projection": {
                    "primary_zone": [20.0, 22.0],
                    "confirmation": 18.0,
                    "invalidation": 13.0,
                },
            }
        ]
    }

    lower, upper = _default_price_y_range(frame, "daily", wave, {})

    assert 1.0 < lower < 13.0
    assert 22.0 < upper < 100.0


def test_wyckoff_overlay_is_complete_and_hidden_by_default(market_frame) -> None:
    latest = market_frame["datetime"].iloc[-1]
    wyckoff = {
        "status": "active",
        "structure": "accumulation",
        "direction": "up",
        "phase": "C",
        "range": {"support": 14.0, "resistance": 18.0},
        "events": [
            {
                "event": "Spring",
                "timestamp": latest,
                "price": 15.0,
                "volume_ratio": 1.2,
                "spread_atr": 1.1,
            }
        ],
        "projection": {
            "confirmation": 18.0,
            "invalidation": 13.5,
            "target_zone": [20.0, 22.0],
        },
    }
    figure = make_subplots(rows=1, cols=1)

    _add_wyckoff_overlay(figure, market_frame, wyckoff)

    names = [trace.name for trace in figure.data]
    assert "威科夫事件" in names
    assert "威科夫情景 1：确认后延续" in names
    assert "威科夫情景 2：结构失败" in names
    assert all(trace.meta["algorithm"] == "wyckoff" for trace in figure.data)
    assert all(trace.visible is False for trace in figure.data)
    assert figure.layout.shapes[-1].name == "algorithm-wyckoff-range"
    assert figure.layout.shapes[-1].visible is False
    assert figure.layout.annotations[-1].name == "algorithm-wyckoff-phase"
    assert figure.layout.annotations[-1].visible is False
