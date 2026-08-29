"""应用配置及路径管理。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def _load_dotenv(path: Path) -> None:
    """加载简单的 KEY=VALUE 配置，不覆盖进程已有环境变量。"""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _env_float(name: str, default: float, minimum: float = 0.0) -> float:
    try:
        return max(minimum, float(os.getenv(name, str(default))))
    except ValueError:
        return default


@dataclass(frozen=True, slots=True)
class Settings:
    """运行配置；环境变量可覆盖所有涉及部署和缓存的值。"""

    app_host: str = "0.0.0.0"
    app_port: int = 8000
    cache_db: Path = field(default_factory=lambda: PROJECT_ROOT / "cache" / "market.db")
    report_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "reports")
    log_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "logs")
    max_provider_concurrency: int = 2
    minute_cache_ttl: int = 60
    daily_cache_ttl: int = 7200
    etf_list_cache_ttl: int = 21600
    instrument_list_cache_ttl: int = 14400
    snapshot_cache_ttl: int = 20
    request_retries: int = 3
    request_timeout: int = 25
    stale_cache_max_age: int = 86400
    log_level: str = "INFO"
    log_max_bytes: int = 5 * 1024 * 1024
    log_backup_count: int = 5
    level_swing_window: int = 4
    level_price_pct: float = 0.008
    level_atr_factor: float = 0.5
    level_min_score: float = 1.35

    @classmethod
    def from_env(cls) -> Settings:
        _load_dotenv(PROJECT_ROOT / ".env")
        return cls(
            app_host=os.getenv("APP_HOST", "0.0.0.0"),
            app_port=_env_int("APP_PORT", 8000),
            cache_db=Path(os.getenv("CACHE_DB", str(PROJECT_ROOT / "cache" / "market.db"))),
            report_dir=Path(os.getenv("REPORT_DIR", str(PROJECT_ROOT / "reports"))),
            log_dir=Path(os.getenv("LOG_DIR", str(PROJECT_ROOT / "logs"))),
            max_provider_concurrency=_env_int("MAX_PROVIDER_CONCURRENCY", 2),
            minute_cache_ttl=_env_int("MINUTE_CACHE_TTL", 60),
            daily_cache_ttl=_env_int("DAILY_CACHE_TTL", 7200),
            etf_list_cache_ttl=_env_int("ETF_LIST_CACHE_TTL", 21600),
            instrument_list_cache_ttl=_env_int("INSTRUMENT_LIST_CACHE_TTL", 14400),
            snapshot_cache_ttl=_env_int("SNAPSHOT_CACHE_TTL", 20),
            request_retries=_env_int("REQUEST_RETRIES", 3),
            request_timeout=_env_int("REQUEST_TIMEOUT", 25),
            stale_cache_max_age=_env_int("STALE_CACHE_MAX_AGE", 86400),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            log_max_bytes=_env_int("LOG_MAX_BYTES", 5 * 1024 * 1024),
            log_backup_count=_env_int("LOG_BACKUP_COUNT", 5),
            level_swing_window=_env_int("LEVEL_SWING_WINDOW", 4, 3),
            level_price_pct=_env_float("LEVEL_PRICE_PCT", 0.008),
            level_atr_factor=_env_float("LEVEL_ATR_FACTOR", 0.5),
            level_min_score=_env_float("LEVEL_MIN_SCORE", 1.35),
        )

    def ensure_directories(self) -> None:
        self.cache_db.parent.mkdir(parents=True, exist_ok=True)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)


settings = Settings.from_env()
