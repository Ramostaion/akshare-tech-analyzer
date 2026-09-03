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
            "gann": {
                "status": "active",
                "anchor_mode": "auto_confirmed_pivot",
                "direction": "up",
                "anchor": {
                    "timestamp": "2026-07-01T00:00:00",
                    "confirmed_at": "2026-07-04T00:00:00",
                    "price": 11.9,
                },
                "scale": {
                    "atr": 0.4,
                    "unit_per_bar": 0.05,
                    "method": "ATR14/8 每根 K 线",
                },
                "fan_lines": [],
                "price_levels": [
                    {"label": "50.0%", "price": 12.5},
                    {"label": "100.0%", "price": 13.1},
                ],
                "time_cycles": [{"bars": 24, "datetime": "2026-09-01T00:00:00"}],
                "confirmation": 12.8,
                "invalidation": 11.9,
                "current_state_label": "等待收盘突破确认位",
                "historical_validation": {
                    "sample_count": 9,
                    "resolved_count": 7,
                    "calibrated": False,
                },
                "note": "角线采用 ATR 归一化。",
            },
            "wyckoff": {
                "status": "active",
                "structure": "accumulation",
                "phase": "C",
                "current_event": "Spring",
                "structural_fit": 0.76,
                "range": {"support": 11.9, "resistance": 12.8},
                "events": [{"event": "Spring"}],
                "projection": {
                    "confirmation": 12.8,
                    "invalidation": 11.7,
                    "target_zone": [13.25, 13.7],
                },
                "historical_validation": {"resolved_count": 8, "calibrated": False},
                "note": "威科夫量价结构候选。",
            },
        },
        "chart_html": (
            '<div class="plotly-graph-div" style="height:420px"></div>'
            "<script>(()=>{const g=document.currentScript.previousElementSibling;"
            "g._fullLayout={xaxis:{matches:'x4'},xaxis2:{matches:'x4'},xaxis4:{}};"
            "g.layout={shapes:[],annotations:[]};"
            "g.data=[{meta:{algorithm:'wave'},visible:true},"
            "{meta:{algorithm:'gann'},visible:false},"
            "{meta:{algorithm:'wyckoff'},visible:false}];})();</script>"
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
            assert not page.locator(".parameter-details").get_attribute("open")
            page.locator("#analyze-button").click()
            page.locator("#overview-setup").get_by_text("趋势回踩确认").wait_for()
            assert page.locator("#overview-setup").inner_text() == "趋势回踩确认"
            assert "¥12.18" in page.locator("#overview-entry-zone").inner_text()
            assert "自动结构锚点" in page.locator("#gann-analysis").inner_text()
            assert "吸筹候选" in page.locator("#wyckoff-analysis").inner_text()
            layout = page.evaluate(
                """() => ({
                  decisionTop: document.querySelector('.decision-grid').getBoundingClientRect().top,
                  chartTop: document.querySelector('#chart').getBoundingClientRect().top,
                  bodyFont: parseFloat(getComputedStyle(
                    document.querySelector('#quant-history')
                  ).fontSize),
                  labelFont: parseFloat(getComputedStyle(
                    document.querySelector('.metrics dt')
                  ).fontSize),
                  favoriteSize: document.querySelector(
                    '#favorite-button'
                  ).getBoundingClientRect().height,
                })"""
            )
            assert layout["decisionTop"] < layout["chartTop"]
            assert layout["bodyFont"] >= 13
            assert layout["labelFont"] >= 12
            assert layout["favoriteSize"] >= 40
            wave_text = page.locator("#wave-candidates").inner_text()
            assert "情景 1" in wave_text
            assert "13.4–13.8" in wave_text
            assert "情景 2" in wave_text
            assert "11.900" in wave_text
            assert "情景 3" in wave_text
            assert "样本不足" not in wave_text
            page.locator(".wave-evidence summary").click()
            assert "样本不足" in page.locator("#wave-candidates").inner_text()
            page.locator(".quant-details summary").click()
            page.locator("#quant-signal").get_by_text("UPTREND", exact=False).wait_for()
            assert "信号质量分" in page.locator("#quant-signal").inner_text()
            page.evaluate(
                """() => {
                  window.Plotly = {
                    restyle: async (graph, update, indices) => {
                      indices.forEach((index) => { graph.data[index].visible = update.visible; });
                    },
                    relayout: async (graph, update) => {
                      graph.__algorithmRelayouts ||= [];
                      graph.__algorithmRelayouts.push(update);
                    },
                    Plots: {resize: () => {}}
                  };
                }"""
            )
            wave_button = page.locator('[data-algorithm="wave"]')
            gann_button = page.locator('[data-algorithm="gann"]')
            wyckoff_button = page.locator('[data-algorithm="wyckoff"]')
            assert wave_button.get_attribute("aria-pressed") == "true"
            assert gann_button.get_attribute("aria-pressed") == "false"
            assert wyckoff_button.get_attribute("aria-pressed") == "false"
            gann_button.click()
            wave_button.click()
            wyckoff_button.click()
            assert gann_button.get_attribute("aria-pressed") == "true"
            assert wave_button.get_attribute("aria-pressed") == "false"
            assert wyckoff_button.get_attribute("aria-pressed") == "true"
            algorithm_relayouts = page.evaluate(
                "document.querySelector('#chart .plotly-graph-div').__algorithmRelayouts || []"
            )
            assert not any(
                "range" in key or "autorange" in key
                for update in algorithm_relayouts
                for key in update
            )
            visibility = page.evaluate(
                "document.querySelector('#chart .plotly-graph-div').data"
                ".map((trace) => trace.visible)"
            )
            assert visibility == [False, True, True]
            assert not page.locator(".factor-details").get_attribute("open")
            audit_sections = page.locator(".audit-details")
            assert audit_sections.count() >= 4
            assert all(
                audit_sections.nth(index).get_attribute("open") is None for index in range(3)
            )
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
                    restyle: async (nextGraph, update, indices) => {
                      indices.forEach((index) => {
                        nextGraph.data[index].visible = update.visible;
                      });
                    },
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
            page.wait_for_function(
                """() => {
                  const data = document.querySelector('#chart .plotly-graph-div').data;
                  return data?.[0]?.visible === false && data?.[1]?.visible === true;
                }"""
            )
            overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
            assert not overflow, f"{name} 存在横向溢出"
            assert not errors, f"{name} 控制台错误: {errors}"
            results.append({"viewport": name, "overflow": overflow, "errors": errors})
            page.close()
        browser.close()
    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
