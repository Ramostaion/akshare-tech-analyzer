"""不可变江恩预测快照的构造与标识。"""

from __future__ import annotations

import hashlib
from typing import Any


def build_snapshot(symbol: str, timeframe: str, result: dict[str, Any]) -> dict[str, Any]:
    anchor = result.get("anchor", {})
    timestamp = str(result.get("snapshot_time"))
    raw = f"{symbol}|{timeframe}|{timestamp}|{anchor.get('lifecycle_id', '')}"
    snapshot_id = hashlib.sha256(raw.encode()).hexdigest()[:24]
    return {
        "snapshot_id": snapshot_id,
        "timestamp": timestamp,
        "symbol": symbol,
        "timeframe": timeframe,
        "anchor": anchor,
        "price_scale_mode": result.get("scale", {}).get("mode"),
        "price_unit": result.get("scale", {}).get("price_unit"),
        "gann_angles": result.get("fan_lines", []),
        "price_levels": result.get("price_levels", []),
        "time_windows": result.get("time_windows", []),
        "confluence_zones": result.get("confluence_zones", []),
        "scenarios": result.get("scenarios", []),
        "immutable": True,
    }


__all__ = ["build_snapshot"]
