"""江恩确认位与失效位的逐根保守回放。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.gann.anchors import confirmed_gann_anchor


def evaluate_gann_history(
    frame: pd.DataFrame,
    direction: str,
    lookahead_bars: int = 24,
    max_history_bars: int = 800,
) -> dict[str, object]:
    """逐时点重建确认锚点；同根目标与失效按失效处理。"""
    resolved: list[tuple[bool, int]] = []
    sample_count = 0
    seen: set[tuple[str, pd.Timestamp]] = set()
    first_end = max(30, len(frame) - max_history_bars)
    for end in range(first_end, max(first_end, len(frame) - 1)):
        window_start = max(0, end - max_history_bars)
        history = frame.iloc[window_start : end + 1].reset_index(drop=True)
        anchor = confirmed_gann_anchor(history)
        if anchor is None or anchor.direction != direction:
            continue
        key = (anchor.pivot.kind, anchor.pivot.timestamp)
        if key in seen:
            continue
        seen.add(key)
        sample_count += 1
        target = anchor.previous_pivot.price
        invalidation = anchor.pivot.price
        future = frame.iloc[end + 1 : end + 1 + lookahead_bars]
        for bars, row in enumerate(future.itertuples(), start=1):
            if direction == "up":
                failed = float(row.low) <= invalidation
                reached = float(row.high) >= target
            else:
                failed = float(row.high) >= invalidation
                reached = float(row.low) <= target
            if failed:
                resolved.append((False, bars))
                break
            if reached:
                resolved.append((True, bars))
                break
    successes = [bars for reached, bars in resolved if reached]
    target_first_count = sum(reached for reached, _bars in resolved)
    calibrated = len(resolved) >= 30
    return {
        "sample_count": sample_count,
        "resolved_count": len(resolved),
        "target_first_count": target_first_count,
        "invalidation_first_count": len(resolved) - target_first_count,
        "target_first_rate": (
            round(target_first_count / len(resolved) * 100, 2)
            if calibrated
            else None
        ),
        "median_target_bars": round(float(np.median(successes)), 1)
        if calibrated and successes
        else None,
        "calibrated": calibrated,
        "lookahead_bars": lookahead_bars,
        "evaluation_bars": min(len(frame), max_history_bars),
        "note": (
            "历史已决样本不足 30 次，暂不展示概率。"
            if not calibrated
            else "历史逐根回放采用同根失效优先的保守规则。"
        ),
    }
