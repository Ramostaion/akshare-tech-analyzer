"""AKShare 行情适配、证券识别、重试与规范化。"""

from __future__ import annotations

import inspect
import json
import math
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import UTC, date, datetime, timedelta
from datetime import time as clock_time
from hashlib import sha256
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from app.cache import CacheEntry, SQLiteCache
from app.config import SHANGHAI_TZ, Settings, settings
from app.logging_config import get_logger
from app.models import Adjust, AssetType, MarketData, Period, ProviderError, SecurityInfo

CANONICAL_COLUMNS = [
    "datetime",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "amplitude",
    "pct_change",
    "change",
    "turnover",
    "open_interest",
    "settlement",
    "currency",
    "source",
    "source_timestamp",
    "captured_at",
]

COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "datetime": ("datetime", "日期", "时间", "day", "date"),
    "open": ("open", "开盘"),
    "high": ("high", "最高"),
    "low": ("low", "最低"),
    "close": ("close", "收盘", "最新价"),
    "volume": ("volume", "成交量"),
    "amount": ("amount", "成交额"),
    "amplitude": ("amplitude", "振幅"),
    "pct_change": ("pct_change", "涨跌幅"),
    "change": ("change", "涨跌额"),
    "turnover": ("turnover", "换手率"),
    "open_interest": ("open_interest", "持仓量", "hold"),
    "settlement": ("settlement", "结算价", "昨结算"),
    "currency": ("currency", "币种"),
    "source": ("source", "数据源"),
    "source_timestamp": ("source_timestamp", "数据时间", "行情时间"),
    "captured_at": ("captured_at", "采集时间"),
}

ETF_FALLBACK_PREFIXES = ("15", "16", "18", "50", "51", "52", "56", "58")
MINUTE_PERIODS = {"1m": "1", "5m": "5", "15m": "15", "30m": "30", "60m": "60"}
MINUTE_PRIMARY_BREAKER_SECONDS = 300
HISTORY_PRIMARY_BREAKER_SECONDS = 120
US_INDEX_NAMES = {
    ".IXIC": "纳斯达克综合指数",
    ".NDX": "纳斯达克100指数",
    ".INX": "标普500指数",
    ".DJI": "道琼斯工业指数",
}
SUPPORTED_FUTURES = {"GC", "SI", "HG", "CL", "NG", "OIL", "XAU", "XAG"}

logger = get_logger("provider")


def _is_valid_us_ticker(symbol: str) -> bool:
    """Return whether a canonical US ticker is safe to pass to the Sina fallback."""
    return (
        1 <= len(symbol) <= 16
        and symbol[0].isalnum()
        and all(char.isascii() and (char.isalnum() or char in ".-") for char in symbol)
    )


def normalize_market_frame(raw: pd.DataFrame) -> pd.DataFrame:
    """把 AKShare 中文/英文行情列规范为固定列，排序去重并剔除非法 K 线。"""
    if raw is None or raw.empty:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)
    source = raw.copy()
    normalized = pd.DataFrame(index=source.index)
    for canonical, candidates in COLUMN_ALIASES.items():
        matched = next((name for name in candidates if name in source.columns), None)
        normalized[canonical] = source[matched] if matched is not None else pd.NA

    normalized["datetime"] = pd.to_datetime(normalized["datetime"], errors="coerce")
    for column in ("source_timestamp", "captured_at"):
        normalized[column] = pd.to_datetime(normalized[column], errors="coerce")
    text_columns = {"currency", "source"}
    datetime_columns = {"datetime", "source_timestamp", "captured_at"}
    numeric_columns = [
        column for column in CANONICAL_COLUMNS if column not in text_columns | datetime_columns
    ]
    for column in numeric_columns:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    normalized = normalized.dropna(subset=["datetime", "open", "high", "low", "close"])
    valid_ohlc = (
        (normalized["high"] >= normalized[["open", "close", "low"]].max(axis=1))
        & (normalized["low"] <= normalized[["open", "close", "high"]].min(axis=1))
        & (normalized[["open", "high", "low", "close"]] >= 0).all(axis=1)
    )
    valid_volume = normalized["volume"].isna() | (normalized["volume"] >= 0)
    normalized = normalized.loc[valid_ohlc & valid_volume]
    normalized = normalized.sort_values("datetime").drop_duplicates("datetime", keep="last")
    return normalized.reset_index(drop=True)[CANONICAL_COLUMNS]


def _stock_exchange_symbol(symbol: str) -> str:
    """将六位 A 股代码转换为腾讯/新浪接口使用的交易所前缀代码。"""
    if symbol.startswith(("4", "8")):
        return f"bj{symbol}"
    if symbol.startswith(("5", "6", "9")):
        return f"sh{symbol}"
    return f"sz{symbol}"


def normalize_tx_stock_frame(raw: pd.DataFrame, period: Period) -> pd.DataFrame:
    """规范腾讯日线，并把成交量从股转为手、换手率从小数转为百分比。"""
    source = raw.copy()
    if "volume" in source:
        source["volume"] = pd.to_numeric(source["volume"], errors="coerce") / 100
    if "turnover" in source:
        source["turnover"] = pd.to_numeric(source["turnover"], errors="coerce") * 100
    normalized = normalize_market_frame(source)
    if normalized.empty:
        return normalized

    if period in {"weekly", "monthly"}:
        frequency = "W-FRI" if period == "weekly" else "M"
        grouped = normalized.groupby(normalized["datetime"].dt.to_period(frequency), sort=True)
        normalized = grouped.agg(
            datetime=("datetime", "max"),
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
            amount=("amount", "sum"),
            turnover=("turnover", "sum"),
        ).reset_index(drop=True)
        for column in ("amplitude", "pct_change", "change"):
            normalized[column] = pd.NA
        for column in CANONICAL_COLUMNS:
            if column not in normalized:
                normalized[column] = pd.NA
        normalized = normalized[CANONICAL_COLUMNS]

    previous_close = normalized["close"].shift(1)
    normalized["change"] = normalized["change"].fillna(normalized["close"].diff())
    normalized["pct_change"] = normalized["pct_change"].fillna(
        normalized["close"].pct_change() * 100
    )
    normalized["amplitude"] = normalized["amplitude"].fillna(
        (normalized["high"] - normalized["low"]) / previous_close.replace(0, pd.NA) * 100
    )
    return normalized


def _records_from_frame(frame: pd.DataFrame) -> list[dict[str, Any]]:
    serializable = frame.copy()
    for column in ("datetime", "source_timestamp", "captured_at"):
        if column in serializable:
            values = pd.to_datetime(serializable[column], errors="coerce")
            serializable[column] = values.dt.strftime("%Y-%m-%dT%H:%M:%S")
    records: list[dict[str, Any]] = []
    for record in serializable.to_dict(orient="records"):
        records.append(
            {
                key: None
                if value is None or (not isinstance(value, (list, dict)) and pd.isna(value))
                else value
                for key, value in record.items()
            }
        )
    return records


def _frame_from_records(records: list[dict[str, Any]]) -> pd.DataFrame:
    return normalize_market_frame(pd.DataFrame.from_records(records))


