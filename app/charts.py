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
WAVE_CONTINUATION_COLOR = "#bef264"
WAVE_INVALIDATION_COLOR = "#fb7185"
WAVE_CONFIRMATION_COLOR = "#fbbf24"
WAVE_NEUTRAL_COLOR = "#94a3b8"
GANN_COLOR = "#c084fc"
GANN_FAST_COLOR = "#e879f9"
GANN_SLOW_COLOR = "#818cf8"
PROJECTION_DISPLAY_FRACTION = 0.15
DEFAULT_VISIBLE_BARS = {
    "daily": 220,
    "weekly": 156,
    "monthly": 120,
}
DEFAULT_INTRADAY_VISIBLE_BARS = 300

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


def _projection_display_end(
    frame: pd.DataFrame,
    projected_end: pd.Timestamp,
    visible_bars: int = 220,
) -> pd.Timestamp:
    """返回仅供绘图使用的终点，确保条件路径在近期窗口中可辨认。"""
    datetimes = pd.to_datetime(frame["datetime"])
    latest = pd.Timestamp(datetimes.iloc[-1])
    start_position = max(0, len(datetimes) - max(2, visible_bars))
    visible_start = pd.Timestamp(datetimes.iloc[start_position])
    minimum_end = latest + (latest - visible_start) * PROJECTION_DISPLAY_FRACTION
    return max(pd.Timestamp(projected_end), minimum_end)


def _time_fraction(start: pd.Timestamp, end: pd.Timestamp, fraction: float) -> pd.Timestamp:
    """在示意横轴上按比例布置路径节点，不赋予节点精确日期含义。"""
    return start + (end - start) * fraction


def _default_chart_x_range(
    frame: pd.DataFrame,
    period: str,
) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """默认聚焦近期行情，同时为条件路径保留右侧显示空间。"""
    datetimes = pd.to_datetime(frame["datetime"])
    intervals = datetimes.diff().dropna()
    if datetimes.empty or intervals.empty or intervals.median() <= pd.Timedelta(0):
        return None
    visible_bars = DEFAULT_VISIBLE_BARS.get(period, DEFAULT_INTRADAY_VISIBLE_BARS)
    start_position = max(0, len(datetimes) - visible_bars)
    latest = pd.Timestamp(datetimes.iloc[-1])
    projected_end = latest + intervals.median() * 24
    return (
        pd.Timestamp(datetimes.iloc[start_position]),
        _projection_display_end(frame, projected_end, visible_bars),
    )


