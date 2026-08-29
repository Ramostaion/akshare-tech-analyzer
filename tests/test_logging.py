from __future__ import annotations

from app.config import Settings
from app.logging_config import configure_logging, get_logger


def test_application_errors_are_written_to_rotating_log(tmp_path) -> None:
    app_settings = Settings(
        cache_db=tmp_path / "cache" / "market.db",
        report_dir=tmp_path / "reports",
        log_dir=tmp_path / "logs",
    )
    logger = configure_logging(app_settings)
    get_logger("test").error("provider_error code=TEST_FAILURE")
    for handler in logger.handlers:
        handler.flush()
    log_text = (app_settings.log_dir / "app.log").read_text(encoding="utf-8")
    assert "provider_error code=TEST_FAILURE" in log_text