class MarketDataProvider:
    """统一提供 A 股与 ETF 行情，封装所有 AKShare 直接调用。"""

    def __init__(
        self,
        cache: SQLiteCache | None = None,
        app_settings: Settings = settings,
        ak_module: Any | None = None,
    ) -> None:
        self.settings = app_settings
        self.cache = cache
        if ak_module is None:
            try:
                import akshare as ak_module  # type: ignore[no-redef]
            except ImportError as exc:
                raise ProviderError("DEPENDENCY_MISSING", "未安装 AKShare，无法获取行情") from exc
        self.ak = ak_module
        self._semaphore = threading.BoundedSemaphore(app_settings.max_provider_concurrency)
        self._executor = ThreadPoolExecutor(
            max_workers=max(app_settings.max_provider_concurrency, 1),
            thread_name_prefix="akshare-provider",
        )
        self._minute_primary_retry_after = 0.0
        self._minute_breaker_lock = threading.Lock()
        self._etf_list_lock = threading.Lock()
        self._us_list_lock = threading.Lock()
        self._future_list_lock = threading.Lock()
        self._source_breaker_lock = threading.Lock()
        self._source_retry_after: dict[str, float] = {}

    def _source_available(self, source: str) -> bool:
        """Return whether a temporarily failing upstream source may be retried."""
        with self._source_breaker_lock:
            return time.monotonic() >= self._source_retry_after.get(source, 0.0)

    def _open_source_breaker(
        self,
        source: str,
        seconds: int = HISTORY_PRIMARY_BREAKER_SECONDS,
    ) -> None:
        """Avoid repeatedly hammering an upstream source after an observed failure."""
        with self._source_breaker_lock:
            self._source_retry_after[source] = time.monotonic() + seconds
        logger.warning("source_circuit_open source=%s seconds=%s", source, seconds)

    def _call(
        self,
        function: Callable[..., Any],
        *,
        attempts: int | None = None,
        wait_timeout: float | None = None,
        **kwargs: Any,
    ) -> Any:
        """在并发上限内执行数据源请求，单次超时并指数退避。"""
        last_error: Exception | None = None
        retry_count = attempts if attempts is not None else self.settings.request_retries
        timeout = wait_timeout if wait_timeout is not None else self.settings.request_timeout
        for attempt in range(retry_count):
            try:
                with self._semaphore:
                    future = self._executor.submit(function, **kwargs)
                    return future.result(timeout=timeout)
            except TimeoutError as exc:
                last_error = exc
                future.cancel()
            except Exception as exc:  # AKShare 的上游异常类型不稳定，统一转换
                last_error = exc
            logger.warning(
                "provider_request_failed function=%s attempt=%s/%s reason=%s",
                getattr(function, "__name__", "unknown"),
                attempt + 1,
                retry_count,
                last_error,
            )
            if attempt + 1 < retry_count:
                time.sleep(0.5 * (2**attempt))
        name = getattr(function, "__name__", "unknown")
        raise ProviderError(
            "DATA_SOURCE_UNAVAILABLE",
            "AKShare 数据源暂时不可用，请稍后重试",
            {"function": name, "reason": str(last_error)},
        ) from last_error

    def _call_supported(
        self,
        function: Callable[..., Any],
        *,
        attempts: int | None = None,
        wait_timeout: float | None = None,
        **kwargs: Any,
    ) -> Any:
        parameters = inspect.signature(function).parameters
        supported = {key: value for key, value in kwargs.items() if key in parameters}
        if "timeout" in parameters and "timeout" not in supported:
            supported["timeout"] = self.settings.request_timeout
        return self._call(
            function,
            attempts=attempts,
            wait_timeout=wait_timeout,
            **supported,
        )

    def _etf_list(self) -> tuple[dict[str, str], str]:
        cache_key = "security-list:etf:fund_etf_spot_em"
        if self.cache and (entry := self.cache.get(cache_key)):
            return dict(entry.payload), "akshare_etf_list_cache"
        with self._etf_list_lock:
            if self.cache and (entry := self.cache.get(cache_key)):
                return dict(entry.payload), "akshare_etf_list_cache"
            function = getattr(self.ak, "fund_etf_spot_em", None)
            if function is None:
                raise ProviderError("ETF_LIST_UNSUPPORTED", "当前 AKShare 版本不提供 ETF 列表接口")
            try:
                raw = self._call(function, attempts=1)
                if raw is None or raw.empty:
                    raise ProviderError("EMPTY_ETF_LIST", "AKShare ETF 列表返回空数据")
            except ProviderError:
                stale_entry = self.cache.get(cache_key, allow_expired=True) if self.cache else None
                if stale_entry is not None:
                    logger.warning("etf_list_using_stale_cache")
                    return dict(stale_entry.payload), "akshare_etf_list_stale_cache"
                raise
            code_column = next(
                (c for c in ("代码", "基金代码", "symbol") if c in raw.columns),
                None,
            )
            name_column = next((c for c in ("名称", "基金简称", "name") if c in raw.columns), None)
            if code_column is None:
                raise ProviderError("SCHEMA_CHANGED", "ETF 列表字段发生变化", list(raw.columns))
            result = {
                str(row[code_column]).strip().zfill(6): (
                    str(row[name_column]).strip()
                    if name_column is not None
                    else str(row[code_column])
                )
                for _, row in raw.iterrows()
            }
            if self.cache:
                self.cache.set(
                    cache_key, result, self.settings.etf_list_cache_ttl, {"source": "AKShare"}
                )
            return result, "akshare_etf_list"

    def _stock_name(self, symbol: str) -> str:
        cache_key = f"security-name:stock:{symbol}"
        if self.cache and (entry := self.cache.get(cache_key)):
            return str(entry.payload)
        function = getattr(self.ak, "stock_individual_info_em", None)
        if function is None:
            return symbol
        try:
            raw = self._call_supported(function, attempts=1, symbol=symbol)
        except ProviderError:
            return symbol
        if raw is None or raw.empty:
            return symbol
        name = symbol
        if {"item", "value"}.issubset(raw.columns):
            values = dict(zip(raw["item"].astype(str), raw["value"], strict=False))
            name = str(values.get("股票简称") or values.get("名称") or symbol)
        elif {"项目", "值"}.issubset(raw.columns):
            values = dict(zip(raw["项目"].astype(str), raw["值"], strict=False))
            name = str(values.get("股票简称") or values.get("名称") or symbol)
        if self.cache and name != symbol:
            self.cache.set(cache_key, name, self.settings.etf_list_cache_ttl, {"source": "AKShare"})
        return name

    def _us_stock_list(self) -> tuple[dict[str, dict[str, str]], str]:
        """Return a cached ticker-to-provider-symbol mapping from AKShare's US table."""
        cache_key = "security-list:us-stock:stock_us_spot_em"
        source_key = "eastmoney_us_stock_list"
        if self.cache and (entry := self.cache.get(cache_key)):
            return dict(entry.payload), "akshare_us_stock_list_cache"
        if not self._source_available(source_key):
            stale = self.cache.get(cache_key, allow_expired=True) if self.cache else None
            if stale:
                return dict(stale.payload), "akshare_us_stock_list_stale_cache"
            raise ProviderError(
                "DATA_SOURCE_UNAVAILABLE", "东方财富美股代码表暂时不可用，已切换备用源"
            )
        with self._us_list_lock:
            if self.cache and (entry := self.cache.get(cache_key)):
                return dict(entry.payload), "akshare_us_stock_list_cache"
            function = getattr(self.ak, "stock_us_spot_em", None)
            if function is None:
                raise ProviderError(
                    "US_STOCK_LIST_UNSUPPORTED", "当前 AKShare 版本不提供美股代码表"
                )
            try:
                raw = self._call(function, attempts=1)
                if raw is None or raw.empty:
                    raise ProviderError("EMPTY_US_STOCK_LIST", "AKShare 美股代码表返回空数据")
            except ProviderError:
                stale = self.cache.get(cache_key, allow_expired=True) if self.cache else None
                if stale:
                    return dict(stale.payload), "akshare_us_stock_list_stale_cache"
                self._open_source_breaker(source_key, 300)
                raise
            code_column = next((c for c in ("代码", "code", "symbol") if c in raw), None)
            name_column = next((c for c in ("名称", "name") if c in raw), None)
            if code_column is None:
                raise ProviderError("SCHEMA_CHANGED", "美股代码表字段发生变化", list(raw.columns))
            result: dict[str, dict[str, str]] = {}
            for _, row in raw.iterrows():
                provider_symbol = str(row[code_column]).strip()
                ticker = provider_symbol.rsplit(".", 1)[-1].upper()
                if ticker:
                    result[ticker] = {
                        "provider_symbol": provider_symbol,
                        "name": str(row[name_column]).strip() if name_column else ticker,
                    }
            if self.cache:
                self.cache.set(
                    cache_key,
                    result,
                    self.settings.instrument_list_cache_ttl,
                    {"source": "AKShare / 东方财富"},
                )
            return result, "akshare_us_stock_list"

    def _future_list(self) -> tuple[dict[str, str], str]:
        cache_key = "security-list:global-future:futures_hq"
        if self.cache and (entry := self.cache.get(cache_key)):
            return dict(entry.payload), "akshare_future_list_cache"
        with self._future_list_lock:
            if self.cache and (entry := self.cache.get(cache_key)):
                return dict(entry.payload), "akshare_future_list_cache"
            function = getattr(self.ak, "futures_hq_subscribe_exchange_symbol", None)
            if function is None:
                raise ProviderError(
                    "FUTURE_LIST_UNSUPPORTED", "当前 AKShare 版本不提供外盘期货品种表"
                )
            raw = self._call(function, attempts=1)
            if raw is None or raw.empty or not {"symbol", "code"}.issubset(raw.columns):
                raise ProviderError("SCHEMA_CHANGED", "外盘期货品种表为空或字段发生变化")
            result = {
                str(row["code"]).upper(): str(row["symbol"])
                for _, row in raw.iterrows()
                if str(row["code"]).upper() in SUPPORTED_FUTURES
            }
            if self.cache:
                self.cache.set(
                    cache_key,
                    result,
                    self.settings.instrument_list_cache_ttl,
                    {"source": "AKShare / 新浪财经"},
                )
            return result, "akshare_future_list"

    def search_instruments(
        self, query: str, asset_type: AssetType, limit: int = 10
    ) -> list[dict[str, str]]:
        """Search supported international instruments by canonical code or name."""
        needle = query.strip().upper()
        if not needle:
            return []
        items: list[dict[str, str]] = []
        if asset_type == "us_stock":
            try:
                securities, _ = self._us_stock_list()
            except ProviderError as exc:
                if not _is_valid_us_ticker(needle):
                    return []
                logger.warning(
                    "us_stock_search_exact_fallback symbol=%s provider_code=%s",
                    needle,
                    exc.code,
                )
                return [
                    {
                        "symbol": needle,
                        "name": f"{needle}（代码表暂不可用）",
                        "asset_type": "us_stock",
                    }
                ]
            items = [
                {"symbol": ticker, "name": item["name"], "asset_type": "us_stock"}
                for ticker, item in securities.items()
                if needle in ticker or needle in item["name"].upper()
            ]
        elif asset_type == "us_index":
            items = [
                {"symbol": symbol, "name": name, "asset_type": "us_index"}
                for symbol, name in US_INDEX_NAMES.items()
                if needle in symbol or needle in name.upper()
            ]
        elif asset_type == "global_future":
            futures, _ = self._future_list()
            items = [
                {"symbol": symbol, "name": name, "asset_type": "global_future"}
                for symbol, name in futures.items()
                if needle in symbol or needle in name.upper()
            ]
        ordered = sorted(
            items,
            key=lambda item: (not item["symbol"].startswith(needle), item["symbol"]),
        )
        return ordered[: max(1, min(limit, 20))]

    @staticmethod
    def market_status(now: datetime | None = None) -> str:
        local_now = now.astimezone(SHANGHAI_TZ) if now else datetime.now(SHANGHAI_TZ)
        if local_now.weekday() >= 5:
            return "休市"
        current = local_now.time().replace(tzinfo=None)
        if clock_time(9, 30) <= current <= clock_time(11, 30) or clock_time(
            13, 0
        ) <= current <= clock_time(15, 0):
            return "交易中"
        if current < clock_time(9, 30):
            return "未开市"
        return "已收盘"

    @staticmethod
    def us_market_status(now: datetime | None = None) -> str:
        local_now = (now or datetime.now(UTC)).astimezone(ZoneInfo("America/New_York"))
        if local_now.weekday() >= 5:
            return "休市"
        current = local_now.time().replace(tzinfo=None)
        if clock_time(9, 30) <= current <= clock_time(16, 0):
            return "交易中"
        if current < clock_time(9, 30):
            return "未开市"
        return "已收盘"

    def identify(self, symbol: str, asset_type: AssetType = "auto") -> SecurityInfo:
        symbol = symbol.strip().upper()
        now = datetime.now(SHANGHAI_TZ)
        if asset_type == "us_stock":
            try:
                securities, method = self._us_stock_list()
            except ProviderError as exc:
                if not _is_valid_us_ticker(symbol):
                    raise
                logger.warning(
                    "us_stock_identify_sina_fallback symbol=%s provider_code=%s",
                    symbol,
                    exc.code,
                )
                return SecurityInfo(
                    symbol=symbol,
                    canonical_symbol=symbol,
                    provider_symbol=symbol,
                    name=symbol,
                    asset_type="us_stock",
                    detection_method="sina_ticker_fallback",
                    data_source="AKShare / 新浪财经美股（代码表故障降级）",
                    source="新浪财经",
                    updated_at=now,
                    market_status=self.us_market_status(),
                    exchange="美国市场",
                    currency="USD",
                    timezone="America/New_York",
                    capabilities={
                        "periods": ["daily", "weekly", "monthly"],
                        "adjustments": ["none", "qfq"],
                        "minute_adjustment": False,
                    },
                )
            match = securities.get(symbol)
            if match is None:
                raise ProviderError("INVALID_SYMBOL", f"美股代码表中未找到 {symbol}")
            return SecurityInfo(
                symbol=symbol,
                canonical_symbol=symbol,
                provider_symbol=match["provider_symbol"],
                name=match["name"],
                asset_type="us_stock",
                detection_method=method,
                data_source="AKShare / 东方财富美股",
                source="东方财富",
                updated_at=now,
                market_status=self.us_market_status(),
                exchange="美国市场",
                currency="USD",
                timezone="America/New_York",
                capabilities={
                    "periods": ["daily", "weekly", "monthly", "1m"],
                    "adjustments": ["none", "qfq", "hfq"],
                    "minute_adjustment": False,
                },
            )
        if asset_type == "us_index":
            if symbol not in US_INDEX_NAMES:
                raise ProviderError("INVALID_SYMBOL", "不支持的美国指数代码")
            return SecurityInfo(
                symbol=symbol,
                canonical_symbol=symbol,
                provider_symbol=symbol,
                name=US_INDEX_NAMES[symbol],
                asset_type="us_index",
                detection_method="supported_us_index_table",
                data_source="AKShare / 新浪财经美国指数",
                source="新浪财经",
                updated_at=now,
                market_status=self.us_market_status(),
                exchange="美国指数",
                currency="USD",
                timezone="America/New_York",
                capabilities={"periods": ["daily", "weekly", "monthly"], "adjustments": []},
                subtype="index",
            )
        if asset_type == "global_future":
            if symbol not in SUPPORTED_FUTURES:
                raise ProviderError(
                    "INVALID_SYMBOL", "暂仅支持 GC、SI、HG、CL、NG、OIL、XAU、XAG"
                )
            futures, method = self._future_list()
            if symbol not in futures:
                raise ProviderError("INVALID_SYMBOL", f"AKShare 品种表中未找到 {symbol}")
            return SecurityInfo(
                symbol=symbol,
                canonical_symbol=symbol,
                provider_symbol=symbol,
                name=futures[symbol],
                asset_type="global_future",
                detection_method=method,
                data_source="AKShare / 新浪财经外盘期货",
                source="新浪财经",
                updated_at=now,
                market_status="以数据源快照为准",
                exchange="境外期货市场",
                currency="USD",
                timezone="America/New_York",
                capabilities={
                    "periods": ["daily", "weekly", "monthly"],
                    "adjustments": [],
                    "snapshot": True,
                },
                subtype="commodity_future",
                series_type="连续参考序列（非具体合约）",
            )
        explicit_etf = asset_type in {"etf", "cn_etf"}
        explicit_stock = asset_type in {"stock", "cn_stock"}
        if explicit_etf:
            try:
                etf_list, method = self._etf_list()
                name = etf_list.get(symbol, symbol)
            except ProviderError:
                name, method = symbol, "explicit_etf"
            resolved = "cn_etf" if asset_type == "cn_etf" else "etf"
        elif explicit_stock:
            resolved = "cn_stock" if asset_type == "cn_stock" else "stock"
            name, method = self._stock_name(symbol), f"explicit_{resolved}"
        else:
            try:
                etf_list, method = self._etf_list()
                if symbol in etf_list:
                    resolved, name = "etf", etf_list[symbol]
                else:
                    resolved, name, method = (
                        "stock",
                        self._stock_name(symbol),
                        "akshare_etf_list_miss",
                    )
            except ProviderError:
                resolved = "etf" if symbol.startswith(ETF_FALLBACK_PREFIXES) else "stock"
                name = symbol if resolved == "etf" else self._stock_name(symbol)
                method = (
                    "fallback_prefix_rule_etf"
                    if resolved == "etf"
                    else "fallback_prefix_rule_stock"
                )
        return SecurityInfo(
            symbol=symbol,
            name=name,
            asset_type=resolved,
            detection_method=method,
            data_source="AKShare / 东方财富",
            updated_at=now,
            market_status=self.market_status(now),
            canonical_symbol=symbol,
            provider_symbol=symbol,
            exchange="中国内地证券市场",
            currency="CNY",
            timezone="Asia/Shanghai",
            source="东方财富",
            capabilities={
                "periods": list(MINUTE_PERIODS) + ["daily", "weekly", "monthly"],
                "adjustments": ["none", "qfq", "hfq"],
            },
        )

    def _cache_key(
        self,
        security: SecurityInfo,
        period: Period,
        adjust: Adjust,
        start: date,
        end: date,
    ) -> str:
        return self._cache_key_for_symbol(
            security.asset_type, security.symbol, period, adjust, start, end
        )

    @staticmethod
    def _cache_key_for_symbol(
        asset_type: str,
        symbol: str,
        period: Period,
        adjust: Adjust,
        start: date,
        end: date,
    ) -> str:
        raw = ":".join(
            [
                asset_type,
                symbol,
                period,
                adjust,
                start.isoformat(),
                end.isoformat(),
            ]
        )
        return f"market:{sha256(raw.encode()).hexdigest()}"

    @staticmethod
    def _history_series_key(
        asset_type: str, symbol: str, period: Period, adjust: Adjust
    ) -> str:
        raw = ":".join((asset_type, symbol, period, adjust))
        return f"history-series:{sha256(raw.encode()).hexdigest()}"

    def _fetch_sina_minute_raw(self, symbol: str, period: str) -> pd.DataFrame:
        """Fetch Sina minute bars directly, avoiding AKShare's extra daily-data request."""
        url = "https://quotes.sina.cn/cn/api/jsonp_v2.php/=/CN_MarketDataService.getKLineData"
        params = {
            "symbol": _stock_exchange_symbol(symbol),
            "scale": period,
            "ma": "no",
            "datalen": "1970",
        }
        retry_count = min(self.settings.request_retries, 2)
        last_error: Exception | None = None
        for attempt in range(retry_count):
            try:
                with self._semaphore:
                    response = requests.get(
                        url,
                        params=params,
                        timeout=self.settings.request_timeout,
                    )
                    response.raise_for_status()
                payload_start = response.text.find("[")
                payload_end = response.text.rfind("]")
                if payload_start < 0 or payload_end <= payload_start:
                    raise ValueError("新浪分钟行情返回内容不是有效 JSONP")
                payload = json.loads(response.text[payload_start : payload_end + 1])
                return pd.DataFrame(payload)
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                if attempt + 1 < retry_count:
                    time.sleep(0.5 * (2**attempt))
        raise ProviderError(
            "MINUTE_FALLBACK_UNAVAILABLE",
            "新浪分钟备用数据源暂时不可用，请稍后重试",
            {"reason": str(last_error)},
        ) from last_error

    def _minute_adjustment_factors(
        self,
        symbol: str,
        adjust: Adjust,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Calculate minute OHLC factors from adjusted and raw Tencent daily closes."""
        function = getattr(self.ak, "stock_zh_a_hist_tx", None)
        if function is None:
            raise ProviderError(
                "MINUTE_ADJUST_UNSUPPORTED",
                "分钟备用数据可用，但当前 AKShare 版本无法计算所选复权方式",
            )
        common = {
            "symbol": _stock_exchange_symbol(symbol),
            "start_date": start.strftime("%Y%m%d"),
            "end_date": end.strftime("%Y%m%d"),
        }
        raw_daily = self._call_supported(function, attempts=2, adjust="", **common)
        adjusted_daily = self._call_supported(function, attempts=2, adjust=adjust, **common)
        raw_frame = normalize_market_frame(raw_daily)
        adjusted_frame = normalize_market_frame(adjusted_daily)
        if raw_frame.empty or adjusted_frame.empty:
            raise ProviderError(
                "MINUTE_ADJUSTMENT_UNAVAILABLE",
                "分钟备用行情缺少可用的日线复权因子",
            )

        raw_close = raw_frame[["datetime", "close"]].rename(columns={"close": "raw_close"})
        adjusted_close = adjusted_frame[["datetime", "close"]].rename(
            columns={"close": "adjusted_close"}
        )
        factors = adjusted_close.merge(raw_close, on="datetime", how="inner")
        factors["factor"] = factors["adjusted_close"] / factors["raw_close"].replace(0, pd.NA)
        factors = factors.replace([math.inf, -math.inf], pd.NA).dropna(subset=["factor"])
        factors = factors.rename(columns={"datetime": "trade_date"})[["trade_date", "factor"]]
        factors["trade_date"] = factors["trade_date"].astype("datetime64[ns]")
        if factors.empty:
            raise ProviderError(
                "MINUTE_ADJUSTMENT_UNAVAILABLE",
                "分钟备用行情无法计算有效的日线复权因子",
            )
        return factors.sort_values("trade_date").reset_index(drop=True)

    def _normalize_sina_minute(
        self,
        raw: pd.DataFrame,
        security: SecurityInfo,
        adjust: Adjust,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Normalize Sina bars, trim dates, convert shares to lots and apply OHLC factors."""
        source = raw.copy()
        if "volume" in source:
            source["volume"] = pd.to_numeric(source["volume"], errors="coerce") / 100
        normalized = normalize_market_frame(source)
        if normalized.empty:
            return normalized

        start_at = pd.Timestamp(start)
        end_at = pd.Timestamp(end) + pd.Timedelta(days=1)
        normalized = normalized.loc[
            (normalized["datetime"] >= start_at) & (normalized["datetime"] < end_at)
        ].copy()
        if normalized.empty:
            return normalized

        if adjust != "none":
            factors = self._minute_adjustment_factors(
                security.symbol,
                adjust,
                normalized["datetime"].min().date(),
                normalized["datetime"].max().date(),
            )
            normalized["trade_date"] = normalized["datetime"].dt.normalize().astype(
                "datetime64[ns]"
            )
            normalized = pd.merge_asof(
                normalized.sort_values("trade_date"),
                factors,
                on="trade_date",
                direction="backward",
            )
            if normalized["factor"].isna().any():
                raise ProviderError(
                    "MINUTE_ADJUSTMENT_UNAVAILABLE",
                    "部分分钟行情缺少对应的复权因子",
                )
            for column in ("open", "high", "low", "close"):
                normalized[column] = normalized[column] * normalized["factor"]
            normalized = normalized.drop(columns=["trade_date", "factor"])

        previous_close = normalized["close"].shift(1)
        normalized["change"] = normalized["close"].diff()
        normalized["pct_change"] = normalized["close"].pct_change() * 100
        normalized["amplitude"] = (
            (normalized["high"] - normalized["low"])
            / previous_close.replace(0, pd.NA)
            * 100
        )
        return normalized.sort_values("datetime").reset_index(drop=True)[CANONICAL_COLUMNS]

    def _fetch_minute_history(
        self,
        security: SecurityInfo,
        period: Period,
        adjust: Adjust,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        function_name = (
            "fund_etf_hist_min_em"
            if security.asset_type in {"etf", "cn_etf"}
            else "stock_zh_a_hist_min_em"
        )
        function = getattr(self.ak, function_name, None)
        if function is None:
            raise ProviderError(
                "MINUTE_DATA_UNSUPPORTED",
                f"当前 AKShare 版本不提供 {security.asset_type.upper()} 分钟行情接口 "
                f"{function_name}",
            )

        primary_error: ProviderError | None = None
        with self._minute_breaker_lock:
            try_primary = time.monotonic() >= self._minute_primary_retry_after
        if try_primary:
            try:
                raw = self._call_supported(
                    function,
                    attempts=1,
                    symbol=security.symbol,
                    start_date=f"{start.isoformat()} 00:00:00",
                    end_date=f"{end.isoformat()} 23:59:59",
                    period=MINUTE_PERIODS[period],
                    adjust="" if adjust == "none" else adjust,
                )
            except ProviderError as exc:
                primary_error = exc
                raw = pd.DataFrame()
            if raw is not None and not raw.empty:
                normalized = normalize_market_frame(raw)
                if not normalized.empty:
                    return normalized
            with self._minute_breaker_lock:
                self._minute_primary_retry_after = (
                    time.monotonic() + MINUTE_PRIMARY_BREAKER_SECONDS
                )

        try:
            fallback_raw = self._fetch_sina_minute_raw(
                security.symbol,
                MINUTE_PERIODS[period],
            )
            normalized = self._normalize_sina_minute(
                fallback_raw,
                security,
                adjust,
                start,
                end,
            )
        except ProviderError as fallback_error:
            raise ProviderError(
                "DATA_SOURCE_UNAVAILABLE",
                "分钟行情主数据源与备用数据源均暂时不可用，请稍后重试",
                {
                    "primary": primary_error.detail if primary_error else "主接口处于短时熔断",
                    "fallback": fallback_error.detail,
                },
            ) from fallback_error
        if normalized.empty:
            raise ProviderError(
                "EMPTY_DATA",
                "分钟备用数据源未返回所选日期区间内的行情；分钟历史通常仅覆盖近期",
            )
        security.data_source = "新浪分钟行情（东方财富失败后降级）"
        if adjust != "none":
            security.data_source += " / 腾讯日线复权因子"
        return normalized

    def _fetch_tencent_history(
        self,
        security: SecurityInfo,
        period: Period,
        adjust_value: str,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Fetch stock or ETF daily bars from Tencent and normalize its units."""
        source_key = "tencent_history"
        if not self._source_available(source_key):
            raise ProviderError(
                "DATA_SOURCE_UNAVAILABLE",
                "腾讯备用数据源正在短时冷却，请稍后重试",
            )
        function = getattr(self.ak, "stock_zh_a_hist_tx", None)
        if function is None:
            raise ProviderError(
                "HISTORY_FALLBACK_UNSUPPORTED",
                "当前 AKShare 版本不提供腾讯历史行情接口",
            )
        try:
            raw = self._call_supported(
                function,
                attempts=2,
                symbol=_stock_exchange_symbol(security.symbol),
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
                adjust=adjust_value,
            )
        except ProviderError:
            self._open_source_breaker(source_key, seconds=60)
            raise
        normalized = normalize_tx_stock_frame(raw, period)
        if normalized.empty:
            raise ProviderError(
                "EMPTY_DATA",
                "腾讯备用数据源未返回该证券在所选区间内的行情",
            )
        security.data_source = "AKShare / 腾讯（东方财富失败后降级）"
        logger.info(
            "history_fallback_to_tencent symbol=%s asset_type=%s period=%s",
            security.symbol,
            security.asset_type,
            period,
        )
        return normalized

    @staticmethod
    def _resample_history(frame: pd.DataFrame, period: Period) -> pd.DataFrame:
        if period == "daily":
            return frame
        frequency = "W-FRI" if period == "weekly" else "ME"
        indexed = frame.set_index("datetime")
        result = indexed.resample(frequency).agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
                "amount": "sum",
                "open_interest": "last",
                "settlement": "last",
            }
        )
        result = result.dropna(subset=["open", "high", "low", "close"]).reset_index()
        return normalize_market_frame(result)

    @staticmethod
    def _finalize_frame(
        frame: pd.DataFrame,
        *,
        currency: str,
        source: str,
        captured_at: datetime,
    ) -> pd.DataFrame:
        result = frame.copy()
        previous_close = result["close"].shift(1)
        result["change"] = result["change"].fillna(result["close"].diff())
        result["pct_change"] = result["pct_change"].fillna(result["close"].pct_change() * 100)
        result["amplitude"] = result["amplitude"].fillna(
            (result["high"] - result["low"]) / previous_close.replace(0, pd.NA) * 100
        )
        result["currency"] = currency
        result["source"] = source
        result["captured_at"] = pd.Timestamp(captured_at).tz_localize(None)
        return result[CANONICAL_COLUMNS]

    def _fetch_us_stock_history(
        self,
        security: SecurityInfo,
        period: Period,
        adjust: Adjust,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        if security.detection_method == "sina_ticker_fallback":
            return self._fetch_us_stock_sina_history(security, period, adjust, start, end)
        if period == "1m":
            function = getattr(self.ak, "stock_us_hist_min_em", None)
            if function is None:
                raise ProviderError(
                    "MINUTE_DATA_UNSUPPORTED", "当前 AKShare 版本不提供美股1分钟行情"
                )
            raw = self._call_supported(
                function,
                symbol=security.provider_symbol,
                start_date=f"{start.isoformat()} 00:00:00",
                end_date=f"{end.isoformat()} 23:59:59",
            )
        else:
            function = getattr(self.ak, "stock_us_hist", None)
            if function is None:
                raise ProviderError(
                    "US_STOCK_DATA_UNSUPPORTED", "当前 AKShare 版本不提供美股历史行情"
                )
            try:
                raw = self._call_supported(
                    function,
                    symbol=security.provider_symbol,
                    period=period,
                    start_date=start.strftime("%Y%m%d"),
                    end_date=end.strftime("%Y%m%d"),
                    adjust="" if adjust == "none" else adjust,
                )
            except ProviderError:
                if adjust == "hfq":
                    raise
                logger.warning(
                    "us_stock_history_fallback_to_sina symbol=%s period=%s",
                    security.symbol,
                    period,
                )
                return self._fetch_us_stock_sina_history(
                    security, period, adjust, start, end
                )
        normalized = normalize_market_frame(raw)
        if normalized.empty:
            raise ProviderError("EMPTY_DATA", "美股数据源未返回所选区间内的行情")
        return self._finalize_frame(
            normalized,
            currency="USD",
            source="东方财富美股",
            captured_at=datetime.now(SHANGHAI_TZ),
        )

    def _fetch_us_stock_sina_history(
        self,
        security: SecurityInfo,
        period: Period,
        adjust: Adjust,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Fetch US daily bars from Sina without guessing an Eastmoney market prefix."""
        if period == "1m":
            raise ProviderError(
                "MINUTE_DATA_UNSUPPORTED",
                "美股代码表不可用时，新浪备用源不提供1分钟行情",
            )
        if adjust == "hfq":
            raise ProviderError(
                "ADJUST_UNSUPPORTED",
                "美股代码表不可用时，新浪备用源不支持后复权",
            )
        function = getattr(self.ak, "stock_us_daily", None)
        if function is None:
            raise ProviderError(
                "US_STOCK_DATA_UNSUPPORTED", "当前 AKShare 版本不提供新浪美股备用行情"
            )
        raw = self._call_supported(
            function,
            symbol=security.symbol,
            adjust="" if adjust == "none" else adjust,
        )
        normalized = normalize_market_frame(raw)
        normalized = normalized.loc[
            normalized["datetime"].dt.date.between(start, end)
        ].reset_index(drop=True)
        normalized = self._resample_history(normalized, period)
        if normalized.empty:
            raise ProviderError("EMPTY_DATA", "新浪美股备用源未返回所选区间内的行情")
        security.provider_symbol = security.symbol
        security.data_source = "AKShare / 新浪财经美股（东方财富故障降级）"
        security.source = "新浪财经"
        if security.detection_method != "sina_ticker_fallback":
            security.detection_method = "eastmoney_code_table_sina_history_fallback"
        return self._finalize_frame(
            normalized,
            currency="USD",
            source="新浪财经美股",
            captured_at=datetime.now(SHANGHAI_TZ),
        )

    def _fetch_us_index_history(
        self,
        security: SecurityInfo,
        period: Period,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        function = getattr(self.ak, "index_us_stock_sina", None)
        if function is None:
            raise ProviderError(
                "US_INDEX_DATA_UNSUPPORTED", "当前 AKShare 版本不提供美国指数历史行情"
            )
        raw = self._call_supported(function, symbol=security.provider_symbol)
        normalized = normalize_market_frame(raw)
        normalized = normalized.loc[
            normalized["datetime"].dt.date.between(start, end)
        ].reset_index(drop=True)
        if normalized.empty:
            raise ProviderError("EMPTY_DATA", "美国指数数据源未返回所选区间内的行情")
        normalized = self._resample_history(normalized, period)
        return self._finalize_frame(
            normalized,
            currency="USD",
            source="新浪财经美国指数",
            captured_at=datetime.now(SHANGHAI_TZ),
        )

    def _fetch_future_snapshot(self, symbol: str) -> dict[str, Any] | None:
        cache_key = f"snapshot:global-future:{symbol}"
        if self.cache and (entry := self.cache.get(cache_key)):
            return dict(entry.payload)
        function = getattr(self.ak, "futures_foreign_commodity_realtime", None)
        if function is None:
            return None
        try:
            raw = self._call_supported(function, attempts=1, symbol=symbol)
        except ProviderError as exc:
            logger.warning("future_snapshot_failed symbol=%s detail=%s", symbol, exc.detail)
            return None
        if raw is None or raw.empty:
            return None
        row = raw.iloc[0]

        def value(*names: str) -> Any:
            for name in names:
                if name in row.index and pd.notna(row[name]):
                    item = row[name]
                    return item.item() if hasattr(item, "item") else item
            return None

        captured_at = datetime.now(SHANGHAI_TZ)
        source_date = value("日期", "date")
        source_time = value("行情时间", "time")
        snapshot = {
            "latest": value("最新价", "current_price"),
            "pct_change": value("涨跌幅", "pct_change"),
            "change": value("涨跌额", "change"),
            "open": value("开盘价", "open"),
            "high": value("最高价", "high"),
            "low": value("最低价", "low"),
            "settlement": value("昨结算", "last_settle_price"),
            "open_interest": value("持仓量", "hold"),
            "source_timestamp": " ".join(
                str(part) for part in (source_date, source_time) if part is not None
            )
            or None,
            "captured_at": captured_at.isoformat(),
            "source": "新浪财经外盘期货",
        }
        if self.cache:
            self.cache.set(
                cache_key,
                snapshot,
                self.settings.snapshot_cache_ttl,
                {"source": "AKShare / 新浪财经"},
            )
        return snapshot

    def _fetch_future_history(
        self,
        security: SecurityInfo,
        period: Period,
        start: date,
        end: date,
    ) -> tuple[pd.DataFrame, dict[str, Any] | None]:
        function = getattr(self.ak, "futures_foreign_hist", None)
        if function is None:
            raise ProviderError(
                "FUTURE_DATA_UNSUPPORTED", "当前 AKShare 版本不提供外盘期货历史行情"
            )
        raw = self._call_supported(function, symbol=security.provider_symbol)
        normalized = normalize_market_frame(raw)
        normalized = normalized.loc[
            normalized["datetime"].dt.date.between(start, end)
        ].reset_index(drop=True)
        normalized = self._resample_history(normalized, period)
        if normalized.empty:
            raise ProviderError("EMPTY_DATA", "外盘期货数据源未返回所选区间内的行情")
        captured_at = datetime.now(SHANGHAI_TZ)
        normalized = self._finalize_frame(
            normalized,
            currency="USD",
            source="新浪财经外盘期货",
            captured_at=captured_at,
        )
        return normalized, self._fetch_future_snapshot(security.symbol)

    def _fetch_history(
        self,
        security: SecurityInfo,
        period: Period,
        adjust: Adjust,
        start: date,
        end: date,
    ) -> tuple[pd.DataFrame, dict[str, Any] | None]:
        adjust_value = "" if adjust == "none" else adjust
        if security.asset_type == "us_stock":
            return self._fetch_us_stock_history(security, period, adjust, start, end), None
        if security.asset_type == "us_index":
            return self._fetch_us_index_history(security, period, start, end), None
        if security.asset_type == "global_future":
            return self._fetch_future_history(security, period, start, end)
        if period in MINUTE_PERIODS:
            return self._fetch_minute_history(security, period, adjust, start, end), None

        is_etf = security.asset_type in {"etf", "cn_etf"}
        function_name = "fund_etf_hist_em" if is_etf else "stock_zh_a_hist"
        source_key = f"eastmoney_{security.asset_type}_history"
        asset_label = "ETF" if is_etf else "个股"
        function = getattr(self.ak, function_name, None)
        if function is None:
            code = "ETF_DATA_UNSUPPORTED" if is_etf else "STOCK_DATA_UNSUPPORTED"
            raise ProviderError(code, f"当前 AKShare 版本不提供{asset_label}历史行情接口")

        primary_error: ProviderError | None = None
        raw = pd.DataFrame()
        if self._source_available(source_key):
            try:
                raw = self._call_supported(
                    function,
                    attempts=1,
                    symbol=security.symbol,
                    period=period,
                    start_date=start.strftime("%Y%m%d"),
                    end_date=end.strftime("%Y%m%d"),
                    adjust=adjust_value,
                )
            except ProviderError as exc:
                primary_error = exc
        else:
            logger.info("source_circuit_skip source=%s", source_key)

        if raw is None or raw.empty:
            self._open_source_breaker(source_key)
            try:
                return self._fetch_tencent_history(
                    security, period, adjust_value, start, end
                ), None
            except ProviderError as fallback_error:
                if primary_error is None and fallback_error.code in {
                    "EMPTY_DATA",
                    "HISTORY_FALLBACK_UNSUPPORTED",
                }:
                    raise ProviderError(
                        "EMPTY_DATA",
                        "数据源未返回该证券在所选区间内的行情",
                    ) from fallback_error
                raise ProviderError(
                    "DATA_SOURCE_UNAVAILABLE",
                    f"{asset_label}主数据源与备用数据源均暂时不可用，请稍后重试",
                    {
                        "primary": primary_error.detail
                        if primary_error
                        else "东方财富接口处于短时熔断",
                        "fallback": fallback_error.detail,
                    },
                ) from fallback_error

        normalized = normalize_market_frame(raw)
        if normalized.empty:
            raise ProviderError(
                "INVALID_DATA",
                "行情字段无法规范化或全部 K 线不满足 OHLC 关系",
                {"columns": list(raw.columns)},
            )
        return normalized, None

    def _market_data_from_cache(
        self,
        entry: CacheEntry,
        security: SecurityInfo,
        period: Period,
        adjust: Adjust,
        stale_note: str | None = None,
    ) -> MarketData:
        """Build a market result from a valid or explicitly marked stale cache entry."""
        metadata = entry.metadata
        quality_notes = list(metadata.get("quality_notes", []))
        if stale_note:
            quality_notes.append(stale_note)
        cached_security = SecurityInfo(
            symbol=security.symbol,
            name=metadata.get("name", security.name),
            asset_type=security.asset_type,
            detection_method=metadata.get("detection_method", security.detection_method),
            data_source=metadata.get("data_source", security.data_source),
            updated_at=entry.created_at.astimezone(SHANGHAI_TZ),
            market_status=security.market_status,
            canonical_symbol=metadata.get("canonical_symbol", security.canonical_symbol),
            provider_symbol=metadata.get("provider_symbol", security.provider_symbol),
            exchange=metadata.get("exchange", security.exchange),
            currency=metadata.get("currency", security.currency),
            timezone=metadata.get("timezone", security.timezone),
            source=metadata.get("source", security.source),
            capabilities=metadata.get("capabilities", security.capabilities),
            subtype=metadata.get("subtype", security.subtype),
            series_type=metadata.get("series_type", security.series_type),
        )
        return MarketData(
            frame=_frame_from_records(entry.payload),
            security=cached_security,
            period=period,
            adjust=adjust,
            fetched_at=entry.created_at.astimezone(SHANGHAI_TZ),
            from_cache=True,
            volume_unit=metadata.get("volume_unit", "手"),
            amount_unit=metadata.get("amount_unit", "元"),
            quality_notes=quality_notes,
            snapshot=metadata.get("snapshot"),
            cache_status=metadata.get("cache_status"),
        )

    def _history_from_incremental_cache(
        self,
        security: SecurityInfo,
        period: Period,
        adjust: Adjust,
        start: date,
        end: date,
    ) -> MarketData | None:
        """按缺失区间更新持久序列；分钟行情不进入此缓存。"""
        if not self.cache or period in MINUTE_PERIODS:
            return None
        series_key = self._history_series_key(
            security.asset_type, security.symbol, period, adjust
        )
        entry = self.cache.get_history_series(series_key)
        if entry is None:
            return None
        stored = _frame_from_records(entry.payload)
        metadata = entry.metadata
        if stored.empty:
            return None
        coverage_start = date.fromisoformat(metadata["coverage_start"])
        coverage_end = date.fromisoformat(metadata["coverage_end"])
        missing_ranges: list[tuple[date, date]] = []
        if start < coverage_start:
            missing_ranges.append((start, coverage_start - timedelta(days=1)))
        if end > coverage_end:
            missing_ranges.append((coverage_end + timedelta(days=1), end))
        age_seconds = (datetime.now(UTC) - entry.updated_at).total_seconds()
        if not missing_ranges and age_seconds > self.settings.daily_cache_ttl:
            last_bar = pd.Timestamp(stored["datetime"].iloc[-1]).date()
            missing_ranges.append((max(start, last_bar - timedelta(days=7)), end))

        fetched_frames: list[pd.DataFrame] = []
        snapshot = metadata.get("snapshot")
        try:
            for missing_start, missing_end in missing_ranges:
                if missing_start > missing_end:
                    continue
                try:
                    fetched, fetched_snapshot = self._fetch_history(
                        security, period, adjust, missing_start, missing_end
                    )
                except ProviderError as exc:
                    if exc.code == "EMPTY_DATA":
                        continue
                    raise
                fetched_frames.append(fetched)
                snapshot = fetched_snapshot or snapshot
        except ProviderError:
            requested = stored.loc[
                stored["datetime"].dt.date.between(start, end)
            ].reset_index(drop=True)
            if requested.empty:
                raise
            cached = MarketData(
                frame=requested,
                security=security,
                period=period,
                adjust=adjust,
                fetched_at=entry.updated_at.astimezone(SHANGHAI_TZ),
                from_cache=True,
                volume_unit=metadata.get("volume_unit", "手"),
                amount_unit=metadata.get("amount_unit", "元"),
                quality_notes=list(metadata.get("quality_notes", []))
                + ["增量更新失败，当前展示数据库已有历史区间。"],
                snapshot=snapshot,
                cache_status={
                    "mode": "stale_series",
                    "existing_rows": len(requested),
                    "new_rows": 0,
                },
            )
            return cached

        if fetched_frames:
            old_datetimes = set(stored["datetime"])
            merged = normalize_market_frame(pd.concat([stored, *fetched_frames], ignore_index=True))
            new_rows = int((~merged["datetime"].isin(old_datetimes)).sum())
            coverage_start = min(start, coverage_start)
            coverage_end = max(end, coverage_end)
            metadata.update(
                {
                    "coverage_start": coverage_start.isoformat(),
                    "coverage_end": coverage_end.isoformat(),
                    "snapshot": snapshot,
                    "data_source": security.data_source,
                    "provider_symbol": security.provider_symbol,
                }
            )
            self.cache.set_history_series(series_key, _records_from_frame(merged), metadata)
            stored = merged
            mode = "incremental_update"
        else:
            new_rows = 0
            mode = "series_cache"
        requested = stored.loc[stored["datetime"].dt.date.between(start, end)].reset_index(
            drop=True
        )
        if requested.empty:
            return None
        if security.asset_type == "global_future" and not fetched_frames:
            snapshot = self._fetch_future_snapshot(security.symbol) or snapshot
        notes = list(metadata.get("quality_notes", []))
        if fetched_frames:
            notes.append(f"已检查数据库并仅拉取缺失区间，本次新增{new_rows}根K线。")
        else:
            notes.append("查询区间已由数据库历史序列完整覆盖，未请求线上历史行情。")
        return MarketData(
            frame=requested,
            security=security,
            period=period,
            adjust=adjust,
            fetched_at=datetime.now(SHANGHAI_TZ) if fetched_frames else entry.updated_at.astimezone(
                SHANGHAI_TZ
            ),
            from_cache=not fetched_frames,
            volume_unit=metadata.get("volume_unit", "手"),
            amount_unit=metadata.get("amount_unit", "元"),
            quality_notes=notes,
            snapshot=snapshot,
            cache_status={
                "mode": mode,
                "coverage_start": coverage_start.isoformat(),
                "coverage_end": coverage_end.isoformat(),
                "existing_rows": len(stored) - new_rows,
                "new_rows": new_rows,
            },
        )

    def get_history(
        self,
        symbol: str,
        asset_type: AssetType,
        period: Period,
        adjust: Adjust,
        start: date,
        end: date,
        force_refresh: bool = False,
    ) -> MarketData:
        normalized_symbol = symbol.strip().upper()
        direct_cache_types = {
            "cn_stock",
            "cn_etf",
            "us_stock",
            "us_index",
            "global_future",
        }
        if self.cache and not force_refresh and asset_type in direct_cache_types:
            direct_key = self._cache_key_for_symbol(
                asset_type, normalized_symbol, period, adjust, start, end
            )
            if entry := self.cache.get(direct_key):
                metadata = entry.metadata
                cached_security = SecurityInfo(
                    symbol=normalized_symbol,
                    name=str(metadata.get("name", normalized_symbol)),
                    asset_type=metadata.get("asset_type", asset_type),
                    detection_method=str(metadata.get("detection_method", "history_cache")),
                    data_source=str(metadata.get("data_source", "SQLite 历史缓存")),
                    updated_at=entry.created_at.astimezone(SHANGHAI_TZ),
                )
                result = self._market_data_from_cache(
                    entry, cached_security, period, adjust
                )
                if result.security.asset_type == "global_future":
                    result.snapshot = (
                        self._fetch_future_snapshot(result.security.symbol) or result.snapshot
                    )
                return result

        security = self.identify(normalized_symbol, asset_type)
        cache_key = self._cache_key(security, period, adjust, start, end)
        if self.cache and not force_refresh and (entry := self.cache.get(cache_key)):
            result = self._market_data_from_cache(entry, security, period, adjust)
            if security.asset_type == "global_future":
                result.snapshot = self._fetch_future_snapshot(security.symbol) or result.snapshot
            return result

        if not force_refresh and (
            incremental := self._history_from_incremental_cache(
                security, period, adjust, start, end
            )
        ):
            return incremental

        try:
            frame, snapshot = self._fetch_history(security, period, adjust, start, end)
        except ProviderError as exc:
            stale_entry = (
                self.cache.get(cache_key, allow_expired=True)
                if self.cache and not force_refresh
                else None
            )
            max_stale_age = (
                min(self.settings.stale_cache_max_age, 300)
                if period in MINUTE_PERIODS
                else self.settings.stale_cache_max_age
            )
            is_recent_stale = stale_entry and (
                datetime.now(UTC) - stale_entry.created_at
            ).total_seconds() <= max_stale_age
            if is_recent_stale:
                logger.warning(
                    "history_using_stale_cache symbol=%s period=%s provider_code=%s",
                    symbol,
                    period,
                    exc.code,
                )
                return self._market_data_from_cache(
                    stale_entry,
                    security,
                    period,
                    adjust,
                    "上游数据源暂时不可用，当前展示的是已过期缓存；请稍后刷新确认。",
                )
            raise
        fetched_at = datetime.now(SHANGHAI_TZ)
        security.updated_at = fetched_at
        quality_notes: list[str] = []
        volume_unit = "股" if security.asset_type == "us_stock" else "手"
        amount_unit = security.currency
        if security.asset_type == "us_index":
            volume_unit = "数据源口径"
            amount_unit = "不可用"
            quality_notes.append("指数没有换手率和复权语义；周线/月线由日线聚合。")
        elif security.asset_type == "global_future":
            volume_unit = "数据源口径"
            amount_unit = "不可用"
            quality_notes.extend(
                [
                    "该行情是品种连续参考序列，不代表某个具体到期合约。",
                    "换月可能产生非市场交易造成的价格跳空，支撑阻力可信度需谨慎评估。",
                    "历史与快照来自不同接口，采集时间可能不一致。",
                ]
            )
            if period in {"weekly", "monthly"}:
                period_label = "周线" if period == "weekly" else "月线"
                quality_notes.append(f"{period_label}由上游日线在本地聚合生成。")
            if snapshot is None:
                quality_notes.append("实时快照暂时不可用，本次仅展示历史行情。")
        elif security.asset_type == "us_stock":
            quality_notes.append("美股成交量单位为股；行情可能延迟，不是交易所级实时推送。")
            if adjust != "none":
                quality_notes.append("复权数据由上游计算，企业行动更新可能改变历史价格。")
        if "腾讯（东方财富失败后降级）" in security.data_source:
            quality_notes.append(
                "东方财富历史接口不可用，本次自动使用腾讯日线备用源；"
                "成交量已从股转换为手，换手率已转换为百分比。"
            )
        elif "新浪分钟行情" in security.data_source:
            quality_notes.append(
                "东方财富分钟接口不可用，本次自动使用新浪分钟备用源；"
                "成交量已从股转换为手，分钟数据并非交易所级实时推送。"
            )
            if adjust != "none":
                quality_notes.append(
                    "新浪分钟 OHLC 已使用腾讯日线收盘价计算的复权因子调整。"
                )
        if period == "1m":
            quality_notes.append(
                "AKShare 1分钟历史通常仅覆盖最近若干交易日，并非交易所级实时推送。"
            )
        if len(frame) < 250:
            quality_notes.append(f"当前仅有{len(frame)}根K线，MA250 等长周期指标可能无有效值。")
        if self.cache:
            ttl = (
                self.settings.minute_cache_ttl
                if period in MINUTE_PERIODS
                else self.settings.daily_cache_ttl
            )
            cache_metadata = {
                "name": security.name,
                "detection_method": security.detection_method,
                "data_source": security.data_source,
                "quality_notes": quality_notes,
                "snapshot": snapshot,
                "volume_unit": volume_unit,
                "amount_unit": amount_unit,
                **security.as_dict(),
                "cached_at_utc": datetime.now(UTC).isoformat(),
                "cache_status": {
                    "mode": "network",
                    "existing_rows": 0,
                    "new_rows": len(frame),
                },
            }
            self.cache.set(
                cache_key,
                _records_from_frame(frame),
                ttl,
                cache_metadata,
            )
            if period not in MINUTE_PERIODS:
                series_metadata = dict(cache_metadata)
                series_metadata.update(
                    {"coverage_start": start.isoformat(), "coverage_end": end.isoformat()}
                )
                self.cache.set_history_series(
                    self._history_series_key(
                        security.asset_type, security.symbol, period, adjust
                    ),
                    _records_from_frame(frame),
                    series_metadata,
                )
        return MarketData(
            frame=frame,
            security=security,
            period=period,
            adjust=adjust,
            fetched_at=fetched_at,
            from_cache=False,
            volume_unit=volume_unit,
            amount_unit=amount_unit,
            quality_notes=quality_notes,
            snapshot=snapshot,
            cache_status={"mode": "network", "existing_rows": 0, "new_rows": len(frame)},
        )
