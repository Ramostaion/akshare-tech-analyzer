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
            "current_decision": {
                "status": "long_trigger",
                "headline": "做多 Trigger 已收盘确认",
                "summary": "严格规则已满足；这仍是确认事件，不是已成交记录。",
                "flat_action": "空仓：仅考虑下一根 K 线在计划区间内执行。",
                "holding_action": "持仓：继续按失效位管理，不重复加仓。",
                "trigger_condition": None,
                "invalidation_condition": None,
                "trigger_price": None,
                "invalidation_price": None,
                "validity_note": "默认仅对下一根 K 线有效。",
                "is_executable": True,
                "wave_context": {
                    "bias": "up",
                    "alignment": "supportive",
                    "note": "上行 Wave 5 形成阶段，与当前 Trigger 方向一致。",
                },
                "gann_context": {
                    "bias": "up",
                    "alignment": "supportive",
                    "note": "上行固定角线保持在 1×1 有利侧，与当前 Trigger 方向一致。",
                },
                "wyckoff_context": {
                    "bias": "up",
                    "alignment": "supportive",
                    "note": "吸筹候选进入 Phase D，与当前 Trigger 方向一致。",
                },
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
                "version": "3.0",
                "ambiguous": False,
                "retired_count": 2,
                "candidate_policy": "最近九个已确认 Pivot 内有限竞争。",
                "candidates": [
                    {
                        "pattern": "unfinished_impulse",
                        "current_wave": 5,
                        "status": "developing",
                        "direction": "up",
                        "scale": "标准尺度",
                        "current_state": "waiting",
                        "current_state_label": "等待收盘确认",
                        "age_bars": 4,
                        "lifecycle_id": "unfinished_impulse:up:2026-06-01",
                        "scale_agreement": 2,
                        "supporting_scales": ["标准尺度", "宽尺度"],
                        "skipped_pivots": 0,
                        "score_components": {
                            "fib_ratio": 0.7,
                            "momentum_volume": 0.8,
                            "duration_balance": 0.75,
                            "pivot_quality": 0.9,
                        },
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
                "version": "3.0",
                "anchor_mode": "confirmed_atr_zigzag_scored",
                "anchor_selection_policy": "新的同向重要 Pivot 完成右侧确认后晋升为当前主锚。",
                "direction": "up",
                "anchor": {
                    "timestamp": "2026-07-01T00:00:00",
                    "confirmed_at": "2026-07-04T00:00:00",
                    "price": 11.9,
                    "score": 78.0,
                },
                "scale": {
                    "atr": 0.4,
                    "unit_per_bar": 0.05,
                    "method": "ATR(14) × 0.25 / bar",
                },
                "fan_lines": [],
                "price_levels": [
                    {"label": "50.0%", "price": 12.5},
                    {"label": "100.0%", "price": 13.1},
                ],
                "time_windows": [{
                    "label": "1T", "base_cycle": 12, "bars_from_now": 8,
                    "score": 78,
                }],
                "forecast_horizon": {"main_bars": 15, "hard_cap_bars": 30},
                "angle_relation": {"2×1": "不利侧", "1×1": "有利侧", "1×2": "有利侧"},
                "confirmation": 12.8,
                "invalidation": 11.9,
                "current_state_label": "等待收盘突破确认位",
                "alternatives": [
                    {"direction": "up", "anchor": {"score": 78}, "structural_fit": 0.72},
                    {"direction": "down", "anchor": {"score": 63}, "structural_fit": 0.55},
                ],
                "ambiguous": False,
                "structural_fit": 0.72,
                "score_components": {
                    "anchor_quality": 0.7,
                    "scale_fit": 0.6,
                    "angle_state": 0.65,
                    "confirmation": 0.45,
                    "resonance": 0.5,
                },
                "confluence_zones": [],
                "scenarios": [{
                    "name": "突破并站稳 1×1", "confidence": 0.62,
                    "trigger": "收盘高于当前 1×1", "confirmation": "连续 2 根收盘确认",
                    "target_zones": [[13.4, 13.8]], "time_windows": [],
                    "invalidation": "收盘跌破 1×2",
                }],
                "historical_validation": {
                    "sample_count": 9,
                    "resolved_count": 7,
                    "angle_events": {
                        "sample_count": 9,
                        "horizon_5": {"direction_accuracy": 55.6},
                    },
                    "time_windows": {
                        "reversal_rate": 60.0,
                        "random_baseline_reversal_rate": 42.0,
                    },
                    "walk_forward": {"available": False, "note": "样本不足。"},
                    "calibrated": False,
                },
                "note": "角线采用 ATR 归一化。",
            },
            "wyckoff": {
                "status": "active",
                "version": "2.0",
                "structure": "accumulation",
                "phase": "C",
                "current_event": "Spring",
                "structural_fit": 0.76,
                "ambiguous": False,
                "score_gap": 0.14,
                "score_components": {
                    "range_stability": 82,
                    "event_sequence": 78,
                    "volume_price_quality": 73,
                    "follow_through": 65,
                    "conflict_penalty": 4,
                },
                "alternatives": [
                    {"structure": "accumulation", "structural_fit": 0.76},
                    {"structure": "distribution", "structural_fit": 0.62},
                ],
                "range": {
                    "support": 11.9,
                    "resistance": 12.8,
                    "age_bars": 68,
                    "quality": {
                        "containment": 0.86,
                        "support_tests": 3,
                        "resistance_tests": 4,
                        "width_atr": 4.5,
                    },
                },
                "events": [
                    {"event": "Spring", "confirmation_state": "follow_through_confirmed"}
                ],
                "projection": {
                    "confirmation": 12.8,
                    "invalidation": 11.7,
                    "target_zone": [13.25, 13.7],
                    "confirmation_status": "confirmed",
                    "confirmed_at": "2026-08-20T00:00:00",
                    "invalidation_basis": "LPS 回测低点",
                    "target_method": "冻结交易区间宽度的条件投影",
                },
                "historical_validation": {
                    "sample_count": 12,
                    "confirmation_count": 8,
                    "confirmation_calibrated": False,
                    "confirmed_resolved_count": 7,
                    "calibrated": False,
                    "sampling_policy": "每个冻结交易区间和方向只采样一次",
                },
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
            "{meta:{algorithm:'wyckoff'},visible:false},"
            "{meta:{overlay:'history_signals'},visible:'legendonly'}];})();</script>"
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
            assert "做多 Trigger 已收盘确认" in page.locator("#decision-banner").inner_text()
            assert "空仓：" in page.locator("#decision-flat-action").inner_text()
            assert page.locator("#execution-plan-details").get_attribute("open") is not None
            assert "江恩 Price-Time V3.0" in page.locator("#gann-analysis").inner_text()
            assert "随机基线" in page.locator("#gann-analysis").inner_text()
            assert "吸筹候选" in page.locator("#wyckoff-analysis").inner_text()
            assert "威科夫 V2.0" in page.locator("#wyckoff-analysis").inner_text()
            assert "每个冻结交易区间" in page.locator("#wyckoff-analysis").inner_text()
            assert "Phase D" in page.locator("#decision-wyckoff-context").inner_text()
            assert "1×1 有利侧" in page.locator("#decision-gann-context").inner_text()
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
            history_toggle = page.locator("#show-history-signals")
            assert wave_button.get_attribute("aria-pressed") == "true"
            assert gann_button.get_attribute("aria-pressed") == "false"
            assert wyckoff_button.get_attribute("aria-pressed") == "false"
            assert not history_toggle.is_checked()
            gann_button.click()
            wave_button.click()
            wyckoff_button.click()
            page.locator(".parameter-details summary").click()
            history_toggle.check(force=True)
            assert gann_button.get_attribute("aria-pressed") == "true"
            assert wave_button.get_attribute("aria-pressed") == "false"
            assert wyckoff_button.get_attribute("aria-pressed") == "true"
            assert history_toggle.is_checked()
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
            assert visibility == [False, True, True, True]
            history_toggle.uncheck(force=True)
            visibility = page.evaluate(
                "document.querySelector('#chart .plotly-graph-div').data"
                ".map((trace) => trace.visible)"
            )
            assert visibility == [False, True, True, False]
            assert not page.locator(".factor-details").get_attribute("open")
            audit_sections = page.locator(".audit-details:not(.execution-plan-details)")
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
            pending_payload = _payload()
            pending_payload["quant"]["current_signal"] = None
            pending_payload["quant"]["current_decision"] = {
                "status": "watch",
                "headline": "交易结构观察中，尚未触发",
                "summary": "当前识别到趋势回踩；只有收盘确认后才生成执行计划。",
                "flat_action": "空仓：继续等待，不提前买入。",
                "holding_action": "持仓：维持原有风控。",
                "trigger_condition": "收盘站上上一根 K 线高点",
                "invalidation_condition": "回踩结构不再成立",
                "trigger_price": 12.8,
                "invalidation_price": 11.8,
                "validity_note": "条件只按最新一根已收盘 K 线判断。",
                "is_executable": False,
            }
            page.evaluate("(data) => renderResult(data)", pending_payload)
            assert "尚未触发" in page.locator("#decision-headline").inner_text()
            assert "收盘站上" in page.locator("#decision-trigger").inner_text()
            assert page.locator("#execution-plan-details").get_attribute("open") is None
            overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
            assert not overflow, f"{name} 存在横向溢出"
            assert not errors, f"{name} 控制台错误: {errors}"
            results.append({"viewport": name, "overflow": overflow, "errors": errors})
            page.close()
        browser.close()
    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
