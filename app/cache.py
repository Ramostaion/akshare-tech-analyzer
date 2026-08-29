"""SQLite 缓存与报告元数据存储。"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class CacheEntry:
    payload: Any
    metadata: dict[str, Any]
    created_at: datetime
    expires_at: datetime


@dataclass(slots=True)
class ReportRecord:
    report_id: str
    path: Path
    symbol: str
    created_at: datetime


class SQLiteCache:
    """线程安全的轻量 SQLite JSON 缓存，不执行任意对象反序列化。"""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        with self._connection:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA busy_timeout=5000")
        self._initialize()

    def _initialize(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS cache_entries (
                    cache_key TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_cache_expiry ON cache_entries(expires_at);
                CREATE TABLE IF NOT EXISTS analysis_results (
                    analysis_id TEXT PRIMARY KEY,
                    request_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reports (
                    report_id TEXT PRIMARY KEY,
                    file_path TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def get(self, key: str, allow_expired: bool = False) -> CacheEntry | None:
        now = datetime.now(UTC)
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM cache_entries WHERE cache_key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at <= now and not allow_expired:
            return None
        return CacheEntry(
            payload=json.loads(row["payload_json"]),
            metadata=json.loads(row["metadata_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            expires_at=expires_at,
        )

    def set(self, key: str, payload: Any, ttl_seconds: int, metadata: dict[str, Any]) -> None:
        created_at = datetime.now(UTC)
        expires_at = created_at + timedelta(seconds=ttl_seconds)
        payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        metadata_json = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO cache_entries
                    (cache_key, payload_json, metadata_json, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    metadata_json = excluded.metadata_json,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at
                """,
                (key, payload_json, metadata_json, created_at.isoformat(), expires_at.isoformat()),
            )

    def save_analysis(
        self, analysis_id: str, request: dict[str, Any], result: dict[str, Any]
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO analysis_results
                    (analysis_id, request_json, result_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    analysis_id,
                    json.dumps(request, ensure_ascii=False),
                    json.dumps(result, ensure_ascii=False),
                    datetime.now(UTC).isoformat(),
                ),
            )

    def save_report(
        self,
        report_id: str,
        path: Path,
        symbol: str,
        request: dict[str, Any],
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO reports (report_id, file_path, symbol, request_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    str(path.resolve()),
                    symbol,
                    json.dumps(request, ensure_ascii=False),
                    datetime.now(UTC).isoformat(),
                ),
            )

    def get_report(self, report_id: str) -> ReportRecord | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT report_id, file_path, symbol, created_at FROM reports WHERE report_id = ?",
                (report_id,),
            ).fetchone()
        if row is None:
            return None
        return ReportRecord(
            report_id=row["report_id"],
            path=Path(row["file_path"]),
            symbol=row["symbol"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def purge_expired(self) -> int:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "DELETE FROM cache_entries WHERE expires_at <= ?", (datetime.now(UTC).isoformat(),)
            )
        return cursor.rowcount

    def close(self) -> None:
        with self._lock:
            self._connection.close()
