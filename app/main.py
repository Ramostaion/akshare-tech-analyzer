"""FastAPI Web 服务入口。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from app import __version__
from app.cache import SQLiteCache
from app.config import PROJECT_ROOT, settings
from app.data_provider import MarketDataProvider
from app.logging_config import configure_logging, get_logger
from app.models import AnalysisError, AnalyzeRequest, AssetType, ProviderError
from app.service import AnalyzerService

logger = get_logger("api")


def error_payload(code: str, message: str, detail: Any | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "detail": detail}}


@asynccontextmanager
async def lifespan(application: FastAPI):
    settings.ensure_directories()
    configure_logging(settings)
    logger.info("application_starting")
    if not hasattr(application.state, "service"):
        cache = SQLiteCache(settings.cache_db)
        provider = MarketDataProvider(cache=cache, app_settings=settings)
        application.state.cache = cache
        application.state.service = AnalyzerService(provider, cache, settings)
    yield
    logger.info("application_stopping")


app = FastAPI(
    title="AKShare 多市场技术分析器",
    version=__version__,
    description="确定性规则驱动的中国证券、美股、美国指数和外盘期货技术分析",
    lifespan=lifespan,
)
templates = Jinja2Templates(directory=PROJECT_ROOT / "templates")
app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "static"), name="static")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    detail = []
    for error in exc.errors():
        item = {
            "type": error.get("type"),
            "loc": list(error.get("loc", ())),
            "message": error.get("msg"),
            "input": error.get("input"),
        }
        if error.get("ctx"):
            item["context"] = {key: str(value) for key, value in error["ctx"].items()}
        detail.append(item)
    return JSONResponse(
        status_code=422,
        content=error_payload("INVALID_REQUEST", "请求参数校验失败", detail),
    )


@app.exception_handler(ProviderError)
async def provider_exception_handler(request: Request, exc: ProviderError) -> JSONResponse:
    logger.warning(
        "provider_error code=%s path=%s detail=%s",
        exc.code,
        request.url.path,
        exc.detail,
    )
    client_errors = {"EMPTY_DATA", "INVALID_DATA", "INVALID_SYMBOL", "MINUTE_DATA_UNSUPPORTED"}
    status = 400 if exc.code in client_errors else 503
    return JSONResponse(
        status_code=status, content=error_payload(exc.code, exc.message, exc.detail)
    )


@app.exception_handler(AnalysisError)
async def analysis_exception_handler(_request: Request, exc: AnalysisError) -> JSONResponse:
    return JSONResponse(status_code=404, content=error_payload(exc.code, exc.message, exc.detail))


@app.exception_handler(Exception)
async def unexpected_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unexpected_error path=%s type=%s", request.url.path, type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content=error_payload("INTERNAL_ERROR", "服务处理请求时发生内部错误", type(exc).__name__),
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": app.title, "version": __version__}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/api/security/{symbol}")
async def security(
    request: Request,
    symbol: str,
    asset_type: AssetType = Query("auto"),
) -> dict[str, Any]:
    normalized = symbol.strip().upper()
    if asset_type in {"auto", "stock", "etf", "cn_stock", "cn_etf"} and (
        len(normalized) != 6 or not normalized.isascii() or not normalized.isdigit()
    ):
        raise ProviderError("INVALID_SYMBOL", "A股和场内ETF代码必须是六位数字")
    service: AnalyzerService = request.app.state.service
    info = await run_in_threadpool(service.provider.identify, normalized, asset_type)
    return {"security": info.as_dict()}


@app.get("/api/instruments/search")
async def search_instruments(
    request: Request,
    q: str = Query(..., min_length=1, max_length=40),
    asset_type: AssetType = Query("us_stock"),
) -> dict[str, Any]:
    if asset_type not in {"us_stock", "us_index", "global_future"}:
        return {"items": []}
    service: AnalyzerService = request.app.state.service
    items = await run_in_threadpool(service.provider.search_instruments, q, asset_type)
    return {"items": items}


@app.post("/api/analyze")
async def analyze(request: Request, payload: AnalyzeRequest) -> dict[str, Any]:
    service: AnalyzerService = request.app.state.service
    bundle = await run_in_threadpool(service.analyze, payload)
    logger.info(
        "analysis_completed symbol=%s asset_type=%s period=%s from_cache=%s report_id=%s",
        payload.symbol,
        payload.asset_type,
        payload.period,
        bundle.market_data.from_cache,
        bundle.report_id,
    )
    return bundle.api_payload(payload)


def _get_report_path(request: Request, report_id: str) -> tuple[Path, str]:
    if (
        not report_id
        or len(report_id) > 64
        or not all(char.isalnum() or char in "-_" for char in report_id)
    ):
        raise AnalysisError("REPORT_NOT_FOUND", "报告不存在或已失效")
    service: AnalyzerService = request.app.state.service
    record = service.cache.get_report(report_id)
    if record is None or not record.path.is_file():
        raise AnalysisError("REPORT_NOT_FOUND", "报告不存在或已失效")
    report_root = service.settings.report_dir.resolve()
    path = record.path.resolve()
    if not path.is_relative_to(report_root):
        raise AnalysisError("REPORT_PATH_INVALID", "报告路径不在允许目录内")
    return path, record.symbol


@app.get("/api/report/{report_id}", response_class=HTMLResponse)
async def view_report(request: Request, report_id: str) -> HTMLResponse:
    path, _ = _get_report_path(request, report_id)
    return HTMLResponse(path.read_text(encoding="utf-8"))


@app.get("/api/report/{report_id}/download")
async def download_report(request: Request, report_id: str) -> FileResponse:
    path, symbol = _get_report_path(request, report_id)
    return FileResponse(path, media_type="text/html", filename=f"{symbol}_technical_report.html")
