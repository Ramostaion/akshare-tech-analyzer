from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from app.cache import SQLiteCache
from app.config import SHANGHAI_TZ, Settings
from app.main import app
from app.models import MarketData, ProviderError, SecurityInfo
from app.service import AnalyzerService


class FixedProvider:
    def __init__(self, frame) -> None:
        self.frame = frame

    def identify(self, symbol: str, asset_type: str = "auto") -> SecurityInfo:
        return SecurityInfo(
            symbol=symbol,
            name="测试证券",
            asset_type="etf" if symbol == "510300" else "stock",
            detection_method="mock_etf_list",
            data_source="测试固定数据",
            updated_at=datetime.now(SHANGHAI_TZ),
            market_status="已收盘",
        )

    def get_history(
        self,
        symbol: str,
        asset_type: str,
        period: str,
        adjust: str,
        start,
        end,
        force_refresh: bool = False,
    ) -> MarketData:
        security = self.identify(symbol, asset_type)
        return MarketData(
            frame=self.frame.copy(),
            security=security,
            period=period,
            adjust=adjust,
            fetched_at=datetime.now(SHANGHAI_TZ),
            from_cache=False,
            quality_notes=["测试固定行情"],
        )


def _install_service(tmp_path, market_frame) -> None:
    app_settings = Settings(
        cache_db=tmp_path / "cache" / "market.db", report_dir=tmp_path / "reports"
    )
    cache = SQLiteCache(app_settings.cache_db)
    app.state.service = AnalyzerService(FixedProvider(market_frame), cache, app_settings)


def test_health_home_and_security(tmp_path, market_frame) -> None:
    _install_service(tmp_path, market_frame)
    with TestClient(app) as client:
        health = client.get("/health")
        home = client.get("/")
        security = client.get("/api/security/600011")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert "技术分析工作台" in home.text
    assert security.json()["security"]["name"] == "测试证券"


def test_analyze_and_offline_report(tmp_path, market_frame) -> None:
    _install_service(tmp_path, market_frame)
    payload = {
        "symbol": "600011",
        "asset_type": "stock",
        "period": "daily",
        "adjust": "qfq",
        "start": "2024-01-01",
        "end": "2026-08-29",
        "show_kdj": True,
    }
    with TestClient(app) as client:
        response = client.post("/api/analyze", json=payload)
        assert response.status_code == 200
        body = response.json()
        report = client.get(body["report_url"])
        download = client.get(body["download_url"])
    assert body["metadata"]["security"]["symbol"] == "600011"
    assert body["analysis"]["state"] != "数据不足"
    assert "Plotly.newPlot" in body["chart_html"]
    assert '"dragmode":"pan"' in body["chart_html"]
    assert "__akshareShapeUndo" in body["chart_html"]
    assert report.status_code == 200
    assert download.status_code == 200
    assert "Plotly.newPlot" in report.text
    assert "__akshareShapeUndo" in report.text
    assert "600011" in report.text
    assert "仅为算法技术分析结果，不构成投资建议" in report.text
    assert "attachment" in download.headers["content-disposition"]


def test_api_validation_and_stable_errors(tmp_path, market_frame) -> None:
    _install_service(tmp_path, market_frame)
    with TestClient(app) as client:
        invalid = client.post("/api/analyze", json={"symbol": "abc"})
        bad_symbol = client.get("/api/security/not-code")
        missing_report = client.get("/api/report/not-found")
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "INVALID_REQUEST"
    assert bad_symbol.json()["error"]["code"] == "INVALID_SYMBOL"
    assert missing_report.status_code == 404
    assert missing_report.json()["error"]["code"] == "REPORT_NOT_FOUND"


class BrokenProvider(FixedProvider):
    def get_history(self, *args, **kwargs):
        raise ProviderError("DATA_SOURCE_UNAVAILABLE", "测试数据源故障")


def test_data_source_failure_has_no_stack(tmp_path, market_frame) -> None:
    app_settings = Settings(
        cache_db=tmp_path / "cache" / "market.db", report_dir=tmp_path / "reports"
    )
    cache = SQLiteCache(app_settings.cache_db)
    app.state.service = AnalyzerService(BrokenProvider(market_frame), cache, app_settings)
    with TestClient(app) as client:
        response = client.post("/api/analyze", json={"symbol": "600011"})
    assert response.status_code == 503
    assert response.json() == {
        "error": {"code": "DATA_SOURCE_UNAVAILABLE", "message": "测试数据源故障", "detail": None}
    }


class UsFixedProvider(FixedProvider):
    def identify(self, symbol: str, asset_type: str = "us_stock") -> SecurityInfo:
        return SecurityInfo(
            symbol=symbol,
            canonical_symbol=symbol,
            provider_symbol=f"106.{symbol}",
            name="苹果",
            asset_type="us_stock",
            detection_method="mock_us_table",
            data_source="测试美股数据",
            source="测试源",
            updated_at=datetime.now(SHANGHAI_TZ),
            market_status="已收盘",
            exchange="NASDAQ",
            currency="USD",
            timezone="America/New_York",
            capabilities={"periods": ["daily"], "adjustments": ["none"]},
        )


def test_us_api_metadata_colors_and_report(tmp_path, market_frame) -> None:
    app_settings = Settings(
        cache_db=tmp_path / "cache" / "market.db", report_dir=tmp_path / "reports"
    )
    cache = SQLiteCache(app_settings.cache_db)
    app.state.service = AnalyzerService(UsFixedProvider(market_frame), cache, app_settings)
    with TestClient(app) as client:
        response = client.post(
            "/api/analyze",
            json={"symbol": "AAPL", "asset_type": "us_stock", "adjust": "none"},
        )
        report = client.get(response.json()["report_url"])
    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["security"]["provider_symbol"] == "106.AAPL"
    assert body["metadata"]["security"]["currency"] == "USD"
    assert '"fillcolor":"#22c55e"' in body["chart_html"]
    assert "NASDAQ" in report.text
    assert "仅为算法技术分析结果，不构成投资建议" in report.text
