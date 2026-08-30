"""API 校验模型及领域数据结构。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, Field, field_validator, model_validator

from app.config import SHANGHAI_TZ

AssetType = Literal[
    "auto",
    "stock",
    "etf",
    "cn_stock",
    "cn_etf",
    "us_stock",
    "us_index",
    "global_future",
]
ResolvedAssetType = Literal[
    "stock", "etf", "cn_stock", "cn_etf", "us_stock", "us_index", "global_future"
]
Period = Literal["daily", "weekly", "monthly", "1m", "5m", "15m", "30m", "60m"]
Adjust = Literal["none", "qfq", "hfq"]


def default_start_date() -> date:
    return datetime.now(SHANGHAI_TZ).date() - timedelta(days=730)


def default_end_date() -> date:
    return datetime.now(SHANGHAI_TZ).date()


class AnalyzeRequest(BaseModel):
    """Web 与服务层共用的分析请求。"""

    symbol: str = Field(..., examples=["600011"])
    asset_type: AssetType = "auto"
    period: Period = "daily"
    adjust: Adjust = "qfq"
    start: date = Field(default_factory=default_start_date)
    end: date = Field(default_factory=default_end_date)
    show_ma: bool = True
    show_boll: bool = True
    show_levels: bool = True
    show_kdj: bool = False
    force_refresh: bool = False

    @field_validator("symbol", mode="before")
    @classmethod
    def validate_symbol(cls, value: Any) -> str:
        return str(value).strip().upper()

    @model_validator(mode="after")
    def validate_date_range(self) -> AnalyzeRequest:
        if self.asset_type in {"us_stock", "us_index", "global_future"} and (
            "adjust" not in self.model_fields_set
        ):
            self.adjust = "none"
        if self.asset_type in {"auto", "stock", "etf", "cn_stock", "cn_etf"}:
            if len(self.symbol) != 6 or not self.symbol.isascii() or not self.symbol.isdigit():
                raise ValueError("A股和场内ETF代码必须是六位数字")
        elif self.asset_type == "us_index":
            if self.symbol not in {".IXIC", ".NDX", ".INX", ".DJI"}:
                raise ValueError("美国指数仅支持 .IXIC、.NDX、.INX、.DJI")
        elif not (
            1 <= len(self.symbol) <= 16
            and self.symbol[0].isalnum()
            and all(char.isascii() and (char.isalnum() or char in ".-") for char in self.symbol)
        ):
            raise ValueError("美股或期货代码格式无效")
        if self.start > self.end:
            raise ValueError("开始日期不能晚于结束日期")
        if (self.end - self.start).days > 365 * 15:
            raise ValueError("单次查询区间不能超过15年")
        if self.asset_type in {"us_index", "global_future"} and self.adjust != "none":
            raise ValueError("美国指数和外盘期货不支持复权，请选择不复权")
        if self.asset_type == "global_future" and self.period not in {
            "daily", "weekly", "monthly"
        }:
            raise ValueError("外盘期货连续参考序列不支持分钟行情")
        if self.asset_type == "us_index" and self.period not in {"daily", "weekly", "monthly"}:
            raise ValueError("美国指数不支持分钟行情")
        if self.asset_type == "us_stock" and self.period not in {
            "daily", "weekly", "monthly", "1m"
        }:
            raise ValueError("当前 AKShare 美股分钟接口仅提供1分钟线")
        if self.asset_type == "us_stock" and self.period == "1m" and self.adjust != "none":
            raise ValueError("当前 AKShare 美股1分钟行情不支持复权")
        return self


class ErrorBody(BaseModel):
    code: str
    message: str
    detail: Any | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


@dataclass(slots=True)
class SecurityInfo:
    symbol: str
    name: str
    asset_type: ResolvedAssetType
    detection_method: str
    data_source: str
    updated_at: datetime
    market_status: str = "未知"
    canonical_symbol: str | None = None
    provider_symbol: str | None = None
    exchange: str = "未知"
    currency: str = "CNY"
    timezone: str = "Asia/Shanghai"
    source: str | None = None
    capabilities: dict[str, Any] | None = None
    subtype: str | None = None
    series_type: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "asset_type": self.asset_type,
            "detection_method": self.detection_method,
            "data_source": self.data_source,
            "updated_at": self.updated_at.isoformat(),
            "market_status": self.market_status,
            "canonical_symbol": self.canonical_symbol or self.symbol,
            "provider_symbol": self.provider_symbol or self.symbol,
            "exchange": self.exchange,
            "currency": self.currency,
            "timezone": self.timezone,
            "source": self.source or self.data_source,
            "capabilities": self.capabilities or {},
            "subtype": self.subtype,
            "series_type": self.series_type,
        }


@dataclass(slots=True)
class MarketData:
    frame: pd.DataFrame
    security: SecurityInfo
    period: Period
    adjust: Adjust
    fetched_at: datetime
    from_cache: bool
    volume_unit: str = "手"
    amount_unit: str = "元"
    quality_notes: list[str] | None = None
    snapshot: dict[str, Any] | None = None
    cache_status: dict[str, Any] | None = None

    def data_quality(self) -> dict[str, Any]:
        """返回规范化后行情的可审计质量摘要。"""
        frame = self.frame
        if frame.empty:
            return {"status": "异常", "rows": 0, "issues": ["没有有效K线"]}
        duplicate_rows = int(frame["datetime"].duplicated().sum())
        invalid_ohlc = int(
            (
                (frame["high"] < frame[["open", "close", "low"]].max(axis=1))
                | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
            ).sum()
        )
        missing_volume = int(frame["volume"].isna().sum()) if "volume" in frame else len(frame)
        issues: list[str] = []
        if duplicate_rows:
            issues.append(f"存在{duplicate_rows}条重复时间记录")
        if invalid_ohlc:
            issues.append(f"存在{invalid_ohlc}条OHLC关系异常记录")
        if missing_volume:
            issues.append(f"有{missing_volume}根K线缺少成交量，量能评分保持中性")
        status = "良好" if not issues else ("注意" if not invalid_ohlc else "异常")
        return {
            "status": status,
            "rows": len(frame),
            "first_bar": pd.Timestamp(frame["datetime"].iloc[0]).isoformat(),
            "last_bar": pd.Timestamp(frame["datetime"].iloc[-1]).isoformat(),
            "duplicate_rows": duplicate_rows,
            "invalid_ohlc_rows": invalid_ohlc,
            "missing_volume_rows": missing_volume,
            "issues": issues,
        }

    def metadata(self) -> dict[str, Any]:
        return {
            "security": self.security.as_dict(),
            "period": self.period,
            "adjust": self.adjust,
            "fetched_at": self.fetched_at.isoformat(),
            "from_cache": self.from_cache,
            "volume_unit": self.volume_unit,
            "amount_unit": self.amount_unit,
            "quality_notes": self.quality_notes or [],
            "snapshot": self.snapshot,
            "rows": len(self.frame),
            "cache_status": self.cache_status
            or {"mode": "exact_cache" if self.from_cache else "network"},
            "data_quality": self.data_quality(),
        }


class ProviderError(RuntimeError):
    """行情适配层的可预期错误。"""

    def __init__(self, code: str, message: str, detail: Any | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail


class AnalysisError(RuntimeError):
    """分析和报告生成阶段的可预期错误。"""

    def __init__(self, code: str, message: str, detail: Any | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail
