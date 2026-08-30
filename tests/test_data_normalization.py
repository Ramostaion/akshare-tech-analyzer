from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.cache import SQLiteCache
from app.config import Settings
from app.data_provider import CANONICAL_COLUMNS, MarketDataProvider, normalize_market_frame
from app.models import ProviderError


def _chinese_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "日期": ["2026-08-29", "2026-08-28", "2026-08-28", "bad", "2026-08-30"],
            "开盘": [10.2, 10.0, 10.1, 10.0, 10.0],
            "收盘": [10.3, 10.1, 10.15, 10.0, 10.2],
            "最高": [10.4, 10.2, 10.3, 10.1, 10.1],
            "最低": [10.1, 9.9, 10.0, 9.9, 9.8],
            "成交量": [100, 80, 90, 50, 70],
            "成交额": [1000, 800, 900, 500, 700],
            "涨跌幅": [1.0, 0.5, 0.6, 0.0, 1.0],
        }
    )


def test_chinese_columns_sort_duplicate_and_invalid_ohlc() -> None:
    result = normalize_market_frame(_chinese_frame())
    assert list(result.columns) == CANONICAL_COLUMNS
    assert len(result) == 2
    assert result["datetime"].is_monotonic_increasing
    assert result.loc[0, "open"] == 10.1
    assert result["datetime"].is_unique


def test_english_etf_columns_are_normalized() -> None:
    raw = pd.DataFrame(
        {
            "datetime": ["2026-08-28 09:35:00"],
            "open": [4.0],
            "high": [4.1],
            "low": [3.9],
            "close": [4.05],
            "volume": [1234],
        }
    )
    result = normalize_market_frame(raw)
    assert len(result) == 1
    assert result.loc[0, "amount"] is pd.NA or pd.isna(result.loc[0, "amount"])


def test_empty_frame_has_stable_schema() -> None:
    result = normalize_market_frame(pd.DataFrame())
    assert result.empty
    assert list(result.columns) == CANONICAL_COLUMNS


class FakeAk:
    def fund_etf_spot_em(self) -> pd.DataFrame:
        return pd.DataFrame({"代码": ["510300"], "名称": ["沪深300ETF"]})

    def stock_individual_info_em(self, symbol: str) -> pd.DataFrame:
        return pd.DataFrame({"item": ["股票简称"], "value": ["华能国际"]})

    def stock_zh_a_hist(
        self, symbol: str, period: str, start_date: str, end_date: str, adjust: str
    ) -> pd.DataFrame:
        return _chinese_frame().iloc[:3]

    def fund_etf_hist_em(
        self, symbol: str, period: str, start_date: str, end_date: str, adjust: str
    ) -> pd.DataFrame:
        return _chinese_frame().iloc[:3]


def test_provider_auto_detection_and_cache(tmp_path) -> None:
    app_settings = Settings(cache_db=tmp_path / "market.db", report_dir=tmp_path / "reports")
    cache = SQLiteCache(app_settings.cache_db)
    provider = MarketDataProvider(cache, app_settings, FakeAk())
    etf = provider.get_history(
        "510300", "auto", "daily", "qfq", date(2026, 1, 1), date(2026, 8, 29)
    )
    stock = provider.get_history(
        "600011", "auto", "daily", "qfq", date(2026, 1, 1), date(2026, 8, 29)
    )
    cached = provider.get_history(
        "510300", "auto", "daily", "qfq", date(2026, 1, 1), date(2026, 8, 29)
    )
    assert etf.security.asset_type == "etf"
    assert etf.security.detection_method.startswith("akshare_etf_list")
    assert stock.security.asset_type == "stock"
    assert stock.security.name == "华能国际"
    assert cached.from_cache is True


class IncrementalAk(FakeAk):
    def __init__(self) -> None:
        self.ranges: list[tuple[str, str]] = []

    def stock_zh_a_hist(
        self, symbol: str, period: str, start_date: str, end_date: str, adjust: str
    ) -> pd.DataFrame:
        self.ranges.append((start_date, end_date))
        dates = pd.date_range(
            pd.to_datetime(start_date), pd.to_datetime(end_date), freq="B"
        )
        close = pd.Series(np.arange(len(dates)), dtype=float) * 0.1 + 10
        return pd.DataFrame(
            {
                "日期": dates,
                "开盘": close - 0.05,
                "收盘": close,
                "最高": close + 0.1,
                "最低": close - 0.1,
                "成交量": 100_000,
                "成交额": 1_000_000,
            }
        )


