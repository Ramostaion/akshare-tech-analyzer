"""不依赖行情网络的日线江恩趋势可视区域检查。"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from playwright.sync_api import sync_playwright

from app.charts import create_figure, render_figure_html
from app.gann import analyze_gann
from app.indicators import add_indicators
from app.models import AnalyzeRequest


def _daily_frame() -> pd.DataFrame:
    size = 320
    positions = np.arange(size)
    close = 10 + positions * 0.025 + np.sin(positions / 5) * 0.35
    open_price = close - np.sin(positions / 3) * 0.08
    high = np.maximum(open_price, close) + 0.16
    low = np.minimum(open_price, close) - 0.16
    volume = 100_000 + (positions % 17) * 2_500
    frame = pd.DataFrame(
        {
            "datetime": pd.bdate_range("2024-01-02", periods=size),
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume.astype(float),
            "amount": volume * close * 100,
        }
    )
    frame["amplitude"] = (frame["high"] - frame["low"]) / frame["close"].shift(1) * 100
    frame["pct_change"] = frame["close"].pct_change() * 100
    frame["change"] = frame["close"].diff()
    frame["turnover"] = 1.2
    return add_indicators(frame)


def main() -> None:
    frame = _daily_frame()
    gann = analyze_gann(frame)
    request = AnalyzeRequest(symbol="600011", period="daily")
    figure = create_figure(frame, {}, {}, request, "日线江恩检查", [], {}, gann)
    chart_html = render_figure_html(figure, full_html=False)
    page_html = f"""
    <!doctype html><html><body style="margin:0;background:#0b1017">
    <button id="toggle">江恩理论</button>{chart_html}
    <script>
      document.querySelector('#toggle').addEventListener('click', async () => {{
        const graph = document.querySelector('.plotly-graph-div');
        const indices = [...graph.data]
          .map((trace, index) => trace.meta?.algorithm === 'gann' ? index : -1)
          .filter((index) => index >= 0);
        await Plotly.restyle(graph, {{visible: true}}, indices);
        const update = {{'yaxis.autorange': true}};
        Object.keys(graph._fullLayout)
          .filter((key) => /^xaxis\\d*$/.test(key))
          .forEach((axis) => {{ update[`${{axis}}.autorange`] = true; }});
        await Plotly.relayout(graph, update);
        graph.dataset.gannReady = 'true';
      }});
    </script></body></html>
    """

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        errors: list[str] = []
        page.on(
            "console",
            lambda message: errors.append(message.text) if message.type == "error" else None,
        )
        page.set_content(page_html, wait_until="load")
        page.locator("#toggle").click()
        page.wait_for_function(
            "document.querySelector('.plotly-graph-div')?.dataset.gannReady === 'true'"
        )
        pointer = page.evaluate(
            """() => {
              const graph = document.querySelector('.plotly-graph-div');
              const rect = graph.getBoundingClientRect();
              const xa = graph._fullLayout.xaxis;
              const ya = graph._fullLayout.yaxis;
              return {
                x: rect.left + xa._offset + xa._length * 0.62,
                y: rect.top + ya._offset + ya._length * 0.45,
              };
            }"""
        )
        page.mouse.move(pointer["x"], pointer["y"])
        page.wait_for_function(
            "document.querySelector('.akshare-crosshair')?.style.display === 'block'"
        )
        result = page.evaluate(
            """() => {
              const graph = document.querySelector('.plotly-graph-div');
              const xa = graph._fullLayout.xaxis;
              const ya = graph._fullLayout.yaxis;
              const trends = graph.data.filter((trace) =>
                String(trace.name || '').startsWith('江恩角线'));
              return {
                count: trends.length,
                visible: trends.every((trace) => trace.visible === true),
                pointsInPlot: trends.every((trace) => {
                  const last = trace.x.length - 1;
                  const x = xa.d2p(trace.x[last]);
                  const y = ya.d2p(trace.y[last]);
                  return x >= 0 && x <= xa._length && y >= 0 && y <= ya._length;
                }),
                minimumTrendPixels: Math.min(...trends.map((trace) => {
                  const start = xa.d2p(trace.x[0]);
                  const end = xa.d2p(trace.x[trace.x.length - 1]);
                  return Math.abs(end - start);
                })),
                crosshair: {
                  date: graph.querySelector('[data-part="date"]')?.textContent || '',
                  price: graph.querySelector('[data-part="price"]')?.textContent || '',
                  verticalHeight: parseFloat(
                    graph.querySelector('[data-part="vertical"]')?.style.height || '0'
                  ),
                  horizontalWidth: parseFloat(
                    graph.querySelector('[data-part="horizontal"]')?.style.width || '0'
                  ),
                },
                controllingRange: graph._fullLayout.xaxis4.range,
              };
            }"""
        )
        browser.close()

    assert result["count"] == 3
    assert result["visible"]
    assert result["pointsInPlot"]
    assert result["minimumTrendPixels"] >= 48
    assert result["crosshair"]["date"]
    assert float(result["crosshair"]["price"].replace(",", "")) > 0
    assert result["crosshair"]["verticalHeight"] > 0
    assert result["crosshair"]["horizontalWidth"] > 0
    assert not errors
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
