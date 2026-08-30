from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from pydantic import ValidationError

from app.cache import SQLiteCache
from app.config import Settings
from app.data_provider import CANONICAL_COLUMNS, MarketDataProvider
from app.models import AnalyzeRequest, ProviderError
from app.report import safe_report_filename


def _bars(size: int = 80) -> pd.DataFrame:
    dates = pd.date_range("2025-01-02", periods=size, freq="B")
    close = pd.Series(range(size), dtype=float) * 0.25 + 100
    return pd.DataFrame(
        {
            "日期": dates,
            "开盘": close - 0.2,
            "收盘": close,
            "最高": close + 0.5,
            "最低": close - 0.5,
            "成交量": 1_000_000,
            "成交额": 100_000_000,
        }
    )


class GlobalAkMock:
    def __init__(self) -> None:
        self.us_history_symbol: str | None = None

    @staticmethod
    def stock_us_spot_em() -> pd.DataFrame:
        return pd.DataFrame(
            {"代码": ["106.AAPL", "105.SPCX"], "名称": ["苹果", "SPAC指数公司"]}
        )

    def stock_us_hist(
        self, symbol: str, period: str, start_date: str, end_date: str, adjust: str
    ) -> pd.DataFrame:
        self.us_history_symbol = symbol
        return _bars()

    @staticmethod
    def stock_us_daily(symbol: str, adjust: str = "") -> pd.DataFrame:
        return _bars().rename(
            columns={
                "日期": "date",
                "开盘": "open",
                "收盘": "close",
                "最高": "high",
                "最低": "low",
                "成交量": "volume",
                "成交额": "amount",
            }
        )

    @staticmethod
    def stock_us_hist_min_em(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        frame = _bars(8).rename(columns={"日期": "时间"})
        frame["时间"] = pd.date_range("2026-08-24 09:30", periods=8, freq="min")
        return frame

    @staticmethod
    def index_us_stock_sina(symbol: str) -> pd.DataFrame:
        return _bars().rename(
            columns={
                "日期": "date",
                "开盘": "open",
                "收盘": "close",
                "最高": "high",
                "最低": "low",
                "成交量": "volume",
                "成交额": "amount",
            }
        )

    @staticmethod
    def futures_hq_subscribe_exchange_symbol() -> pd.DataFrame:
        return pd.DataFrame(
            {"symbol": ["COMEX黄金", "COMEX白银", "其他"], "code": ["GC", "SI", "ZZ"]}
        )

    @staticmethod
    def futures_foreign_hist(symbol: str) -> pd.DataFrame:
        frame = _bars().rename(
            columns={
                "日期": "date",
                "开盘": "open",
                "收盘": "close",
                "最高": "high",
                "最低": "low",
                "成交量": "volume",
            }
        )
        frame["settlement"] = frame["close"] - 0.1
        frame["open_interest"] = 50_000
        return frame

    @staticmethod
    def futures_foreign_commodity_realtime(symbol: str) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "最新价": [2450.5],
                "涨跌幅": [1.2],
                "涨跌额": [29.1],
                "开盘价": [2420.0],
                "最高价": [2460.0],
                "最低价": [2410.0],
                "昨结算": [2421.4],
                "持仓量": [123456],
                "日期": ["2026-08-29"],
                "行情时间": ["15:30:00"],
            }
        )


@pytest.fixture
def global_provider(tmp_path) -> tuple[MarketDataProvider, GlobalAkMock]:
    mock = GlobalAkMock()
    settings = Settings(
        cache_db=tmp_path / "cache.db",
        report_dir=tmp_path / "reports",
        request_retries=1,
    )
    provider = MarketDataProvider(SQLiteCache(settings.cache_db), settings, mock)
    return provider, mock


def test_us_ticker_uses_code_table_provider_symbol(global_provider) -> None:
    provider, mock = global_provider
    info = provider.identify("aapl", "us_stock")
    assert info.symbol == "AAPL"
    assert info.provider_symbol == "106.AAPL"
    assert info.currency == "USD"
    market = provider.get_history(
        "AAPL", "us_stock", "daily", "none", date(2025, 1, 1), date(2026, 8, 29)
    )
    assert mock.us_history_symbol == "106.AAPL"
    assert market.volume_unit == "股"
    assert list(market.frame.columns) == CANONICAL_COLUMNS
    assert set(market.frame["currency"].dropna()) == {"USD"}