def test_history_cache_fetches_only_missing_date_range(tmp_path) -> None:
    app_settings = Settings(cache_db=tmp_path / "market.db", report_dir=tmp_path / "reports")
    ak = IncrementalAk()
    provider = MarketDataProvider(SQLiteCache(app_settings.cache_db), app_settings, ak)

    provider.get_history(
        "600011", "stock", "daily", "qfq", date(2026, 8, 3), date(2026, 8, 14)
    )
    expanded = provider.get_history(
        "600011", "stock", "daily", "qfq", date(2026, 8, 3), date(2026, 8, 21)
    )

    assert ak.ranges == [("20260803", "20260814"), ("20260815", "20260821")]
    assert expanded.cache_status["mode"] == "incremental_update"
    assert expanded.cache_status["new_rows"] == 5
    assert expanded.metadata()["data_quality"]["status"] == "良好"


class EmptyAk(FakeAk):
    def stock_zh_a_hist(
        self, symbol: str, period: str, start_date: str, end_date: str, adjust: str
    ) -> pd.DataFrame:
        return pd.DataFrame()


def test_provider_empty_data_is_readable_error(tmp_path) -> None:
    app_settings = Settings(cache_db=tmp_path / "market.db", report_dir=tmp_path / "reports")
    provider = MarketDataProvider(SQLiteCache(app_settings.cache_db), app_settings, EmptyAk())
    with pytest.raises(ProviderError, match="未返回") as error:
        provider.get_history("600011", "stock", "daily", "qfq", date(2026, 1, 1), date(2026, 8, 29))
    assert error.value.code == "EMPTY_DATA"


class FallbackAk(FakeAk):
    def stock_zh_a_hist(
        self, symbol: str, period: str, start_date: str, end_date: str, adjust: str
    ) -> pd.DataFrame:
        raise ConnectionError("东方财富连接中断")

    def stock_zh_a_hist_tx(
        self, symbol: str, start_date: str, end_date: str, adjust: str
    ) -> pd.DataFrame:
        dates = pd.date_range("2026-07-01", periods=40, freq="D")
        close = pd.Series(range(1000, 1040), dtype=float) / 100
        return pd.DataFrame(
            {
                "date": dates,
                "open": close - 0.05,
                "close": close,
                "high": close + 0.1,
                "low": close - 0.1,
                "volume": 1_000_000.0,
                "turnover": 0.012,
                "amount": 10_000_000.0,
            }
        )


def test_stock_daily_falls_back_to_tencent_and_converts_units(tmp_path) -> None:
    app_settings = Settings(
        cache_db=tmp_path / "market.db",
        report_dir=tmp_path / "reports",
        request_retries=1,
    )
    provider = MarketDataProvider(SQLiteCache(app_settings.cache_db), app_settings, FallbackAk())
    result = provider.get_history(
        "600011", "stock", "daily", "qfq", date(2026, 7, 1), date(2026, 8, 29)
    )
    assert result.security.data_source == "AKShare / 腾讯（东方财富失败后降级）"
    assert result.frame["volume"].iloc[-1] == 10_000
    assert result.frame["turnover"].iloc[-1] == pytest.approx(1.2)
    assert result.frame["pct_change"].iloc[-1] > 0
    assert any("腾讯日线备用源" in note for note in result.quality_notes)


class EtfFallbackAk(FallbackAk):
    def fund_etf_hist_em(
        self, symbol: str, period: str, start_date: str, end_date: str, adjust: str
    ) -> pd.DataFrame:
        raise ConnectionError("东方财富 ETF 历史接口连接中断")


def test_etf_daily_falls_back_to_tencent(tmp_path) -> None:
    app_settings = Settings(
        cache_db=tmp_path / "market.db",
        report_dir=tmp_path / "reports",
        request_retries=1,
    )
    provider = MarketDataProvider(SQLiteCache(app_settings.cache_db), app_settings, EtfFallbackAk())
    result = provider.get_history(
        "510760", "etf", "daily", "qfq", date(2026, 7, 1), date(2026, 8, 29)
    )
    assert result.security.asset_type == "etf"
    assert result.security.data_source == "AKShare / 腾讯（东方财富失败后降级）"
    assert result.frame["volume"].iloc[-1] == 10_000
    assert any("腾讯日线备用源" in note for note in result.quality_notes)


class CircuitBreakerAk(FallbackAk):
    def __init__(self) -> None:
        self.history_calls = 0

    def stock_zh_a_hist(
        self, symbol: str, period: str, start_date: str, end_date: str, adjust: str
    ) -> pd.DataFrame:
        self.history_calls += 1
        raise ConnectionError("东方财富历史接口连接中断")


def test_stock_history_circuit_breaker_skips_repeated_primary_calls(tmp_path) -> None:
    app_settings = Settings(
        cache_db=tmp_path / "market.db",
        report_dir=tmp_path / "reports",
        request_retries=1,
    )
    ak = CircuitBreakerAk()
    provider = MarketDataProvider(SQLiteCache(app_settings.cache_db), app_settings, ak)
    request = ("600011", "stock", "daily", "qfq", date(2026, 7, 1), date(2026, 8, 29))
    provider.get_history(*request)
    provider.get_history(*request, force_refresh=True)
    assert ak.history_calls == 1


