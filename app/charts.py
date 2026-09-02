"""Plotly 交互 K 线图构建。"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

from app.models import AnalyzeRequest
from app.signals import TradingSignal

CN_UP_COLOR = "#ef4444"
CN_DOWN_COLOR = "#22c55e"
GLOBAL_UP_COLOR = "#22c55e"
GLOBAL_DOWN_COLOR = "#ef4444"
GRID_COLOR = "rgba(148, 163, 184, 0.13)"
TEXT_COLOR = "#dbe4ee"
BUY_TRIGGER_COLOR = "#facc15"
WAVE_COLOR = "#22d3ee"
WAVE_CONTINUATION_COLOR = "#a3e635"
WAVE_INVALIDATION_COLOR = "#fb7185"
WAVE_CONFIRMATION_COLOR = "#fbbf24"
WAVE_NEUTRAL_COLOR = "#94a3b8"
GANN_COLOR = "#c084fc"
GANN_FAST_COLOR = "#e879f9"
GANN_SLOW_COLOR = "#818cf8"

SETUP_LABELS = {
    "trend_pullback": "趋势回踩",
    "breakout": "突破",
    "support_reversal": "支撑反转",
}

WAVE_PATTERN_LABELS = {
    "impulse": "推动五浪",
    "unfinished_impulse": "未完成推动浪",
    "abc_zigzag": "ABC锯齿调整",
    "unfinished_abc": "未完成ABC调整",
}

PLOTLY_UNDO_POST_SCRIPT = r"""
(function (graph) {
  if (!graph || graph.__akshareShapeUndo) return;
  const cloneShapes = () => JSON.parse(JSON.stringify(graph.layout.shapes || []));
  const state = {
    history: [cloneShapes()],
    applying: false,
    timer: null
  };
  graph.__akshareShapeUndo = state;

  const commit = () => {
    state.timer = null;
    const current = cloneShapes();
    const previous = state.history[state.history.length - 1];
    if (JSON.stringify(current) !== JSON.stringify(previous)) {
      state.history.push(current);
      if (state.history.length > 50) state.history.shift();
    }
  };
  state.commit = commit;

  graph.on("plotly_relayout", (changes) => {
    if (state.applying) return;
    const shapeChanged = Object.keys(changes || {}).some(
      (key) => key === "shapes" || key.startsWith("shapes[")
    );
    if (!shapeChanged) return;
    clearTimeout(state.timer);
    state.timer = setTimeout(commit, 80);
  });

  window.__akshareActivePlot = graph;
  if (window.__akshareUndoHandlerInstalled) return;
  window.__akshareUndoHandlerInstalled = true;
  document.addEventListener("keydown", (event) => {
    if (!(event.ctrlKey || event.metaKey) || event.shiftKey || event.key.toLowerCase() !== "z") {
      return;
    }
    const target = event.target;
    if (
      target instanceof HTMLInputElement ||
      target instanceof HTMLTextAreaElement ||
      target instanceof HTMLSelectElement ||
      target?.isContentEditable
    ) {
      return;
    }
    const activeGraph = window.__akshareActivePlot;
    const activeState = activeGraph?.__akshareShapeUndo;
    if (!activeGraph || !activeState) return;
    if (activeState.timer) {
      clearTimeout(activeState.timer);
      activeState.commit();
    }
    if (activeState.history.length <= 1) return;
    event.preventDefault();
    activeState.history.pop();
    activeState.applying = true;
    const previous = JSON.parse(
      JSON.stringify(activeState.history[activeState.history.length - 1])
    );
    Plotly.relayout(activeGraph, {shapes: previous}).finally(() => {
      activeState.applying = false;
    });
  });
})(document.getElementById("{plot_id}"));
"""


def _add_main_overlays(
    figure: go.Figure,
    frame: pd.DataFrame,
    levels: dict[str, Any],
    request: AnalyzeRequest,
) -> None:
    if request.show_ma:
        colors = {
            "MA5": "#fbbf24",
            "MA10": "#38bdf8",
            "MA20": "#f472b6",
            "MA60": "#a78bfa",
            "MA120": "#fb923c",
            "MA250": "#94a3b8",
        }
        for column, color in colors.items():
            if column in frame and frame[column].notna().any():
                figure.add_trace(
                    go.Scatter(
                        x=frame["datetime"],
                        y=frame[column],
                        name=column,
                        mode="lines",
                        line={"width": 1.1, "color": color},
                        hovertemplate=f"{column}: %{{y:.3f}}<extra></extra>",
                    ),
                    row=1,
                    col=1,
                )
    if request.show_boll and frame["BOLL_MID"].notna().any():
        for column, dash in (("BOLL_UPPER", "dot"), ("BOLL_MID", "solid"), ("BOLL_LOWER", "dot")):
            figure.add_trace(
                go.Scatter(
                    x=frame["datetime"],
                    y=frame[column],
                    name="BOLL(20,2)" if column == "BOLL_MID" else column,
                    mode="lines",
                    line={"width": 1, "color": "#67e8f9", "dash": dash},
                    opacity=0.72,
                    legendgroup="BOLL",
                    showlegend=column == "BOLL_MID",
                    hovertemplate=f"{column}: %{{y:.3f}}<extra></extra>",
                ),
                row=1,
                col=1,
            )
    if request.show_levels:
        for kind, color, label in (
            ("supports", "rgba(34,197,94,0.14)", "S"),
            ("resistances", "rgba(239,68,68,0.14)", "R"),
        ):
            for index, level in enumerate(levels.get(kind, []), start=1):
                figure.add_hrect(
                    y0=level["lower"],
                    y1=level["upper"],
                    fillcolor=color,
                    line_width=0,
                    row=1,
                    col=1,
                    annotation_text=f"{label}{index} {level['price']:.3f}",
                    annotation_position="left" if index % 2 else "right",
                    annotation_font={"size": 9, "color": TEXT_COLOR},
                )


def _add_macd_events(
    figure: go.Figure, frame: pd.DataFrame, up_color: str, down_color: str
) -> None:
    difference = frame["DIF"] - frame["DEA"]
    previous = difference.shift(1)
    events = frame.loc[
        ((difference > 0) & (previous <= 0)) | ((difference < 0) & (previous >= 0))
    ].tail(8)
    if events.empty:
        return
    labels = ["MACD金叉" if row.DIF > row.DEA else "MACD死叉" for row in events.itertuples()]
    colors = [up_color if label == "MACD金叉" else down_color for label in labels]
    symbols = ["triangle-up" if label == "MACD金叉" else "triangle-down" for label in labels]
    y_values = [
        row.low * 0.985 if label == "MACD金叉" else row.high * 1.015
        for row, label in zip(events.itertuples(), labels, strict=True)
    ]
    figure.add_trace(
        go.Scatter(
            x=events["datetime"],
            y=y_values,
            mode="markers",
            name="MACD事件",
            text=labels,
            marker={"color": colors, "symbol": symbols, "size": 9},
            hovertemplate="%{text}<extra></extra>",
        ),
        row=1,
        col=1,
    )


def _add_buy_signal_markers(
    figure: go.Figure,
    frame: pd.DataFrame,
    signals: list[TradingSignal],
) -> None:
    """在确认 Trigger 的 K 线下方标记历史做多信号。"""
    buy_signals = [signal for signal in signals if signal.direction == "long"]
    if not buy_signals:
        return

    positions = {
        pd.Timestamp(timestamp): position
        for position, timestamp in enumerate(frame["datetime"])
    }
    x_values: list[pd.Timestamp] = []
    y_values: list[float] = []
    hover_text: list[str] = []
    for signal in buy_signals:
        timestamp = pd.Timestamp(signal.timestamp)
        position = positions.get(timestamp)
        if position is None:
            continue
        bar = frame.iloc[position]
        x_values.append(timestamp)
        y_values.append(float(bar["low"]) * 0.985)
        setup_label = SETUP_LABELS.get(signal.setup, signal.setup)
        hover_text.append(
            f"买入 Trigger（收盘确认）<br>日期：{timestamp:%Y-%m-%d %H:%M}"
            f"<br>类型：{setup_label}<br>质量分：{signal.score:.1f}/100"
            f"<br>收盘参考价：{signal.entry_reference:.3f}"
            "<br>默认最早在下一根 K 线执行"
        )
    if not x_values:
        return

    figure.add_trace(
        go.Scatter(
            x=x_values,
            y=y_values,
            mode="markers",
            name="历史买入 Trigger",
            text=hover_text,
            marker={
                "color": BUY_TRIGGER_COLOR,
                "symbol": "triangle-up",
                "size": 12,
                "line": {"color": "#713f12", "width": 1},
            },
            hovertemplate="%{text}<extra></extra>",
        ),
        row=1,
        col=1,
    )


def _wave_point_labels(pattern: str, point_count: int) -> list[str]:
    labels = (
        ["起点", "A", "B", "C"]
        if pattern in {"abc_zigzag", "unfinished_abc"}
        else ["0", "1", "2", "3", "4", "5"]
    )
    return labels[:point_count]


def _add_wave_overlay(figure: go.Figure, wave: dict[str, Any]) -> None:
    """将最高置信度候选的已确认 Pivot 连线并标注浪名。"""
    candidates = wave.get("candidates", [])
    if not candidates:
        return
    candidate = candidates[0]
    pivots = candidate.get("pivots", [])
    if len(pivots) < 2:
        return

    pattern = str(candidate.get("pattern", ""))
    pattern_label = WAVE_PATTERN_LABELS.get(pattern, pattern)
    point_labels = _wave_point_labels(pattern, len(pivots))
    x_values = [pd.Timestamp(item["timestamp"]) for item in pivots]
    y_values = [float(item["price"]) for item in pivots]
    text_positions = [
        "bottom center" if item.get("kind") == "low" else "top center" for item in pivots
    ]
    structural_fit = float(
        candidate.get("structural_fit", candidate.get("confidence", 0))
    ) * 100
    scale = str(candidate.get("scale", "标准尺度"))
    status = "进行中" if candidate.get("status") == "developing" else "已完成"
    hover_text = []
    for label, pivot in zip(point_labels, pivots, strict=True):
        confirmation_lag = int(pivot["confirmation_position"]) - int(pivot["position"])
        wave_name = label if label == "起点" else f"{label}浪"
        timestamp = pd.Timestamp(pivot["timestamp"])
        hover_text.append(
            f"{pattern_label} · {wave_name}<br>日期：{timestamp:%Y-%m-%d %H:%M}"
            f"<br>价格：{float(pivot['price']):.3f}<br>结构匹配度：{structural_fit:.1f}/100"
            f"（非概率）<br>状态：{status} · {scale}"
            f"<br>右侧确认滞后：{confirmation_lag}根 K 线"
        )
    figure.add_trace(
        go.Scatter(
            x=x_values,
            y=y_values,
            mode="lines+markers+text",
            name="浪形候选 Top-1",
            meta={"algorithm": "wave"},
            legendgroup="algorithm-wave",
            text=point_labels,
            textposition=text_positions,
            textfont={"color": WAVE_COLOR, "size": 12},
            line={"color": WAVE_COLOR, "width": 2, "dash": "dash"},
            marker={
                "color": "#0b1017",
                "size": 8,
                "line": {"color": WAVE_COLOR, "width": 2},
            },
            customdata=hover_text,
            hovertemplate="%{customdata}<extra></extra>",
        ),
        row=1,
        col=1,
    )


def _add_wave_scenarios(
    figure: go.Figure,
    frame: pd.DataFrame,
    wave: dict[str, Any],
) -> None:
    """从最新 K 线绘制延续与失效两条非时间预测情景。"""
    candidates = wave.get("candidates", [])
    if not candidates or frame.empty:
        return
    candidate = candidates[0]
    projection = candidate.get("projection", {})
    target_zone = projection.get("primary_zone", [])
    invalidation = projection.get("invalidation")
    confirmation = projection.get("confirmation")
    if len(target_zone) != 2 or invalidation is None:
        return

    datetimes = pd.to_datetime(frame["datetime"])
    intervals = datetimes.diff().dropna()
    if intervals.empty:
        return
    interval = intervals.median()
    if interval <= pd.Timedelta(0):
        return

    current_time = pd.Timestamp(datetimes.iloc[-1])
    future_time = current_time + interval * 8
    zone_lower, zone_upper = sorted(float(value) for value in target_zone)
    target_midpoint = (zone_lower + zone_upper) / 2
    current_price = float(frame["close"].iloc[-1])
    invalidation_price = float(invalidation)
    confirmation_price = float(confirmation) if confirmation is not None else None
    common_x = [current_time, future_time]
    target_label = str(projection.get("target_label", "条件目标观察区"))
    invalidation_label = str(projection.get("invalidation_label", "候选失效位"))
    invalidation_rule = str(
        projection.get("invalidation_rule", "触及该位置后撤销候选并重新计浪")
    )
    confirmation_label = str(projection.get("confirmation_label", "路径确认位"))
    confirmation_rule = str(
        projection.get("confirmation_rule", "满足确认条件后再观察目标区")
    )

    path_is_up = projection.get("path_direction") == "up"
    if projection.get("path_direction") not in {"up", "down"}:
        path_is_up = target_midpoint >= current_price
    zone_entry = zone_lower if path_is_up else zone_upper
    confirmation_pending = confirmation_price is not None and (
        confirmation_price > current_price if path_is_up else confirmation_price < current_price
    )
    if confirmation_pending:
        path_1_x = [
            current_time,
            current_time + interval * 3,
            current_time + interval * 6,
            future_time,
        ]
        path_1_y = [current_price, confirmation_price, zone_entry, target_midpoint]
        failed_probe = confirmation_price
    else:
        path_1_x = [current_time, current_time + interval * 5, future_time]
        path_1_y = [current_price, zone_entry, target_midpoint]
        failed_probe = current_price + (zone_entry - current_price) * 0.35
    path_2_x = [current_time, current_time + interval * 3, current_time + interval * 7]
    path_2_y = [current_price, failed_probe, invalidation_price]

    atr_value = frame["ATR14"].iloc[-1] if "ATR14" in frame else None
    if pd.notna(atr_value) and float(atr_value) > 0:
        atr_value = float(atr_value)
        widths = [
            atr_value * (0.1 + 0.65 * index / max(1, len(path_1_y) - 1))
            for index in range(len(path_1_y))
        ]
        corridor_lower = [value - width for value, width in zip(path_1_y, widths, strict=True)]
        corridor_upper = [value + width for value, width in zip(path_1_y, widths, strict=True)]
        figure.add_trace(
            go.Scatter(
                x=path_1_x,
                y=corridor_lower,
                mode="lines",
                name="情景 1 波动走廊下界",
                meta={"algorithm": "wave"},
                legendgroup="algorithm-wave",
                line={"width": 0},
                showlegend=False,
                hoverinfo="skip",
            ),
            row=1,
            col=1,
        )
        figure.add_trace(
            go.Scatter(
                x=path_1_x,
                y=corridor_upper,
                mode="lines",
                name="情景 1 ATR 不确定性走廊",
                meta={"algorithm": "wave"},
                legendgroup="algorithm-wave",
                line={"width": 0},
                fill="tonexty",
                fillcolor="rgba(163,230,53,0.08)",
                showlegend=False,
                hoverinfo="skip",
            ),
            row=1,
            col=1,
        )

    figure.add_trace(
        go.Scatter(
            x=path_1_x,
            y=path_1_y,
            mode="lines+markers+text",
            name="浪形情景 1：确认后延续",
            meta={"algorithm": "wave"},
            legendgroup="algorithm-wave",
            text=[""] * (len(path_1_x) - 1) + ["情景 1"],
            textposition="top center",
            textfont={"color": WAVE_CONTINUATION_COLOR, "size": 11},
            line={"color": WAVE_CONTINUATION_COLOR, "width": 2.5, "dash": "dash"},
            marker={"color": WAVE_CONTINUATION_COLOR, "size": 6},
            hovertemplate=(
                f"情景 1：确认后向{target_label}推进"
                f"<br>目标区：{zone_lower:.3f}–{zone_upper:.3f}"
                "<br>折线节点与横向距离均为结构示意，不预测具体价格或时间"
                "<extra></extra>"
            ),
        ),
        row=1,
        col=1,
    )
    if confirmation_price is not None and (
        confirmation_pending or candidate.get("current_state") == "waiting"
    ):
        neutral_midpoint = (confirmation_price + invalidation_price) / 2
        neutral_x = [
            current_time,
            current_time + interval * 2,
            current_time + interval * 4,
            current_time + interval * 6,
        ]
        neutral_y = [
            current_price,
            (current_price + neutral_midpoint) / 2,
            current_price,
            neutral_midpoint,
        ]
        figure.add_trace(
            go.Scatter(
                x=neutral_x,
                y=neutral_y,
                mode="lines+markers+text",
                name="浪形情景 3：确认前震荡等待",
                meta={"algorithm": "wave"},
                legendgroup="algorithm-wave",
                text=["", "", "", "情景 3"],
                textposition="bottom center",
                textfont={"color": WAVE_NEUTRAL_COLOR, "size": 11},
                line={"color": WAVE_NEUTRAL_COLOR, "width": 1.8, "dash": "dot"},
                marker={"color": WAVE_NEUTRAL_COLOR, "size": 5},
                hovertemplate=(
                    "情景 3：价格在确认位与失效位之间反复，候选继续观察"
                    "<br>折线节点与横向距离均为结构示意，不预测具体价格或时间"
                    "<extra></extra>"
                ),
            ),
            row=1,
            col=1,
        )
    figure.add_trace(
        go.Scatter(
            x=path_2_x,
            y=path_2_y,
            mode="lines+markers+text",
            name="浪形情景 2：尝试失败后失效",
            meta={"algorithm": "wave"},
            legendgroup="algorithm-wave",
            text=["", "", "情景 2"],
            textposition="bottom center",
            textfont={"color": WAVE_INVALIDATION_COLOR, "size": 11},
            line={"color": WAVE_INVALIDATION_COLOR, "width": 2.5, "dash": "dash"},
            marker={"color": WAVE_INVALIDATION_COLOR, "size": 6},
            hovertemplate=(
                f"情景 2：确认尝试失败后转向{invalidation_label}"
                f"<br>结构边界：{invalidation_price:.3f}<br>{invalidation_rule}"
                "<br>折线节点与横向距离均为结构示意，不预测具体价格或时间"
                "<extra></extra>"
            ),
        ),
        row=1,
        col=1,
    )
    if confirmation_price is not None:
        figure.add_trace(
            go.Scatter(
                x=common_x,
                y=[confirmation_price, confirmation_price],
                mode="lines",
                name="浪形确认位",
                meta={"algorithm": "wave"},
                legendgroup="algorithm-wave",
                showlegend=False,
                line={"color": WAVE_CONFIRMATION_COLOR, "width": 1.5, "dash": "dash"},
                hovertemplate=(
                    f"{confirmation_label} {confirmation_price:.3f}<br>{confirmation_rule}"
                    "<br>未确认前属于观察状态<extra></extra>"
                ),
            ),
            row=1,
            col=1,
        )
    figure.add_trace(
        go.Scatter(
            x=common_x,
            y=[invalidation_price, invalidation_price],
            mode="lines",
            name="浪形失效位",
            meta={"algorithm": "wave"},
            legendgroup="algorithm-wave",
            showlegend=False,
            line={"color": WAVE_INVALIDATION_COLOR, "width": 1.5, "dash": "dot"},
            hovertemplate=(
                f"{invalidation_label} {invalidation_price:.3f}"
                f"<br>{invalidation_rule}"
                "<br>水平长度仅为展示空间，不预测到达时间<extra></extra>"
            ),
        ),
        row=1,
        col=1,
    )
    figure.add_shape(
        name="algorithm-wave-target-zone",
        type="rect",
        x0=current_time,
        x1=future_time,
        y0=zone_lower,
        y1=zone_upper,
        fillcolor="rgba(163,230,53,0.10)",
        line={"color": "rgba(163,230,53,0.45)", "width": 1, "dash": "dot"},
        row=1,
        col=1,
    )
    figure.add_annotation(
        name="algorithm-wave-time-note",
        x=future_time,
        y=zone_upper,
        text="右侧横向距离仅为情景示意，不代表时间",
        showarrow=False,
        xanchor="right",
        yanchor="bottom",
        font={"color": "#94a3b8", "size": 9},
        bgcolor="rgba(11,16,23,0.72)",
        row=1,
        col=1,
    )


def _add_gann_overlay(
    figure: go.Figure,
    frame: pd.DataFrame,
    gann: dict[str, Any],
) -> None:
    """绘制 ATR 归一化江恩扇形、价格分割和时间周期。"""
    if gann.get("status") != "active" or frame.empty:
        return
    anchor = gann.get("anchor", {})
    anchor_time = pd.Timestamp(anchor.get("timestamp"))
    anchor_price = float(anchor.get("price"))
    direction = str(gann.get("direction", "up"))
    direction_label = "上行" if direction == "up" else "下行"
    common = {
        "meta": {"algorithm": "gann"},
        "legendgroup": "algorithm-gann",
        "visible": False,
    }
    fan_items = gann.get("fan_lines", [])
    future_times = [pd.Timestamp(item["end_time"]) for item in fan_items]
    latest_time = pd.Timestamp(frame["datetime"].iloc[-1])
    future_end = max(future_times, default=latest_time)
    current_close = float(frame["close"].iloc[-1])
    trend_end_prices = [float(item["end_price"]) for item in fan_items]
    padding_prices = [current_close, *trend_end_prices]
    figure.add_trace(
        go.Scatter(
            x=[latest_time] + [future_end] * len(trend_end_prices),
            y=padding_prices,
            mode="lines",
            name="江恩未来显示空间",
            line={"width": 0},
            opacity=0,
            showlegend=False,
            hoverinfo="skip",
        ),
        row=1,
        col=1,
    )

    figure.add_trace(
        go.Scatter(
            x=[anchor_time],
            y=[anchor_price],
            mode="markers+text",
            name="江恩自动确认锚点",
            text=["G"],
            textposition="top center" if direction == "up" else "bottom center",
            marker={"color": GANN_COLOR, "size": 10, "symbol": "diamond"},
            hovertemplate=(
                f"江恩自动锚点（{direction_label}）<br>日期：%{{x|%Y-%m-%d %H:%M}}"
                f"<br>价格：%{{y:.3f}}<br>右侧确认：{anchor.get('confirmed_at', '--')}"
                "<extra></extra>"
            ),
            **common,
        ),
        row=1,
        col=1,
    )
    fan_colors = {"2×1": GANN_FAST_COLOR, "1×1": GANN_COLOR, "1×2": GANN_SLOW_COLOR}
    for item in fan_items:
        label = str(item["label"])
        figure.add_trace(
            go.Scatter(
                x=[
                    pd.Timestamp(item.get("current_time", item["start_time"])),
                    pd.Timestamp(item["end_time"]),
                ],
                y=[float(item.get("current_price", item["start_price"])), float(item["end_price"])],
                mode="lines+text",
                name=f"江恩后续趋势 {label}",
                text=["", label],
                textposition="middle right",
                textfont={"color": fan_colors.get(label, GANN_COLOR), "size": 11},
                line={
                    "color": fan_colors.get(label, GANN_COLOR),
                    "width": 3 if label == "1×1" else 2,
                    "dash": "solid" if label == "1×1" else "dash",
                },
                hovertemplate=(
                    f"江恩后续趋势 {label}<br>ATR 归一化路径"
                    "<br>横向延伸是结构观察范围，不是精确到达时间<extra></extra>"
                ),
                **common,
            ),
            row=1,
            col=1,
        )

    level_end = max(future_times, default=latest_time)
    level_x: list[pd.Timestamp | None] = []
    level_y: list[float | None] = []
    level_text: list[str | None] = []
    levels = sorted(
        gann.get("price_levels", []),
        key=lambda item: abs(float(item["price"]) - float(frame["close"].iloc[-1])),
    )[:5]
    for item in levels:
        price = float(item["price"])
        level_x.extend([latest_time, level_end, None])
        level_y.extend([price, price, None])
        level_text.extend([str(item["label"]), str(item["label"]), None])
    if level_x:
        figure.add_trace(
            go.Scatter(
                x=level_x,
                y=level_y,
                text=level_text,
                mode="lines",
                name="江恩价格分割",
                line={"color": "rgba(192,132,252,0.55)", "width": 1, "dash": "dot"},
                hovertemplate="江恩价格分割 %{text}<br>价格：%{y:.3f}<extra></extra>",
                **common,
            ),
            row=1,
            col=1,
        )

    visible_low = float(frame["low"].tail(120).min())
    visible_high = float(frame["high"].tail(120).max())
    cycle_x: list[pd.Timestamp | None] = []
    cycle_y: list[float | None] = []
    cycle_text: list[str | None] = []
    for item in gann.get("time_cycles", []):
        timestamp = pd.Timestamp(item["datetime"])
        cycle_x.extend([timestamp, timestamp, None])
        cycle_y.extend([visible_low, visible_high, None])
        label = f"{item['bars']}根"
        cycle_text.extend([label, label, None])
    if cycle_x:
        figure.add_trace(
            go.Scatter(
                x=cycle_x,
                y=cycle_y,
                text=cycle_text,
                mode="lines",
                name="江恩时间观察窗",
                line={"color": "rgba(129,140,248,0.25)", "width": 1, "dash": "dot"},
                hovertemplate="江恩时间周期 %{text}<br>仅为观察窗口<extra></extra>",
                **common,
            ),
            row=1,
            col=1,
        )

    boundary_end = level_end
    for name, price, color, dash in (
        ("江恩确认位", gann.get("confirmation"), GANN_FAST_COLOR, "dash"),
        ("江恩失效位", gann.get("invalidation"), WAVE_INVALIDATION_COLOR, "dot"),
    ):
        if price is None:
            continue
        figure.add_trace(
            go.Scatter(
                x=[latest_time, boundary_end],
                y=[float(price), float(price)],
                mode="lines",
                name=name,
                showlegend=False,
                line={"color": color, "width": 1.5, "dash": dash},
                hovertemplate=f"{name} %{{y:.3f}}<br>以收盘确认<extra></extra>",
                **common,
            ),
            row=1,
            col=1,
        )


def create_figure(
    frame: pd.DataFrame,
    analysis: dict[str, Any],
    levels: dict[str, Any],
    request: AnalyzeRequest,
    title: str,
    signals: list[TradingSignal] | None = None,
    wave: dict[str, Any] | None = None,
    gann: dict[str, Any] | None = None,
) -> go.Figure:
    """创建主图、成交量、MACD、RSI 以及可选 KDJ 子图。"""
    show_kdj = request.show_kdj
    is_global = request.asset_type in {"us_stock", "us_index", "global_future"}
    up_color = GLOBAL_UP_COLOR if is_global else CN_UP_COLOR
    down_color = GLOBAL_DOWN_COLOR if is_global else CN_DOWN_COLOR
    row_count = 5 if show_kdj else 4
    row_heights = [0.48, 0.12, 0.14, 0.13, 0.13] if show_kdj else [0.58, 0.14, 0.14, 0.14]
    subplot_titles = ["价格", "成交量", "MACD", "RSI"] + (["KDJ"] if show_kdj else [])
    figure = make_subplots(
        rows=row_count,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.025,
        row_heights=row_heights,
        subplot_titles=subplot_titles,
    )
    figure.add_trace(
        go.Candlestick(
            x=frame["datetime"],
            open=frame["open"],
            high=frame["high"],
            low=frame["low"],
            close=frame["close"],
            name="K线",
            showlegend=False,
            increasing={"line": {"color": up_color}, "fillcolor": up_color},
            decreasing={"line": {"color": down_color}, "fillcolor": down_color},
            hovertext=[
                f"涨跌幅: {value:.2f}%" if pd.notna(value) else "涨跌幅: --"
                for value in frame["pct_change"]
            ],
        ),
        row=1,
        col=1,
    )
    _add_main_overlays(figure, frame, levels, request)
    _add_macd_events(figure, frame, up_color, down_color)
    _add_buy_signal_markers(figure, frame, signals or [])
    _add_wave_overlay(figure, wave or {})
    _add_wave_scenarios(figure, frame, wave or {})
    _add_gann_overlay(figure, frame, gann or {})

    volume_colors = [
        up_color if close >= open_ else down_color
        for open_, close in zip(frame["open"], frame["close"], strict=True)
    ]
    figure.add_trace(
        go.Bar(
            x=frame["datetime"],
            y=frame["volume"],
            name="成交量",
            showlegend=False,
            marker_color=volume_colors,
            opacity=0.72,
            hovertemplate="成交量: %{y:,.0f}<extra></extra>",
        ),
        row=2,
        col=1,
    )
    for column, color in (("VOL_MA5", "#fbbf24"), ("VOL_MA10", "#38bdf8")):
        figure.add_trace(
            go.Scatter(
                x=frame["datetime"], y=frame[column], name=column, line={"color": color, "width": 1}
            ),
            row=2,
            col=1,
        )

    macd_colors = [up_color if value >= 0 else down_color for value in frame["MACD"].fillna(0)]
    figure.add_trace(
        go.Bar(
            x=frame["datetime"],
            y=frame["MACD"],
            name="MACD柱",
            showlegend=False,
            marker_color=macd_colors,
            opacity=0.75,
        ),
        row=3,
        col=1,
    )
    figure.add_trace(
        go.Scatter(
            x=frame["datetime"], y=frame["DIF"], name="DIF", line={"color": "#fbbf24", "width": 1.2}
        ),
        row=3,
        col=1,
    )
    figure.add_trace(
        go.Scatter(
            x=frame["datetime"], y=frame["DEA"], name="DEA", line={"color": "#38bdf8", "width": 1.2}
        ),
        row=3,
        col=1,
    )

    for column, color in (("RSI6", "#fbbf24"), ("RSI12", "#38bdf8"), ("RSI24", "#f472b6")):
        figure.add_trace(
            go.Scatter(
                x=frame["datetime"],
                y=frame[column],
                name=column,
                line={"color": color, "width": 1.1},
            ),
            row=4,
            col=1,
        )
    for value, dash in ((30, "dot"), (50, "dash"), (70, "dot")):
        figure.add_hline(
            y=value,
            line={"color": "rgba(148,163,184,0.45)", "width": 1, "dash": dash},
            row=4,
            col=1,
        )
    figure.update_yaxes(range=[0, 100], row=4, col=1)

    if show_kdj:
        for column, color in (("K", "#fbbf24"), ("D", "#38bdf8"), ("J", "#f472b6")):
            figure.add_trace(
                go.Scatter(
                    x=frame["datetime"],
                    y=frame[column],
                    name=column,
                    line={"color": color, "width": 1.1},
                ),
                row=5,
                col=1,
            )
        for value in (20, 50, 80):
            figure.add_hline(
                y=value,
                line={"color": "rgba(148,163,184,0.4)", "width": 1, "dash": "dot"},
                row=5,
                col=1,
            )

    figure.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0b1017",
        plot_bgcolor="#0b1017",
        font={"color": TEXT_COLOR, "family": "Inter, 'Microsoft YaHei', sans-serif", "size": 11},
        height=1180 if show_kdj else 1030,
        margin={"l": 54, "r": 64, "t": 102, "b": 42},
        hovermode="x unified",
        dragmode="pan",
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.015,
            "x": 0,
            "font": {"size": 9},
            "itemwidth": 32,
        },
        modebar={"orientation": "v"},
        bargap=0.05,
    )
    figure.update_xaxes(
        showgrid=True,
        gridcolor=GRID_COLOR,
        showspikes=True,
        spikecolor="rgba(226,232,240,0.5)",
        spikethickness=1,
        rangeslider_visible=False,
        rangebreaks=[{"bounds": ["sat", "mon"]}] if request.period == "daily" else None,
    )
    figure.update_yaxes(showgrid=True, gridcolor=GRID_COLOR, fixedrange=False)
    return figure


PLOTLY_CONFIG = {
    "responsive": True,
    "displaylogo": False,
    "scrollZoom": True,
    "modeBarButtonsToAdd": ["drawline", "drawrect", "eraseshape"],
    "toImageButtonOptions": {"format": "png", "filename": "akshare_technical_chart", "scale": 2},
}


def render_figure_html(figure: go.Figure, *, full_html: bool) -> str:
    """Render online and offline charts with one shared Plotly configuration."""
    return pio.to_html(
        figure,
        full_html=full_html,
        include_plotlyjs="inline",
        config=PLOTLY_CONFIG,
        auto_play=False,
        post_script=PLOTLY_UNDO_POST_SCRIPT,
    )
