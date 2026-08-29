"""离线单文件 HTML 报告生成。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from plotly.graph_objects import Figure

from app.charts import render_figure_html
from app.config import PROJECT_ROOT, SHANGHAI_TZ
from app.models import AnalyzeRequest, MarketData


def safe_report_filename(
    request: AnalyzeRequest,
    resolved_asset_type: str | None = None,
    now: datetime | None = None,
) -> str:
    """仅使用校验后的白名单字段构建 Web 报告文件名。"""
    generated_at = (now or datetime.now(SHANGHAI_TZ)).strftime("%Y%m%d_%H%M%S")
    asset_type = resolved_asset_type or request.asset_type
    safe_symbol = request.symbol.replace(".", "_").replace("-", "_").strip("_")
    parts = (safe_symbol, asset_type, request.period, request.adjust, generated_at)
    return "_".join(parts) + ".html"


def render_report_header(
    market_data: MarketData,
    request: AnalyzeRequest,
    analysis: dict[str, Any],
    levels: dict[str, Any],
) -> str:
    environment = Environment(
        loader=FileSystemLoader(PROJECT_ROOT / "templates"),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = environment.get_template("report.html")
    return template.render(
        market=market_data.metadata(),
        request=request,
        analysis=analysis,
        levels=levels,
        generated_at=datetime.now(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S %Z"),
    )


def build_report_html(
    figure: Figure,
    market_data: MarketData,
    request: AnalyzeRequest,
    analysis: dict[str, Any],
    levels: dict[str, Any],
) -> str:
    """生成包含 Plotly、CSS、分析正文的完整离线 HTML。"""
    html = render_figure_html(figure, full_html=True)
    header = render_report_header(market_data, request, analysis, levels)
    return html.replace("<body>", f"<body>{header}", 1).replace(
        "<head>",
        '<head><meta name="viewport" content="width=device-width,initial-scale=1">',
        1,
    )


def write_report(html: str, output_path: Path) -> Path:
    output = Path(output_path).expanduser().resolve()
    if output.suffix.lower() != ".html":
        raise ValueError("报告输出文件必须使用 .html 后缀")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    return output