@pytest.mark.parametrize(("period", "maximum_rows"), [("weekly", 7), ("monthly", 2)])
def test_tencent_fallback_resamples_longer_periods(tmp_path, period, maximum_rows) -> None:
    app_settings = Settings(
        cache_db=tmp_path / f"{period}.db",
        report_dir=tmp_path / "reports",
        request_retries=1,
    )
    provider = MarketDataProvider(SQLiteCache(app_settings.cache_db), app_settings, FallbackAk())
    result = provider.get_history(
        "600011", "stock", period, "qfq", date(2026, 7, 1), date(2026, 8, 29)
    )
    assert len(result.frame) <= maximum_rows
    assert result.frame["datetime"].is_monotonic_increasing
    assert result.frame["volume"].sum() == 400_000


def _sina_minute_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "day": [
                "2026-08-27 15:00:00",
                "2026-08-28 09:35:00",
                "2026-08-28 09:40:00",
            ],
            "open": [9.9, 10.0, 10.1],
            "high": [10.1, 10.2, 10.3],
            "low": [9.8, 9.9, 10.0],
            "close": [10.0, 10.1, 10.2],
            "volume": [100_000, 200_000, 300_000],
            "amount": [1_000_000, 2_000_000, 3_000_000],
        }
    )


class MinuteFallbackAk(FakeAk):
    def stock_zh_a_hist_min_em(
        self, symbol: str, start_date: str, end_date: str, period: str, adjust: str
    ) -> pd.DataFrame:
        raise ConnectionError("东方财富分钟接口连接失败")

    def fund_etf_hist_min_em(
        self, symbol: str, start_date: str, end_date: str, period: str, adjust: str
    ) -> pd.DataFrame:
        raise ConnectionError("东方财富 ETF 分钟接口连接失败")

    def stock_zh_a_hist_tx(
        self, symbol: str, start_date: str, end_date: str, adjust: str
    ) -> pd.DataFrame:
        factor = 0.5 if adjust == "qfq" else 1.0
        dates = pd.Series(pd.date_range("2026-08-27", periods=2, freq="D")).astype(
            "datetime64[s]"
        )
        return pd.DataFrame(
            {
                "date": dates,
                "open": [10.0 * factor, 10.0 * factor],
                "high": [10.2 * factor, 10.2 * factor],
                "low": [9.8 * factor, 9.8 * factor],
                "close": [10.0 * factor, 10.0 * factor],
                "volume": [1_000_000, 1_000_000],
            }
        )


@pytest.mark.parametrize(
    ("period", "scale"),
    [("1m", "1"), ("5m", "5"), ("15m", "15"), ("30m", "30"), ("60m", "60")],
)
def test_stock_minute_periods_fall_back_and_trim_dates(
    tmp_path, monkeypatch, period, scale
) -> None:
    app_settings = Settings(
        cache_db=tmp_path / f"{period}.db",
        report_dir=tmp_path / "reports",
        request_retries=1,
    )
    provider = MarketDataProvider(
        SQLiteCache(app_settings.cache_db), app_settings, MinuteFallbackAk()
    )
    received_scales: list[str] = []

    def fake_sina(symbol: str, requested_scale: str) -> pd.DataFrame:
        assert symbol == "600011"
        received_scales.append(requested_scale)
        return _sina_minute_frame()

    monkeypatch.setattr(provider, "_fetch_sina_minute_raw", fake_sina)
    result = provider.get_history(
        "600011",
        "stock",
        period,
        "none",
        date(2026, 8, 28),
        date(2026, 8, 28),
    )

    assert received_scales == [scale]
    assert len(result.frame) == 2
    assert result.frame["datetime"].dt.date.unique().tolist() == [date(2026, 8, 28)]
    assert result.frame["volume"].tolist() == [2_000, 3_000]
    assert result.security.data_source == "新浪分钟行情（东方财富失败后降级）"
    assert any("新浪分钟备用源" in note for note in result.quality_notes)


def test_etf_minute_fallback_applies_qfq_factor(tmp_path, monkeypatch) -> None:
    app_settings = Settings(
        cache_db=tmp_path / "etf-minute.db",
        report_dir=tmp_path / "reports",
        request_retries=1,
    )
    provider = MarketDataProvider(
        SQLiteCache(app_settings.cache_db), app_settings, MinuteFallbackAk()
    )
    monkeypatch.setattr(
        provider,
        "_fetch_sina_minute_raw",
        lambda symbol, period: _sina_minute_frame(),
    )
    result = provider.get_history(
        "510300",
        "etf",
        "5m",
        "qfq",
        date(2026, 8, 28),
        date(2026, 8, 28),
    )

    assert result.frame["close"].tolist() == pytest.approx([5.05, 5.1])
    assert result.frame["high"].tolist() == pytest.approx([5.1, 5.15])
    assert result.security.data_source.endswith("腾讯日线复权因子")
    assert any("复权因子" in note for note in result.quality_notes)
