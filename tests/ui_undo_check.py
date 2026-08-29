"""Run a browser smoke check for Plotly shape undo in an offline report."""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

BROWSER_PATHS = (
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    browser_path = next((path for path in BROWSER_PATHS if path.exists()), None)
    if browser_path is None:
        raise SystemExit("未找到本机 Chrome 或 Edge")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=str(browser_path), headless=True)
        page = browser.new_page()
        page.goto(args.report.resolve().as_uri(), wait_until="load")
        page.locator(".plotly-graph-div").wait_for(state="visible")
        initial = page.evaluate("document.querySelector('.plotly-graph-div').layout.shapes.length")
        page.evaluate(
            """
            async () => {
              const graph = document.querySelector('.plotly-graph-div');
              const shapes = JSON.parse(JSON.stringify(graph.layout.shapes || []));
              shapes.push({type: 'line', xref: 'paper', yref: 'paper', x0: 0.1, x1: 0.8,
                y0: 0.2, y1: 0.7, line: {color: '#ffffff'}});
              await Plotly.relayout(graph, {shapes});
            }
            """
        )
        page.wait_for_timeout(150)
        drawn = page.evaluate("document.querySelector('.plotly-graph-div').layout.shapes.length")
        page.keyboard.press("Control+z")
        page.wait_for_timeout(150)
        undone = page.evaluate("document.querySelector('.plotly-graph-div').layout.shapes.length")
        browser.close()

    if drawn != initial + 1 or undone != initial:
        raise SystemExit(f"撤销检查失败: initial={initial}, drawn={drawn}, undone={undone}")
    print(f"撤销检查通过: initial={initial}, drawn={drawn}, undone={undone}")


if __name__ == "__main__":
    main()
