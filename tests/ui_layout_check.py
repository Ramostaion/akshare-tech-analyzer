"""使用本机 Chrome/Edge 对工作台做手动布局回归截图。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

BROWSER_PATHS = (
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
)


def inspect_layout(url: str, output_dir: Path) -> list[dict[str, object]]:
    browser_path = next((path for path in BROWSER_PATHS if path.exists()), None)
    if browser_path is None:
        raise RuntimeError("未找到本机 Chrome 或 Edge")
    output_dir.mkdir(parents=True, exist_ok=True)
    viewports = {"desktop": (1440, 1000), "mobile": (390, 844)}
    results: list[dict[str, object]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=str(browser_path),
            headless=True,
        )
        for name, (width, height) in viewports.items():
            page = browser.new_page(viewport={"width": width, "height": height})
            console_errors: list[str] = []
            page.on(
                "console",
                lambda message, errors=console_errors: (
                    errors.append(message.text) if message.type == "error" else None
                ),
            )
            page.goto(url, wait_until="networkidle")
            page.locator("#symbol").fill("600011")
            page.locator("#asset-type").select_option("cn_stock")
            page.locator("#start").fill("2024-01-01")
            page.locator("#end").fill("2026-08-29")
            page.locator("#analyze-button").click()
            page.locator(".plotly-graph-div").wait_for(state="visible", timeout=120_000)
            page.wait_for_timeout(1_000)
            metrics = page.evaluate(
                """
                () => {
                  const rect = (selector) => {
                    const element = document.querySelector(selector);
                    if (!element) return null;
                    const box = element.getBoundingClientRect();
                    return {x: box.x, y: box.y, width: box.width, height: box.height};
                  };
                  const children = [...document.querySelectorAll('#analyze-form > *')]
                    .filter((element) => element.getClientRects().length)
                    .map((element, index) => ({index, box: element.getBoundingClientRect()}));
                  const overlaps = [];
                  for (let left = 0; left < children.length; left += 1) {
                    for (let right = left + 1; right < children.length; right += 1) {
                      const a = children[left].box;
                      const b = children[right].box;
                      const xOverlap = Math.min(a.right, b.right) - Math.max(a.left, b.left);
                      const yOverlap = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
                      if (xOverlap > 1 && yOverlap > 1) {
                        overlaps.push([children[left].index, children[right].index]);
                      }
                    }
                  }
                  return {
                    bodyScrollWidth: document.documentElement.scrollWidth,
                    viewportWidth: window.innerWidth,
                    form: rect('#analyze-form'),
                    chartShell: rect('#chart'),
                    graph: rect('.plotly-graph-div'),
                    plotSvg: rect('.plotly-graph-div .main-svg'),
                    formOverlaps: overlaps,
                  };
                }
                """
            )
            metrics["name"] = name
            metrics["consoleErrors"] = console_errors
            results.append(metrics)
            page.screenshot(path=output_dir / f"ui-{name}.png", full_page=True)
            page.close()
        browser.close()
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--output-dir", type=Path, default=Path("reports/ui-check"))
    args = parser.parse_args()
    results = inspect_layout(args.url, args.output_dir)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    failures: list[str] = []
    for result in results:
        name = result["name"]
        if result["bodyScrollWidth"] > result["viewportWidth"] + 1:
            failures.append(f"{name}: 页面存在横向溢出")
        if result["formOverlaps"]:
            failures.append(f"{name}: 表单控件发生重叠")
        chart = result["chartShell"]
        plot = result["plotSvg"]
        if chart is None or plot is None or plot["width"] < chart["width"] * 0.98:
            failures.append(f"{name}: Plotly 图表未铺满容器")
        if result["consoleErrors"]:
            failures.append(f"{name}: 浏览器控制台存在错误")
    if failures:
        raise SystemExit("；".join(failures))


if __name__ == "__main__":
    main()
