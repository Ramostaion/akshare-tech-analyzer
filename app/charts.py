"""Plotly 交互 K 线图构建。"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

from app.models import AnalyzeRequest

CN_UP_COLOR = "#ef4444"
CN_DOWN_COLOR = "#22c55e"
GLOBAL_UP_COLOR = "#22c55e"
GLOBAL_DOWN_COLOR = "#ef4444"
GRID_COLOR = "rgba(148, 163, 184, 0.13)"
TEXT_COLOR = "#dbe4ee"

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


def create_figure(
    frame: pd.DataFrame,
    analysis: dict[str, Any],
    levels: dict[str, Any],
    request: AnalyzeRequest,
    title: str,
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
