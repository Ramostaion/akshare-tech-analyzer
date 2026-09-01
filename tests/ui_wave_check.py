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
            page.locator("#start").fill("2024-09-01")
            page.locator("#end").fill("2026-09-01")
            page.locator("#analyze-button").click()
            page.locator(".plotly-graph-div").wait_for(state="visible", timeout=120_000)
            result = page.evaluate(
                """
                () => ({
                  traces: [...(document.querySelector('.plotly-graph-div')?.data || [])]
                    .map((trace) => trace.name || ''),
                  waveText: document.querySelector('#wave-candidates')?.innerText || '',
                  overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
                })
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
        assert any(str(item).startswith("浪形情景 1") for item in traces)
        assert any(str(item).startswith("浪形情景 2") for item in traces)
        assert not result["overflow"]
        assert not result["errors"]


if __name__ == "__main__":
    main()
