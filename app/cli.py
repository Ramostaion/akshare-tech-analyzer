"""命令行离线 HTML 报告入口。"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from app.cache import SQLiteCache
from app.config import settings
from app.data_provider import MarketDataProvider
from app.logging_config import configure_logging, get_logger
from app.models import AnalyzeRequest, ProviderError
from app.service import AnalyzerService

logger = get_logger("cli")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AKShare 多市场技术分析离线报告")
    parser.add_argument("--symbol", required=True, help="证券、指数或期货品种代码")
    parser.add_argument(
        "--asset-type",
        choices=[
            "auto", "stock", "etf", "cn_stock", "cn_etf", "us_stock", "us_index",
            "global_future",
        ],
        default="auto",
    )
    parser.add_argument(
        "--period",
        choices=["daily", "weekly", "monthly", "1m", "5m", "15m", "30m", "60m"],
        default="daily",
    )
    parser.add_argument("--start", type=date.fromisoformat, required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", type=date.fromisoformat, required=True, help="YYYY-MM-DD")
    parser.add_argument("--adjust", choices=["none", "qfq", "hfq"], default=None)
    parser.add_argument("--output", type=Path, required=True, help="输出 .html 文件")
    parser.add_argument("--show-kdj", action="store_true", help="图中增加 KDJ 子图")
    parser.add_argument("--force-refresh", action="store_true", help="忽略未过期缓存")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        request = AnalyzeRequest(
            symbol=args.symbol,
            asset_type=args.asset_type,
            period=args.period,
            start=args.start,
            end=args.end,
            adjust=args.adjust
            or ("none" if args.asset_type in {"us_stock", "us_index", "global_future"} else "qfq"),
            show_kdj=args.show_kdj,
            force_refresh=args.force_refresh,
        )
        settings.ensure_directories()
        configure_logging(settings)
        cache = SQLiteCache(settings.cache_db)
        provider = MarketDataProvider(cache, settings)
        bundle = AnalyzerService(provider, cache, settings).analyze(request, args.output)
    except (ProviderError, ValidationError, ValueError) as exc:
        message = exc.message if isinstance(exc, ProviderError) else str(exc)
        logger.exception("cli_generation_failed symbol=%s error=%s", args.symbol, message)
        print(f"生成失败：{message}", file=sys.stderr)
        return 2
    security = bundle.market_data.security
    print(f"证券名称：{security.name} ({security.symbol})")
    print(f"数据条数：{len(bundle.market_data.frame)}")
    print(f"分析状态：{bundle.analysis['state']}")
    print(f"技术评分：{bundle.analysis['score']}/100")
    print(f"HTML报告：{bundle.report_path.resolve()}")
    print("提示：仅为算法技术分析结果，不构成投资建议。")
    logger.info("cli_generation_completed symbol=%s report=%s", security.symbol, bundle.report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
