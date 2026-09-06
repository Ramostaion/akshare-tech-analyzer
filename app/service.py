"""连接行情、指标、规则、图表与报告的应用服务。"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.analysis import analyze_technical_state
from app.backtest import run_signal_backtest, run_strategy_backtest
from app.cache import SQLiteCache
from app.charts import create_figure, render_figure_html
from app.config import Settings, settings
from app.data_provider import MarketDataProvider
from app.decision import build_current_decision, resolve_current_signal
from app.execution import ExecutionConfig
from app.factors import build_factors, factor_snapshot
from app.gann import analyze_gann, gann_decision_context
from app.indicators import add_indicators
from app.levels import identify_levels
from app.logging_config import get_logger
from app.models import AnalyzeRequest, MarketData
from app.regime import classify_regime, regime_series
from app.report import build_report_html, safe_report_filename, write_report
from app.setups import current_setups, evaluate_setups
from app.signals import generate_signals
from app.wave import analyze_wave_candidates
from app.wyckoff import analyze_wyckoff, wyckoff_decision_context

logger = get_logger("service")


@dataclass(slots=True)
class AnalysisBundle:
    market_data: MarketData
    analysis: dict[str, Any]
    levels: dict[str, Any]
    quant: dict[str, Any]
    chart_html: str
    report_id: str
    report_path: Path

    def api_payload(self, request: AnalyzeRequest) -> dict[str, Any]:
        return {
            "request": request.model_dump(mode="json"),
            "metadata": self.market_data.metadata(),
            "analysis": self.analysis,
            "levels": self.levels,
            "quant": self.quant,
            "chart_html": self.chart_html,
            "report_id": self.report_id,
            "report_url": f"/api/report/{self.report_id}",
            "download_url": f"/api/report/{self.report_id}/download",
        }


class AnalyzerService:
    def __init__(
        self,
        provider: MarketDataProvider,
        cache: SQLiteCache,
        app_settings: Settings = settings,
    ) -> None:
        self.provider = provider
        self.cache = cache
        self.settings = app_settings

    def analyze(self, request: AnalyzeRequest, output_path: Path | None = None) -> AnalysisBundle:
        market_data = self.provider.get_history(
            symbol=request.symbol,
            asset_type=request.asset_type,
            period=request.period,
            adjust=request.adjust,
            start=request.start,
            end=request.end,
            force_refresh=request.force_refresh,
        )
        enriched = add_indicators(market_data.frame)
        analysis = analyze_technical_state(enriched)
        analysis["backtest"] = run_signal_backtest(enriched)
        levels = identify_levels(enriched, self.settings)
        factors = build_factors(enriched, levels)
        regimes = regime_series(enriched, factors)
        regime = classify_regime(enriched, factors)
        setup_frame = evaluate_setups(enriched, factors, regimes)
        signals = generate_signals(request.symbol, enriched, factors, regimes, setup_frame)
        execution_config = ExecutionConfig(
            entry_price=(
                "next_close"
                if self.settings.execution_entry_price == "next_close"
                else "next_open"
            ),
            commission_rate=self.settings.execution_commission_rate,
            slippage_bps=self.settings.execution_slippage_bps,
            t_plus_one=(
                self.settings.execution_t_plus_one_cn
                if market_data.security.asset_type in {"stock", "etf", "cn_stock", "cn_etf"}
                else False
            ),
            max_holding_bars=self.settings.execution_max_holding_bars,
            target_r_multiple=self.settings.execution_target_r,
            atr_stop_multiple=self.settings.execution_atr_stop,
        )
        strategy_backtest = run_strategy_backtest(enriched, signals, execution_config)
        latest_timestamp = pd.Timestamp(enriched["datetime"].iloc[-1]).to_pydatetime()
        current_signals = [signal for signal in signals if signal.timestamp == latest_timestamp]
        setup_items = current_setups(setup_frame)
        current_signal, signal_conflict = resolve_current_signal(current_signals)
        current_decision = build_current_decision(
            enriched,
            factors,
            setup_items,
            current_signals,
            current_signal,
            conflict=signal_conflict,
        )
        similar_setup_names = (
            [current_signal.setup]
            if current_signal is not None
            else [str(item["setup"]) for item in setup_items]
        )
        similar_stats = _similar_signal_statistics(
            strategy_backtest,
            similar_setup_names,
            current_signal.regime if current_signal is not None else regime["regime"],
            triggered=current_signal is not None
            or any(bool(item["triggered"]) for item in setup_items),
        )
        if current_signal is not None and similar_stats["sample_count"] >= 30:
            current_signal.historical_probability = similar_stats["win_rate"] / 100
        wave_analysis = analyze_wave_candidates(enriched)
        gann_analysis = analyze_gann(enriched)
        wyckoff_analysis = analyze_wyckoff(enriched)
        current_decision["gann_context"] = gann_decision_context(
            gann_analysis, str(current_decision["status"])
        )
        current_decision["wyckoff_context"] = wyckoff_decision_context(
            wyckoff_analysis, str(current_decision["status"])
        )
        quant = {
            "factor_snapshot": factor_snapshot(factors),
            "market_regime": regime,
            "current_setups": setup_items,
            "current_signal": current_signal.model_dump(mode="json") if current_signal else None,
            "current_decision": current_decision,
            "current_signal_conflict": [
                item.model_dump(mode="json") for item in current_signals
            ] if signal_conflict else [],
            "recent_signals": [item.model_dump(mode="json") for item in signals[-10:]],
            "signal_quality_score": current_signal.score if current_signal else None,
            "score_type": "RULE_SCORE",
            "historical_similar": similar_stats,
            "backtest": strategy_backtest,
            "wave": wave_analysis,
            "gann": gann_analysis,
            "wyckoff": wyckoff_analysis,
        }
        analysis["technical_score_label"] = "Market / Technical State Score"
        analysis["quant"] = quant
        security = market_data.security
        if security.asset_type == "global_future":
            for level in levels.get("supports", []) + levels.get("resistances", []):
                level["confidence"] = {"高": "中", "中": "低"}.get(
                    level["confidence"], level["confidence"]
                )
            analysis["warning"].append(
                "连续参考序列可能受换月跳空影响，关键位可信度已按较低等级展示。"
            )
        title = f"{security.symbol} {security.name}"
        figure = create_figure(
            enriched,
            analysis,
            levels,
            request,
            title,
            signals,
            wave_analysis,
            gann_analysis,
            wyckoff_analysis,
        )
        chart_html = render_figure_html(figure, full_html=False)
        report_html = build_report_html(figure, market_data, request, analysis, levels, quant)
        report_id = secrets.token_urlsafe(18)
        target = output_path or self.settings.report_dir / safe_report_filename(
            request, security.asset_type
        )
        report_path = write_report(report_html, target)
        request_payload = request.model_dump(mode="json")
        self.cache.save_analysis(report_id, request_payload, analysis)
        self.cache.save_report(report_id, report_path, request.symbol, request_payload)
        logger.info(
            "analysis_bundle_created symbol=%s period=%s rows=%s from_cache=%s report_id=%s",
            request.symbol,
            request.period,
            len(market_data.frame),
            market_data.from_cache,
            report_id,
        )
        return AnalysisBundle(
            market_data=market_data,
            analysis=analysis,
            levels=levels,
            quant=quant,
            chart_html=chart_html,
            report_id=report_id,
            report_path=report_path,
        )


def _similar_signal_statistics(
    backtest: dict[str, Any],
    setup_names: list[str],
    regime: str,
    *,
    triggered: bool,
) -> dict[str, Any]:
    """汇总当前一个或多个 Setup 在同 Regime 下的已完成历史交易。"""
    if not setup_names:
        return {
            "sample_count": 0,
            "win_rate": None,
            "expected_r": None,
            "median_mfe_r": None,
            "median_mae_r": None,
            "note": "当前没有可匹配的Setup。",
        }
    trades = [
        item
        for item in backtest.get("trades", [])
        if item["setup"] in setup_names and item["regime"] == regime
    ]
    if not trades:
        return {
            "sample_count": 0,
            "win_rate": None,
            "expected_r": None,
            "median_mfe_r": None,
            "median_mae_r": None,
            "note": "当前Setup在同Regime下暂无已完成历史样本。",
        }
    r_values = np.array([item["r_multiple"] for item in trades], dtype=float)
    return {
        "sample_count": len(trades),
        "win_rate": round(float(np.mean(r_values > 0) * 100), 2),
        "expected_r": round(float(np.mean(r_values)), 4),
        "median_mfe_r": round(float(np.median([item["mfe_r"] for item in trades])), 4),
        "median_mae_r": round(float(np.median([item["mae_r"] for item in trades])), 4),
        "note": (
            "历史统计不代表未来收益。少于30个样本时不显示历史概率。"
            if triggered
            else "Setup尚未触发；统计来自相同Setup与Regime的历史完成交易。"
        ),
    }
