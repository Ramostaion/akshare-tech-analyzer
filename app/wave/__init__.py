"""第一版 Elliott Wave 候选分析。"""

from app.wave.patterns import find_wave_candidates
from app.wave.pivots import confirmed_zigzag_pivots


def analyze_wave_candidates(frame, top_n: int = 3):
    """返回 Top-N 候选；结果表达候选而非唯一浪型断言。"""
    pivots = confirmed_zigzag_pivots(frame)
    return {
        "candidates": find_wave_candidates(frame, pivots, top_n=top_n),
        "pivot_count": len(pivots),
        "note": "波浪结果为基于已确认Pivot的候选结构，不代表唯一正确浪型。",
    }


__all__ = ["analyze_wave_candidates", "confirmed_zigzag_pivots", "find_wave_candidates"]
