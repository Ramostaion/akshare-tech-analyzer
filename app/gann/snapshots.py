"""不可变江恩预测快照的构造与标识。"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def build_snapshot(symbol: str, timeframe: str, result: dict[str, Any]) -> dict[str, Any]:
    anchor = result.get("anchor", {})
    timestamp = str(result.get("snapshot_time"))
    calculation = {
        "version": result.get("version"),
        "anchor": anchor,
        "scale": result.get("scale", {}),
        "fan": result.get("fan_lines", []),
        "price_zones": result.get("price_zones", []),
        "time_windows": result.get("time_windows", []),
        "confluence": result.get("confluence_zones", []),
        "scenarios": result.get("scenarios", []),
    }
    fingerprint = hashlib.sha256(
        json.dumps(calculation, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]
    raw = (
        f"{symbol}|{timeframe}|{timestamp}|{anchor.get('lifecycle_id', '')}|{fingerprint}"
    )
    snapshot_id = hashlib.sha256(raw.encode()).hexdigest()[:24]
    return {
        "snapshot_id": snapshot_id,
        "calculation_fingerprint": fingerprint,
        "timestamp": timestamp,
        "symbol": symbol,
        "timeframe": timeframe,
        "anchor": anchor,
        "price_scale_mode": result.get("scale", {}).get("mode"),
        "price_unit": result.get("scale", {}).get("price_unit"),
        "gann_angles": result.get("fan_lines", []),
        "price_levels": result.get("price_levels", []),
        "price_zones": result.get("price_zones", []),
        "time_windows": result.get("time_windows", []),
        "confluence_zones": result.get("confluence_zones", []),
        "scenarios": result.get("scenarios", []),
        "anchor_lifecycles": result.get("anchor_lifecycles", []),
        "forecast_horizon": result.get("forecast_horizon", {}),
        "immutable": True,
    }


__all__ = ["build_snapshot"]
