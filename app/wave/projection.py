"""候选浪目标区与失效位投影。"""

from __future__ import annotations

from app.wave.pivots import WavePivot


def project_candidate(pattern: str, pivots: list[WavePivot]) -> dict[str, object]:
    """使用已完成波段的 Fib 比例给出研究区间，而非固定收益预测。"""
    if len(pivots) < 3:
        return {"primary_zone": [], "invalidation": None}
    prices = [item.price for item in pivots]
    if pattern in {"impulse", "unfinished_impulse"}:
        base_move = abs(prices[1] - prices[0])
        anchor = prices[-1]
        return {
            "primary_zone": [round(anchor + base_move * 0.618, 4), round(anchor + base_move, 4)],
            "invalidation": round(prices[-2], 4),
        }
    first_leg = abs(prices[-2] - prices[-3])
    anchor = prices[-1]
    return {
        "primary_zone": [round(anchor - first_leg, 4), round(anchor - first_leg * 0.618, 4)],
        "invalidation": round(prices[-2], 4),
    }
