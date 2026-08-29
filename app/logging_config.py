"""Application logging with a local rotating file sink."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from app.config import Settings

LOGGER_NAME = "akshare_analyzer"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(app_settings: Settings) -> logging.Logger:
    """Configure the application logger once and write events to app.log."""
    app_settings.ensure_directories()
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(getattr(logging, app_settings.log_level, logging.INFO))
    logger.propagate = False
    log_path = (app_settings.log_dir / "app.log").resolve()
    if any(
        isinstance(handler, RotatingFileHandler)
        and handler.baseFilename == str(log_path)
        for handler in logger.handlers
    ):
        return logger

    for existing_handler in logger.handlers[:]:
        logger.removeHandler(existing_handler)
        existing_handler.close()
    handler = RotatingFileHandler(
        log_path,
        maxBytes=app_settings.log_max_bytes,
        backupCount=app_settings.log_backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(handler)
    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced application logger."""
    return logging.getLogger(f"{LOGGER_NAME}.{name}")
