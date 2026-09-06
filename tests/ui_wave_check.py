"""使用缓存行情检查浪形连线和后市情景是否实际进入 Plotly。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

BROWSER_PATHS = (
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    browser_path = next((path for path in BROWSER_PATHS if path.exists()), None)
    if browser_path is None:
        raise RuntimeError("未找到本机 Chrome 或 Edge")

    results: list[dict[str, object]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=str(browser_path), headless=True)
        for name, width, height in (("desktop", 1440, 1000), ("mobile", 390, 844)):
            page = browser.new_page(viewport={"width": width, "height": height})
            errors: list[str] = []
            page.on(
                "console",
                lambda message, target=errors: (
                    target.append(message.text) if message.type == "error" else None
                ),
            )
            page.goto(args.url, wait_until="networkidle")
            page.locator("#asset-type").select_option("global_future")
            page.locator("#symbol").fill("GC")
            page.locator(".parameter-details summary").click()
            page.locator("#start").fill("2024-09-01")
            page.locator("#end").fill("2026-09-01")
            page.locator("#analyze-button").click()
            page.locator(".plotly-graph-div").wait_for(state="visible", timeout=120_000)
            page.locator('[data-algorithm="gann"]').click()
            page.locator('[data-algorithm="wave"]').click()
            page.wait_for_timeout(250)
            result = page.evaluate(
                """
                () => {
                  const graph = document.querySelector('.plotly-graph-div');
                  const traces = [...(graph?.data || [])];
                  return {
                  traces: traces
                    .map((trace) => trace.name || ''),
                  waveText: document.querySelector('#wave-candidates')?.innerText || '',
                  overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
                  gannVisible: traces.filter((trace) => trace.meta?.algorithm === 'gann')
                    .every((trace) => trace.visible === true),
                  waveHidden: traces.filter((trace) => trace.meta?.algorithm === 'wave')
                    .every((trace) => trace.visible === false),
                  waveShapesHidden: [...(graph?.layout?.shapes || [])]
                    .filter((shape) => String(shape.name || '').startsWith('algorithm-wave'))
                    .every((shape) => shape.visible === false),
                  waveResolvedNote: [...(graph?.layout?.annotations || [])]
                    .some((note) => note.name === 'algorithm-wave-resolved-note'),
                  priceAxisRange: graph?._fullLayout?.yaxis?.range || [],
                  gannRanges: traces
                    .filter((trace) => trace.meta?.algorithm === 'gann')
                    .map((trace) => ({name: trace.name, y: trace.y || []})),
                  gannTrendInRange: Math.max(...traces
                    .filter((trace) => String(trace.name || '').startsWith('江恩角线'))
                    .flatMap((trace) => [...(trace.x || [])]
                      .map((value) => new Date(value).getTime())))
                    <= new Date(graph?._fullLayout?.xaxis?.range?.[1]).getTime(),
                  gannTrendPixels: Math.min(...traces
                    .filter((trace) => String(trace.name || '').startsWith('江恩角线'))
                    .map((trace) => Math.abs(
                      graph._fullLayout.xaxis.d2p(trace.x.at(-1))
                      - graph._fullLayout.xaxis.d2p(trace.x[0])
                    ))),
                  waveScenarioPixels: Math.min(...traces
                    .filter((trace) => String(trace.name || '').startsWith('浪形情景'))
                    .map((trace) => Math.abs(
                      graph._fullLayout.xaxis.d2p(trace.x.at(-1))
                      - graph._fullLayout.xaxis.d2p(trace.x[0])
                    ))),
                  };
                }
                """
            )
            result["viewport"] = name
            result["errors"] = errors
            results.append(result)
            page.close()
        browser.close()

    print(json.dumps(results, ensure_ascii=False))
    for result in results:
        traces = result["traces"]
        assert "候选 1" in result["waveText"]
        assert "浪形候选 Top-1" in traces
        has_scenario = any(str(item).startswith("浪形情景 1") for item in traces)
        assert has_scenario or result["waveResolvedNote"]
        if has_scenario:
            assert any(str(item).startswith("浪形情景 2") for item in traces)
        assert "江恩角线 1×1" in traces
        assert result["gannVisible"]
        assert result["waveHidden"]
        assert result["waveShapesHidden"]
        assert result["gannTrendInRange"]
        minimum_pixels = 48 if result["viewport"] == "desktop" else 24
        assert result["gannTrendPixels"] >= minimum_pixels
        if has_scenario:
            assert result["waveScenarioPixels"] >= minimum_pixels
        assert not result["overflow"]
        assert not result["errors"]


if __name__ == "__main__":
    main()
