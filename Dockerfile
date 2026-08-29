FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CACHE_DB=/data/cache/market.db \
    REPORT_DIR=/data/reports

WORKDIR /app

RUN groupadd --system analyzer \
    && useradd --system --gid analyzer --home-dir /app analyzer \
    && mkdir -p /data/cache /data/reports \
    && chown -R analyzer:analyzer /app /data

COPY pyproject.toml README.md ./
COPY app ./app
COPY templates ./templates
COPY static ./static

RUN pip install --upgrade pip \
    && pip install .

USER analyzer
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
