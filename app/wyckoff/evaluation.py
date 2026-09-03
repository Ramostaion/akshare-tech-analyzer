"""威科夫候选的逐根保守历史回放。"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.wyckoff.events import detect_wyckoff_structure
from app.wyckoff.projection import project_wyckoff


def evaluate_wyckoff_history(
    frame: pd.DataFrame,
    direction: str,
    lookahead_bars: int = 20,
    max_history_bars: int = 420,
) -> dict[str, Any]:
    """按当时可见前缀重建结构，同根目标与失效按失效优先。"""
    outcomes: list[tuple[bool, int]] = []
    first_end = max(80, len(frame) - max_history_bars)
    for end in range(first_end, len(frame) - lookahead_bars, 5):
        history = frame.iloc[: end + 1]
        structure = detect_wyckoff_structure(history)
        if structure.get("status") != "active" or structure.get("direction") != direction:
            continue
        if structure.get("current_event") == "Trading Range":
            continue
        projection = project_wyckoff(history, structure)
        lower, upper = projection["target_zone"]
        invalidation = float(projection["invalidation"])
        future = frame.iloc[end + 1 : end + 1 + lookahead_bars]
        for bars, row in enumerate(future.itertuples(), start=1):
            invalid = row.low <= invalidation if direction == "up" else row.high >= invalidation
            target = row.high >= lower if direction == "up" else row.low <= upper
            if invalid:
                outcomes.append((False, bars))
                break
            if target:
                outcomes.append((True, bars))
                break
    wins = [bars for reached, bars in outcomes if reached]
    calibrated = len(outcomes) >= 30
    return {
        "sample_count": len(outcomes),
        "resolved_count": len(outcomes),
        "target_first_rate": round(len(wins) / len(outcomes) * 100, 1)
        if calibrated and outcomes
        else None,
        "median_target_bars": round(float(np.median(wins)), 1) if calibrated and wins else None,
        "calibrated": calibrated,
        "lookahead_bars": lookahead_bars,
        "note": (
            "已决样本不足 30 次，暂不展示概率。"
            if not calibrated
            else "历史统计不代表未来收益。"
        ),
    }