def _default_price_y_range(
    frame: pd.DataFrame,
    period: str,
    wave: dict[str, Any],
    gann: dict[str, Any],
    wyckoff: dict[str, Any] | None = None,
) -> tuple[float, float] | None:
    """按近期行情及默认可见图层设置价格轴，避免隐藏投影压扁 K 线。"""
    if frame.empty:
        return None
    visible_bars = DEFAULT_VISIBLE_BARS.get(period, DEFAULT_INTRADAY_VISIBLE_BARS)
    recent = frame.tail(visible_bars)
    values = [float(recent["low"].min()), float(recent["high"].max())]

    candidates = wave.get("candidates", [])
    if candidates:
        candidate = candidates[0]
        values.extend(float(item["price"]) for item in candidate.get("pivots", []))
        projection = candidate.get("projection", {})
        values.extend(float(value) for value in projection.get("primary_zone", []))
        for key in ("confirmation", "invalidation"):
            if projection.get(key) is not None:
                values.append(float(projection[key]))

    # 江恩与威科夫默认关闭。它们可能包含距离现价很远的冻结锚点或条件投影，
    # 隐藏图层不应参与初始取景，否则理论线会反过来压缩真实价格走势。

    finite_values = [value for value in values if pd.notna(value)]
    if not finite_values:
        return None
    lower = min(finite_values)
    upper = max(finite_values)
    padding = max((upper - lower) * 0.05, abs(float(frame["close"].iloc[-1])) * 0.005, 0.01)
    return lower - padding, upper + padding

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

  const crosshair = document.createElement("div");
  crosshair.className = "akshare-crosshair";
  crosshair.innerHTML = [
    '<i data-part="vertical"></i>',
    '<i data-part="horizontal"></i>',
    '<span data-part="date"></span>',
    '<span data-part="price"></span>'
  ].join("");
  Object.assign(crosshair.style, {
    position: "absolute",
    inset: "0",
    zIndex: "30",
    pointerEvents: "none",
    display: "none"
  });
  const vertical = crosshair.querySelector('[data-part="vertical"]');
  const horizontal = crosshair.querySelector('[data-part="horizontal"]');
  const dateLabel = crosshair.querySelector('[data-part="date"]');
  const priceLabel = crosshair.querySelector('[data-part="price"]');
  [vertical, horizontal].forEach((line) => Object.assign(line.style, {
    position: "absolute",
    display: "block",
    background: "rgba(226,232,240,0.58)"
  }));
  Object.assign(vertical.style, {width: "1px"});
  Object.assign(horizontal.style, {height: "1px"});
  [dateLabel, priceLabel].forEach((label) => Object.assign(label.style, {
    position: "absolute",
    display: "block",
    boxSizing: "border-box",
    padding: "3px 6px",
    border: "1px solid #64748b",
    borderRadius: "3px",
    background: "#17202b",
    color: "#f8fafc",
    font: "11px/1.2 Consolas, monospace",
    whiteSpace: "nowrap",
    textAlign: "center"
  }));
  graph.style.position = "relative";
  graph.appendChild(crosshair);
  graph.__akshareCrosshair = crosshair;

  const hideCrosshair = () => { crosshair.style.display = "none"; };
  graph.addEventListener("mousemove", (event) => {
    if (event.buttons) {
      hideCrosshair();
      return;
    }
    const layout = graph._fullLayout;
    const xAxis = layout?.xaxis;
    const yAxis = layout?.yaxis;
    if (!xAxis || !yAxis) return;
    const bounds = graph.getBoundingClientRect();
    const x = event.clientX - bounds.left;
    const y = event.clientY - bounds.top;
    const inPricePlot = (
      x >= xAxis._offset && x <= xAxis._offset + xAxis._length
      && y >= yAxis._offset && y <= yAxis._offset + yAxis._length
    );
    if (!inPricePlot) {
      hideCrosshair();
      return;
    }

    const timestamp = new Date(xAxis.p2d(x - xAxis._offset));
    const price = Number(yAxis.p2d(y - yAxis._offset));
    if (Number.isNaN(timestamp.getTime()) || !Number.isFinite(price)) {
      hideCrosshair();
      return;
    }
    const span = Math.abs(Number(yAxis.range[1]) - Number(yAxis.range[0]));
    const digits = span < 1 ? 4 : span < 100 ? 2 : span < 1000 ? 1 : 0;
    const dateSpan = Math.abs(
      new Date(xAxis.range[1]).getTime() - new Date(xAxis.range[0]).getTime()
    );
    const dateOptions = dateSpan <= 45 * 86400000
      ? {month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false}
      : {year: "numeric", month: "2-digit", day: "2-digit"};
    dateLabel.textContent = new Intl.DateTimeFormat("zh-CN", dateOptions).format(timestamp);
    priceLabel.textContent = price.toFixed(digits);

    const plotTop = layout._size?.t ?? yAxis._offset;
    const plotHeight = layout._size?.h ?? yAxis._length;
    const labelX = Math.min(
      Math.max(x, xAxis._offset + 54),
      xAxis._offset + xAxis._length - 54
    );
    Object.assign(vertical.style, {left: `${x}px`, top: `${plotTop}px`, height: `${plotHeight}px`});
    Object.assign(horizontal.style, {
      left: `${xAxis._offset}px`,
      top: `${y}px`,
      width: `${xAxis._length}px`
    });
    Object.assign(dateLabel.style, {
      left: `${labelX}px`,
      top: `${plotTop + plotHeight - 23}px`,
      transform: "translateX(-50%)"
    });
    Object.assign(priceLabel.style, {
      left: `${xAxis._offset + xAxis._length - 2}px`,
      top: `${y}px`,
      transform: "translate(-100%, -50%)"
    });
    crosshair.style.display = "block";
  });
  graph.addEventListener("mouseleave", hideCrosshair);

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
    """在确认 Trigger 的 K 线下方标记历史做多信号，默认隐藏。"""
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
            f"做多 Trigger（收盘确认，非实际成交）<br>日期：{timestamp:%Y-%m-%d %H:%M}"
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
            name="历史做多 Trigger（非实际成交）",
            text=hover_text,
            marker={
                "color": BUY_TRIGGER_COLOR,
                "symbol": "triangle-up",
                "size": 12,
                "line": {"color": "#713f12", "width": 1},
            },
            hovertemplate="%{text}<extra></extra>",
            meta={"overlay": "history_signals"},
            legendgroup="technical-signals",
            visible="legendonly",
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
        figure.add_annotation(
            name="algorithm-wave-empty-note",
            x=0.99,
            y=0.98,
            xref="paper",
            yref="paper",
            text="当前周期没有满足硬规则的已确认波浪候选",
            showarrow=False,
            xanchor="right",
            yanchor="top",
            font={"color": WAVE_NEUTRAL_COLOR, "size": 10},
            bgcolor="rgba(11,16,23,0.78)",
        )
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
    projected_time = current_time + interval * 8
    future_time = _projection_display_end(frame, projected_time)
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
            _time_fraction(current_time, future_time, 3 / 8),
            _time_fraction(current_time, future_time, 6 / 8),
            future_time,
        ]
        path_1_y = [current_price, confirmation_price, zone_entry, target_midpoint]
        failed_probe = confirmation_price
    else:
        path_1_x = [
            current_time,
            _time_fraction(current_time, future_time, 5 / 8),
            future_time,
        ]
        path_1_y = [current_price, zone_entry, target_midpoint]
        failed_probe = current_price + (zone_entry - current_price) * 0.35
    path_2_x = [
        current_time,
        _time_fraction(current_time, future_time, 3 / 8),
        _time_fraction(current_time, future_time, 7 / 8),
    ]
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
                line={"color": WAVE_CONTINUATION_COLOR, "width": 4, "dash": "solid"},
                marker={
                    "color": WAVE_CONTINUATION_COLOR,
                    "size": 8,
                    "line": {"color": "#365314", "width": 1},
                },
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
            _time_fraction(current_time, future_time, 2 / 8),
            _time_fraction(current_time, future_time, 4 / 8),
            _time_fraction(current_time, future_time, 6 / 8),
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
    """绘制锚点、标准化角线、价格位、时间窗、共振区和条件情景。"""
    if gann.get("status") != "active" or frame.empty:
        return
    anchor = gann.get("anchor", {})
    anchor_time = pd.Timestamp(anchor["timestamp"])
    anchor_price = float(anchor["price"])
    direction = str(gann.get("direction", "up"))
    direction_label = "上行" if direction == "up" else "下行"
    common = {
        "meta": {"algorithm": "gann"},
        "legendgroup": "algorithm-gann",
        "visible": False,
    }
    fan_items = [
        item for item in gann.get("fan_lines", []) if item.get("default_visible")
    ]
    latest_time = pd.Timestamp(frame["datetime"].iloc[-1])
    future_end = max(
        (pd.Timestamp(item["end_time"]) for item in fan_items), default=latest_time
    )
    current_close = float(frame["close"].iloc[-1])
    trend_end_prices = [float(item["end_price"]) for item in fan_items]
    figure.add_trace(
        go.Scatter(
            x=[latest_time] + [future_end] * len(trend_end_prices),
            y=[current_close, *trend_end_prices],
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
            name="江恩确认锚点",
            text=["G"],
            textposition="top center" if direction == "up" else "bottom center",
            marker={"color": GANN_COLOR, "size": 10, "symbol": "diamond"},
            hovertemplate=(
                f"江恩锚点（{direction_label}）<br>Pivot：%{{x|%Y-%m-%d %H:%M}}"
                f"<br>价格：%{{y:.3f}}<br>确认于：{anchor.get('confirmed_at', '--')}"
                f"<br>Anchor Score：{anchor.get('score', '--')}/100<extra></extra>"
            ),
            **common,
        ),
        row=1,
        col=1,
    )
    fan_colors = {"2×1": GANN_FAST_COLOR, "1×1": GANN_COLOR, "1×2": GANN_SLOW_COLOR}
    scale_method = str(gann.get("scale", {}).get("method", "标准化价格单位 / bar"))
    for item in fan_items:
        label = str(item["label"])
        figure.add_trace(
            go.Scatter(
                x=[pd.Timestamp(item["start_time"]), pd.Timestamp(item["end_time"])],
                y=[float(item["start_price"]), float(item["end_price"])],
                mode="lines+text",
                name=f"江恩角线 {label}",
                text=["", label],
                textposition="middle right",
                textfont={"color": fan_colors.get(label, GANN_COLOR), "size": 11},
                line={
                    "color": fan_colors.get(label, GANN_COLOR),
                    "width": 3 if label == "1×1" else 2,
                    "dash": "solid" if label == "1×1" else "dash",
                },
                hovertemplate=(
                    f"江恩角线 {label}<br>{scale_method}"
                    "<br>动态支撑/阻力，不是精确目标价<extra></extra>"
                ),
                **common,
            ),
            row=1,
            col=1,
        )
    zones = gann.get("confluence_zones", [])
    if zones:
        figure.add_trace(
            go.Scatter(
                x=[pd.Timestamp(item["datetime"]) for item in zones],
                y=[float(item["center"]) for item in zones],
                mode="markers",
                name="江恩时价共振区",
                marker={"color": GANN_COLOR, "size": 11, "symbol": "diamond-open"},
                text=[
                    f"{item['angle']} · {item['time_window']['label']} · 评分 {item['score']}"
                    for item in zones
                ],
                hovertemplate=(
                    "江恩时价共振 %{text}<br>中心：%{y:.3f}"
                    "<br>价格与时间共同观察区<extra></extra>"
                ),
                **common,
            ),
            row=1,
            col=1,
        )
    level_x: list[pd.Timestamp | None] = []
    level_y: list[float | None] = []
    level_text: list[str | None] = []
    levels = sorted(
        gann.get("price_levels", []),
        key=lambda item: abs(float(item["price"]) - current_close),
    )[:5]
    for item in levels:
        price = float(item["price"])
        level_x.extend([latest_time, future_end, None])
        level_y.extend([price, price, None])
        level_text.extend([str(item["label"]), str(item["label"]), None])
    if level_x:
        figure.add_trace(
            go.Scatter(
                x=level_x,
                y=level_y,
                text=level_text,
                mode="lines",
                name="江恩重要价格位",
                line={"color": "rgba(192,132,252,0.55)", "width": 1, "dash": "dot"},
                hovertemplate="江恩价格因子 %{text}<br>价格：%{y:.3f}<extra></extra>",
                **common,
            ),
            row=1,
            col=1,
        )
    windows = gann.get("time_windows", [])
    for index, item in enumerate(windows):
        figure.add_vrect(
            x0=pd.Timestamp(item["start_datetime"]),
            x1=pd.Timestamp(item["end_datetime"]),
            fillcolor="rgba(129,140,248,0.10)",
            line={"color": "rgba(129,140,248,0.32)", "width": 1},
            layer="below",
            visible=False,
            name=f"algorithm-gann-time-{index}",
            row=1,
            col=1,
        )
    if windows:
        figure.add_trace(
            go.Scatter(
                x=[pd.Timestamp(item["center_datetime"]) for item in windows],
                y=[current_close] * len(windows),
                text=[
                    f"{item['label']} · 基础 {item['base_cycle']} 根 · 评分 {item['score']}"
                    for item in windows
                ],
                mode="markers",
                name="江恩时间观察窗",
                marker={"color": "rgba(129,140,248,0.7)", "size": 8, "symbol": "line-ns"},
                hovertemplate=(
                    "江恩时间窗 %{text}<br>按实际 K 线序号计算，仅供观察<extra></extra>"
                ),
                **common,
            ),
            row=1,
            col=1,
        )
    for name, price, color, dash in (
        ("江恩情景触发位", gann.get("confirmation"), GANN_FAST_COLOR, "dash"),
        ("江恩结构失效位", gann.get("invalidation"), WAVE_INVALIDATION_COLOR, "dot"),
    ):
        if price is None:
            continue
        figure.add_trace(
            go.Scatter(
                x=[latest_time, future_end],
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
    target_zone = gann.get("target_zone", [])
    if len(target_zone) == 2:
        figure.add_trace(
            go.Scatter(
                x=[latest_time, future_end, future_end, latest_time, latest_time],
                y=[
                    float(target_zone[0]),
                    float(target_zone[0]),
                    float(target_zone[1]),
                    float(target_zone[1]),
                    float(target_zone[0]),
                ],
                mode="lines",
                fill="toself",
                name="江恩目标共振区",
                line={"color": "rgba(192,132,252,0.35)", "width": 1},
                fillcolor="rgba(192,132,252,0.08)",
                hovertemplate="江恩条件目标区 %{y:.3f}<extra></extra>",
                **common,
            ),
            row=1,
            col=1,
        )
    for index, scenario in enumerate(gann.get("scenarios", []), start=1):
        targets = scenario.get("target_zones", [])
        if not targets:
            continue
        target = sum(map(float, targets[0])) / 2
        confidence = float(scenario.get("effective_confidence", 0.5))
        figure.add_trace(
            go.Scatter(
                x=[latest_time, future_end],
                y=[current_close, target],
                mode="lines+markers",
                name=f"江恩情景 {index}：{scenario.get('name', '')}",
                line={
                    "color": GANN_COLOR if index == 1 else GANN_SLOW_COLOR,
                    "width": 2,
                    "dash": "dash",
                },
                opacity=max(0.3, confidence),
                hovertemplate=(
                    f"{scenario.get('name', '')}<br>触发：{scenario.get('trigger', '')}"
                    f"<br>确认：{scenario.get('confirmation', '')}"
                    f"<br>失效：{scenario.get('invalidation', '')}"
                    "<br>横向距离仅作情景示意<extra></extra>"
                ),
                **common,
            ),
            row=1,
            col=1,
        )

def _add_wyckoff_overlay(
    figure: go.Figure,
    frame: pd.DataFrame,
    wyckoff: dict[str, Any],
) -> None:
    """绘制威科夫交易区间、事件和两条条件情景。"""
    if wyckoff.get("status") != "active" or frame.empty:
        return
    support = float(wyckoff["range"]["support"])
    resistance = float(wyckoff["range"]["resistance"])
    projection = wyckoff.get("projection", {})
    target_zone = projection.get("target_zone", [])
    if len(target_zone) != 2:
        return
    current_time = pd.Timestamp(frame["datetime"].iloc[-1])
    current_price = float(frame["close"].iloc[-1])
    interval = pd.to_datetime(frame["datetime"]).diff().dropna().median()
    if interval <= pd.Timedelta(0):
        return
    future_time = _projection_display_end(frame, current_time + interval * 12)
    confirmation = float(projection["confirmation"])
    invalidation = float(projection["invalidation"])
    target_midpoint = sum(float(value) for value in target_zone) / 2
    common = {
        "meta": {"algorithm": "wyckoff"},
        "legendgroup": "algorithm-wyckoff",
        "visible": False,
    }

    range_position = int(wyckoff["range"].get("start_position", max(0, len(frame) - 120)))
    range_position = max(0, min(range_position, len(frame) - 1))
    range_start = pd.Timestamp(frame["datetime"].iloc[range_position])
    figure.add_shape(
        name="algorithm-wyckoff-range",
        type="rect",
        x0=range_start,
        x1=current_time,
        y0=support,
        y1=resistance,
        fillcolor="rgba(251,191,36,0.06)",
        line={"color": "rgba(251,191,36,0.65)", "width": 1, "dash": "dot"},
        visible=False,
        row=1,
        col=1,
    )
    events = wyckoff.get("events", [])
    if events:
        figure.add_trace(
            go.Scatter(
                x=[pd.Timestamp(item["timestamp"]) for item in events],
                y=[float(item["price"]) for item in events],
                text=[str(item["event"]) for item in events],
                customdata=[
                    f"量比 {float(item['volume_ratio']):.2f} · "
                    f"振幅 {float(item['spread_atr']):.2f} ATR · "
                    + (
                        "已获后续确认"
                        if item.get("confirmation_state") == "follow_through_confirmed"
                        else "仅收盘确认"
                    )
                    for item in events
                ],
                mode="markers+text",
                name="威科夫事件",
                textposition="top center",
                marker={"color": "#fbbf24", "size": 8, "symbol": "diamond"},
                hovertemplate="威科夫 %{text}<br>%{customdata}<extra></extra>",
                **common,
            ),
            row=1,
            col=1,
        )

    scenario_x = [
        current_time,
        _time_fraction(current_time, future_time, 0.45),
        future_time,
    ]
    already_confirmed = projection.get("confirmation_status") == "confirmed"
    continuation_y = [
        current_price,
        current_price if already_confirmed else confirmation,
        target_midpoint,
    ]
    failure_y = [current_price, (current_price + confirmation) / 2, invalidation]
    for name, y_values, color, dash in (
        (
            "威科夫情景 1：已确认后延续"
            if already_confirmed
            else "威科夫情景 1：等待确认后延续",
            continuation_y,
            "#facc15",
            "solid",
        ),
        ("威科夫情景 2：结构失败", failure_y, "#fb7185", "dash"),
    ):
        figure.add_trace(
            go.Scatter(
                x=scenario_x,
                y=y_values,
                mode="lines+markers+text",
                name=name,
                text=["", "", "情景 1" if "情景 1" in name else "情景 2"],
                textposition="top center" if "情景 1" in name else "bottom center",
                line={"color": color, "width": 3, "dash": dash},
                marker={"color": color, "size": 7},
                hovertemplate=(
                    f"{name}<br>横向距离仅为结构示意，不预测到达时间<extra></extra>"
                ),
                **common,
            ),
            row=1,
            col=1,
        )

    figure.add_annotation(
        name="algorithm-wyckoff-phase",
        x=current_time,
        y=resistance,
        text=(
            f"威科夫 {str(wyckoff.get('structure', '')).upper()} "
            f"Phase {wyckoff.get('phase', '--')}"
            + (" · 双候选接近" if wyckoff.get("ambiguous") else "")
        ),
        showarrow=False,
        xanchor="right",
        yanchor="bottom",
        font={"color": "#fbbf24", "size": 10},
        bgcolor="rgba(11,16,23,0.78)",
        visible=False,
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
    wyckoff: dict[str, Any] | None = None,
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
    _add_wyckoff_overlay(figure, frame, wyckoff or {})

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
                x=frame["datetime"], y=frame[column], name=column,
                line={"color": color, "width": 1},
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
            x=frame["datetime"], y=frame["DIF"], name="DIF",
            line={"color": "#fbbf24", "width": 1.2},
        ),
        row=3,
        col=1,
    )
    figure.add_trace(
        go.Scatter(
            x=frame["datetime"], y=frame["DEA"], name="DEA",
            line={"color": "#38bdf8", "width": 1.2},
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
    default_y_range = _default_price_y_range(
        frame,
        request.period,
        wave or {},
        gann or {},
        wyckoff or {},
    )
    if default_y_range is not None:
        figure.update_yaxes(range=list(default_y_range), autorange=False, row=1, col=1)
    default_x_range = _default_chart_x_range(frame, request.period)
    if default_x_range is not None:
        figure.update_xaxes(range=list(default_x_range), autorange=False)
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
