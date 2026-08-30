"""连接行情、指标、规则、图表与报告的应用服务。"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.analysis import analyze_technical_state
from app.backtest import run_signal_backtest
from app.cache import SQLiteCache
from app.charts import create_figure, render_figure_html
from app.config import Settings, settings
from app.data_provider import MarketDataProvider
from app.indicators import add_indicators
from app.levels import identify_levels
from app.logging_config import get_logger
from app.models import AnalyzeRequest, MarketData
from app.report import build_report_html, safe_report_filename, write_report

logger = get_logger("service")


@dataclass(slots=True)
class AnalysisBundle:
    market_data: MarketData
    analysis: dict[str, Any]
    levels: dict[str, Any]
    chart_html: str
    report_id: str
    report_path: Path

    def api_payload(self, request: AnalyzeRequest) -> dict[str, Any]:
        return {
            "request": request.model_dump(mode="json"),
            "metadata": self.market_data.metadata(),
            "analysis": self.analysis,
            "levels": self.levels,
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
        figure = create_figure(enriched, analysis, levels, request, title)
        chart_html = render_figure_html(figure, full_html=False)
        report_html = build_report_html(figure, market_data, request, analysis, levels)
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
            chart_html=chart_html,
            report_id=report_id,
            report_path=report_path,
        )
