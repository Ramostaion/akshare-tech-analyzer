"""不依赖行情网络的量化结果 UI 手动检查。"""

from __future__ import annotations

import argparse
import json

from playwright.sync_api import Route, sync_playwright


def _payload() -> dict[str, object]:
    return {
        "request": {
            "symbol": "600011",
            "asset_type": "cn_stock",
            "period": "daily",
            "adjust": "qfq",
            "start": "2024-01-01",
            "end": "2026-08-30",
            "show_kdj": False,
        },
        "metadata": {
            "security": {
                "symbol": "600011",
                "name": "离线测试",
                "asset_type": "cn_stock",
                "data_source": "fixture",
                "timezone": "Asia/Shanghai",
                "exchange": "SSE",
                "currency": "CNY",
                "provider_symbol": "600011",
                "detection_method": "offline fixture",
                "series_type": None,
            },
            "from_cache": False,
            "fetched_at": "2026-08-30T10:00:00+08:00",
            "period": "daily",
            "adjust": "qfq",
            "rows": 320,
            "volume_unit": "手",
            "snapshot": None,
            "quality_notes": [],
            "cache_status": {"mode": "network", "new_rows": 320},
            "data_quality": {"status": "良好", "rows": 320, "issues": []},
        },
        "analysis": {
            "state": "震荡偏强",
            "score": 66,
            "market_regime": {"label": "上升趋势"},
            "latest": {"close": 12.3, "pct_change": 1.2, "ATR_PCT": 2.1, "RSI12": 55},
            "summary": "离线量化界面检查。",
            "evidence": {"bullish": ["证据"], "bearish": [], "neutral": []},
            "warning": ["测试提示"],
            "formula_notes": ["公式"],
            "components": {
                "trend": {"name": "趋势", "score": 65, "reasons": []},
            },
            "backtest": {"method": "旧版兼容", "signals": 0, "cost_rate": 0.1, "results": {}},
        },
        "levels": {
            "supports": [{"price": 11.8}],
            "resistances": [{"price": 13.2}],
            "scenario": None,
        },
        "quant": {
            "market_regime": {"regime": "UPTREND", "confidence": 0.78, "evidence": ["均线向上"]},
            "current_setups": [{"setup": "trend_pullback", "triggered": True}],
            "current_signal": {
                "direction": "long",
                "setup": "trend_pullback",
                "score": 76,
                "entry_reference": 12.3,
                "entry_zone_lower": 12.18,
                "entry_zone_upper": 12.36,
                "stop_price": 11.8,
                "target_1": 13.05,
                "target_2": 13.3,
                "reward_risk_ratio": 1.5,
            },
            "historical_similar": {
                "sample_count": 42,
                "win_rate": 61.9,
                "expected_r": 0.48,
                "median_mfe_r": 1.6,
                "median_mae_r": 0.7,
                "note": "历史统计不代表未来收益。",
            },
            "factor_snapshot": {"close_vs_ma20_atr": 0.2, "volume_ratio_20": 0.8},
            "backtest": {
                "metrics": {
                    "trade_count": 42,
                    "win_rate": 61.9,
                    "expectancy_r": 0.48,
                    "profit_factor": 1.7,
                    "cumulative_return": 18.2,
                    "max_drawdown": -6.1,
                    "average_holding_bars": 8.2,
                    "sharpe": 1.1,
                }
            },
            "wave": {
                "candidates": [
                    {
                        "pattern": "unfinished_impulse",
                        "current_wave": 5,
                        "status": "developing",
                        "direction": "up",
                        "scale": "标准尺度",
                        "current_state": "waiting",
                        "current_state_label": "等待收盘确认",
                        "confidence": 0.72,
                        "projection": {
                            "primary_zone": [13.4, 13.8],
                            "confirmation": 12.8,
                            "invalidation": 11.9,
                            "path_direction": "up",
                        },
                        "historical_validation": {
                            "sample_count": 12,
                            "resolved_count": 8,
                            "calibrated": False,
                            "lookahead_bars": 20,
                        },
                    }
                ]
            },
        },
        "chart_html": (
            '<div class="plotly-graph-div" style="height:420px"></div>'
            "<script>document.currentScript.previousElementSibling._fullLayout = {};</script>"
        ),
        "download_url": "/api/report/offline/download",
    }


def _fulfill(route: Route) -> None:
    route.fulfill(status=200, content_type="application/json", body=json.dumps(_payload()))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        for name, width, height in (("desktop", 1440, 1000), ("mobile", 390, 844)):
            page = browser.new_page(viewport={"width": width, "height": height})
            errors: list[str] = []
            page.on(
                "console",
                lambda message, captured=errors: (
                    captured.append(message.text) if message.type == "error" else None
                ),
            )
            page.route("**/api/analyze", _fulfill)
            page.goto(args.url, wait_until="networkidle")
            page.locator("#analyze-button").click()
            page.locator("#quant-signal").get_by_text("UPTREND", exact=False).wait_for()
            assert page.locator("#overview-setup").inner_text() == "趋势回踩确认"
            assert "¥12.18" in page.locator("#overview-entry-zone").inner_text()
            wave_text = page.locator("#wave-candidates").inner_text()
            assert "情景 1" in wave_text
            assert "13.4–13.8" in wave_text
            assert "情景 2" in wave_text
            assert "11.900" in wave_text
            assert "情景 3" in wave_text
            assert "样本不足" in wave_text
            assert not page.locator(".factor-details").get_attribute("open")
            audit_sections = page.locator(".audit-details")
            assert audit_sections.count() >= 4
            assert all(not audit_sections.nth(index).get_attribute("open") for index in range(4))
            indicator_audit = page.locator(".audit-details").filter(has_text="指标最新值")
            indicator_audit.locator("summary").click()
            assert indicator_audit.get_attribute("open") is not None
            assert indicator_audit.locator("#indicator-list").is_visible()
            page.evaluate(
                """() => {
                  const graph = document.querySelector("#chart .plotly-graph-div");
                  graph.layout = {
                    xaxis: {range: ["2025-01-01", "2025-06-30"], autorange: false},
                    yaxis: {autorange: true}
                  };
                  window.Plotly = {
                    relayout: async (nextGraph, view) => { nextGraph.__restoredView = view; },
                    Plots: {resize: () => {}}
                  };
                }"""
            )
            page.evaluate("runAnalysis(true)")
            page.wait_for_function(
                "document.querySelector('#chart .plotly-graph-div').__restoredView"
            )
            restored_view = page.evaluate(
                "document.querySelector('#chart .plotly-graph-div').__restoredView"
            )
            assert restored_view["xaxis.range"] == ["2025-01-01", "2025-06-30"]
            assert restored_view["xaxis.autorange"] is False
            assert "yaxis.range" not in restored_view
            overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
            assert not overflow, f"{name} 存在横向溢出"
            assert not errors, f"{name} 控制台错误: {errors}"
            results.append({"viewport": name, "overflow": overflow, "errors": errors})
            page.close()
        browser.close()
    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