def test_unknown_us_ticker_is_not_guessed(global_provider) -> None:
    provider, _ = global_provider
    with pytest.raises(ProviderError, match="未找到"):
        provider.identify("NOPE", "us_stock")


class BrokenEastmoneyUsListMock(GlobalAkMock):
    @staticmethod
    def stock_us_spot_em() -> pd.DataFrame:
        raise RuntimeError("eastmoney code table unavailable")


def test_us_ticker_falls_back_to_sina_when_code_table_is_unavailable(tmp_path) -> None:
    settings = Settings(
        cache_db=tmp_path / "cache.db",
        report_dir=tmp_path / "reports",
        request_retries=1,
    )
    provider = MarketDataProvider(
        SQLiteCache(settings.cache_db), settings, BrokenEastmoneyUsListMock()
    )

    suggestions = provider.search_instruments("lmt", "us_stock")
    market = provider.get_history(
        "LMT", "us_stock", "daily", "none", date(2025, 1, 1), date(2026, 8, 29)
    )

    assert suggestions[0]["symbol"] == "LMT"
    assert market.security.provider_symbol == "LMT"
    assert market.security.detection_method == "sina_ticker_fallback"
    assert "新浪财经美股" in market.security.data_source
    assert not market.frame.empty


def test_us_index_history_can_be_resampled(global_provider) -> None:
    provider, _ = global_provider
    market = provider.get_history(
        ".IXIC", "us_index", "weekly", "none", date(2025, 1, 1), date(2026, 8, 29)
    )
    assert market.security.name == "纳斯达克综合指数"
    assert 10 < len(market.frame) < 80
    assert market.frame["turnover"].isna().all()


def test_future_history_and_snapshot_are_distinct(global_provider) -> None:
    provider, _ = global_provider
    market = provider.get_history(
        "GC", "global_future", "daily", "none", date(2025, 1, 1), date(2026, 8, 29)
    )
    assert market.security.series_type == "连续参考序列（非具体合约）"
    assert market.snapshot is not None
    assert market.snapshot["latest"] == 2450.5
    assert market.frame["open_interest"].notna().all()
    assert any("换月" in note for note in market.quality_notes)


@pytest.mark.parametrize("period", ["weekly", "monthly"])
def test_future_history_can_be_resampled(global_provider, period: str) -> None:
    provider, _ = global_provider
    market = provider.get_history(
        "GC", "global_future", period, "none", date(2025, 1, 1), date(2026, 8, 29)
    )

    assert 0 < len(market.frame) < 80
    assert any("本地聚合" in note for note in market.quality_notes)


@pytest.mark.parametrize(
    ("symbol", "asset_type", "period", "adjust"),
    [
        (".IXIC", "us_index", "1m", "none"),
        ("GC", "global_future", "1m", "none"),
        ("GC", "global_future", "daily", "qfq"),
        ("AAPL", "us_stock", "5m", "none"),
    ],
)
def test_unsupported_capabilities_are_rejected(
    symbol: str, asset_type: str, period: str, adjust: str
) -> None:
    with pytest.raises(ValidationError):
        AnalyzeRequest(
            symbol=symbol, asset_type=asset_type, period=period, adjust=adjust
        )


def test_international_default_is_unadjusted() -> None:
    request = AnalyzeRequest(symbol="AAPL", asset_type="us_stock")
    assert request.adjust == "none"


def test_instrument_search_and_safe_index_filename(global_provider) -> None:
    provider, _ = global_provider
    assert provider.search_instruments("苹果", "us_stock")[0]["symbol"] == "AAPL"
    request = AnalyzeRequest(symbol=".IXIC", asset_type="us_index")
    filename = safe_report_filename(request, "us_index")
    assert filename.startswith("IXIC_us_index_daily_none_")
    assert not filename.startswith(".")
