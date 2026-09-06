"""无未来函数的威科夫稳定区间与双候选事件状态机。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

LOOKBACK = 60
RANGE_SEED_BARS = 40
BREAK_CONFIRM_BARS = 3
EVENT_COOLDOWN_BARS = 4


@dataclass(slots=True)
class StructureState:
    structure: str
    direction: str
    phase: str = "B"
    events: list[dict[str, Any]] = field(default_factory=list)
    spring_or_utad: dict[str, Any] | None = None
    strength_event: dict[str, Any] | None = None
    phase_e_count: int = 0


def _finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _range_timeline(work: pd.DataFrame) -> pd.DataFrame:
    """逐根冻结区间；连续三根有效离开后才用最近窗口建立新区间。"""
    timeline = pd.DataFrame(
        {"support": np.nan, "resistance": np.nan, "range_start": -1},
        index=work.index,
    )
    seed = work.iloc[:LOOKBACK]
    support = float(seed["low"].quantile(0.12))
    resistance = float(seed["high"].quantile(0.88))
    range_start = 0
    above_count = below_count = 0
    for position in range(LOOKBACK, len(work)):
        row = work.iloc[position]
        atr = _finite(row.get("ATR14")) or 0.0
        margin = atr * 0.35
        close = float(row["close"])
        above_count = above_count + 1 if close > resistance + margin else 0
        below_count = below_count + 1 if close < support - margin else 0
        if max(above_count, below_count) >= BREAK_CONFIRM_BARS:
            range_start = max(0, position - RANGE_SEED_BARS + 1)
            recent = work.iloc[range_start : position + 1]
            support = float(recent["low"].quantile(0.12))
            resistance = float(recent["high"].quantile(0.88))
            above_count = below_count = 0
        timeline.loc[position] = (support, resistance, range_start)
    return timeline


def _range_quality(
    work: pd.DataFrame,
    timeline: pd.DataFrame,
    range_start: int,
) -> dict[str, float | int]:
    segment = work.iloc[range_start:]
    current = timeline.iloc[-1]
    support = float(current["support"])
    resistance = float(current["resistance"])
    atr = pd.to_numeric(segment["ATR14"], errors="coerce").median()
    tolerance = (float(atr) if np.isfinite(atr) else 0.0) * 0.25
    contained = segment["close"].between(support - tolerance, resistance + tolerance)
    containment = float(contained.mean()) if len(contained) else 0.0
    support_tests = int((segment["low"] <= support + tolerance).sum())
    resistance_tests = int((segment["high"] >= resistance - tolerance).sum())
    boundary_score = min(1.0, (support_tests + resistance_tests) / 6)
    width_atr = (resistance - support) / atr if np.isfinite(atr) and atr > 0 else 0.0
    width_score = 1.0 if 2.0 <= width_atr <= 15.0 else 0.55
    score = containment * 0.55 + boundary_score * 0.25 + width_score * 0.2
    return {
        "score": round(score, 3),
        "containment": round(containment, 3),
        "support_tests": support_tests,
        "resistance_tests": resistance_tests,
        "width_atr": round(float(width_atr), 3),
    }


def _event(
    label: str,
    direction: str,
    position: int,
    row: pd.Series,
    volume_ratio: float,
    spread_ratio: float,
    close_location: float,
) -> dict[str, Any]:
    timestamp = pd.Timestamp(row["datetime"]).isoformat()
    return {
        "event": label,
        "direction": direction,
        "position": position,
        "timestamp": timestamp,
        "price": round(float(row["close"]), 6),
        "low": round(float(row["low"]), 6),
        "high": round(float(row["high"]), 6),
        "volume_ratio": round(volume_ratio, 3),
        "spread_atr": round(spread_ratio, 3),
        "close_location": round(close_location, 3),
        "confirmation_state": "close_confirmed",
        "confirmed_at": timestamp,
        "follow_through_confirmed_at": None,
    }


def _append_event(state: StructureState, item: dict[str, Any]) -> bool:
    if state.events:
        latest = state.events[-1]
        if (
            latest["event"] == item["event"]
            and item["position"] - latest["position"] <= EVENT_COOLDOWN_BARS
        ):
            return False
    state.events.append(item)
    return True


def _mark_follow_through(item: dict[str, Any] | None, timestamp: object) -> None:
    if item is None or item.get("follow_through_confirmed_at"):
        return
    item["confirmation_state"] = "follow_through_confirmed"
    item["follow_through_confirmed_at"] = pd.Timestamp(timestamp).isoformat()


def _process_accumulation(
    state: StructureState,
    *,
    position: int,
    row: pd.Series,
    support: float,
    resistance: float,
    atr: float,
    volume_ratio: float,
    spread_ratio: float,
    close_location: float,
    prior_return: float,
) -> None:
    width = resistance - support
    labels = {item["event"] for item in state.events}
    item: dict[str, Any] | None = None
    if (
        state.strength_event is None
        and "SC" not in labels
        and prior_return <= -0.035
        and row["low"] <= support + atr * 0.25
        and volume_ratio >= 1.25
        and spread_ratio >= 1.0
        and close_location >= 0.42
    ):
        item = _event("SC", "up", position, row, volume_ratio, spread_ratio, close_location)
        state.phase = "A"
    elif (
        state.strength_event is None
        and "SC" in labels
        and "AR" not in labels
        and row["high"] >= support + width * 0.55
        and position > state.events[0]["position"]
    ):
        item = _event("AR", "up", position, row, volume_ratio, spread_ratio, close_location)
        state.phase = "B"
    elif (
        state.strength_event is None
        and "AR" in labels
        and "ST" not in labels
        and row["low"] <= support + atr * 0.4
        and row["low"] >= state.events[0]["low"] - atr * 0.15
    ):
        item = _event("ST", "up", position, row, volume_ratio, spread_ratio, close_location)
        state.phase = "B"
    elif (
        state.strength_event is None
        and
        row["low"] < support - atr * 0.05
        and row["close"] > support
        and close_location >= 0.55
        and volume_ratio >= 0.7
    ):
        item = _event(
            "Spring", "up", position, row, volume_ratio, spread_ratio, close_location
        )
        state.phase = "C"
        state.spring_or_utad = item
    elif (
        state.spring_or_utad is not None
        and state.strength_event is None
        and position > state.spring_or_utad["position"]
        and row["low"] <= support + atr * 0.4
        and row["low"] >= state.spring_or_utad["low"] - atr * 0.1
        and volume_ratio <= min(1.0, state.spring_or_utad["volume_ratio"] * 0.95)
        and row["close"] > support
    ):
        item = _event("Test", "up", position, row, volume_ratio, spread_ratio, close_location)
        state.phase = "C"
        _mark_follow_through(state.spring_or_utad, row["datetime"])
    elif (
        state.strength_event is None
        and row["close"] > resistance
        and volume_ratio >= 1.1
        and spread_ratio >= 0.9
        and close_location >= 0.62
    ):
        item = _event("SOS", "up", position, row, volume_ratio, spread_ratio, close_location)
        state.phase = "D"
        state.strength_event = item
    elif (
        state.strength_event is not None
        and position > state.strength_event["position"]
        and row["low"] <= resistance + atr * 0.4
        and row["close"] >= resistance - atr * 0.1
        and volume_ratio <= 1.0
    ):
        item = _event("LPS", "up", position, row, volume_ratio, spread_ratio, close_location)
        state.phase = "D"
        _mark_follow_through(state.strength_event, row["datetime"])
    if item is not None:
        _append_event(state, item)
    state.phase_e_count = state.phase_e_count + 1 if row["close"] > resistance else 0
    if state.strength_event is not None and state.phase_e_count >= 2:
        state.phase = "E"
        _mark_follow_through(state.strength_event, row["datetime"])


def _process_distribution(
    state: StructureState,
    *,
    position: int,
    row: pd.Series,
    support: float,
    resistance: float,
    atr: float,
    volume_ratio: float,
    spread_ratio: float,
    close_location: float,
    prior_return: float,
) -> None:
    width = resistance - support
    labels = {item["event"] for item in state.events}
    item: dict[str, Any] | None = None
    if (
        state.strength_event is None
        and "BC" not in labels
        and prior_return >= 0.035
        and row["high"] >= resistance - atr * 0.25
        and volume_ratio >= 1.25
        and spread_ratio >= 1.0
        and close_location <= 0.58
    ):
        item = _event("BC", "down", position, row, volume_ratio, spread_ratio, close_location)
        state.phase = "A"
    elif (
        state.strength_event is None
        and "BC" in labels
        and "AR" not in labels
        and row["low"] <= resistance - width * 0.55
        and position > state.events[0]["position"]
    ):
        item = _event("AR", "down", position, row, volume_ratio, spread_ratio, close_location)
        state.phase = "B"
    elif (
        state.strength_event is None
        and "AR" in labels
        and "ST" not in labels
        and row["high"] >= resistance - atr * 0.4
        and row["high"] <= state.events[0]["high"] + atr * 0.15
    ):
        item = _event("ST", "down", position, row, volume_ratio, spread_ratio, close_location)
        state.phase = "B"
    elif (
        state.strength_event is None
        and
        row["high"] > resistance + atr * 0.05
        and row["close"] < resistance
        and close_location <= 0.45
        and volume_ratio >= 0.7
    ):
        item = _event(
            "UTAD", "down", position, row, volume_ratio, spread_ratio, close_location
        )
        state.phase = "C"
        state.spring_or_utad = item
    elif (
        state.spring_or_utad is not None
        and state.strength_event is None
        and position > state.spring_or_utad["position"]
        and row["high"] >= resistance - atr * 0.4
        and row["high"] <= state.spring_or_utad["high"] + atr * 0.1
        and volume_ratio <= min(1.0, state.spring_or_utad["volume_ratio"] * 0.95)
        and row["close"] < resistance
    ):
        item = _event("Test", "down", position, row, volume_ratio, spread_ratio, close_location)
        state.phase = "C"
        _mark_follow_through(state.spring_or_utad, row["datetime"])
    elif (
        state.strength_event is None
        and row["close"] < support
        and volume_ratio >= 1.1
        and spread_ratio >= 0.9
        and close_location <= 0.38
    ):
        item = _event("SOW", "down", position, row, volume_ratio, spread_ratio, close_location)
        state.phase = "D"
        state.strength_event = item
    elif (
        state.strength_event is not None
        and position > state.strength_event["position"]
        and row["high"] >= support - atr * 0.4
        and row["close"] <= support + atr * 0.1
        and volume_ratio <= 1.0
    ):
        item = _event("LPSY", "down", position, row, volume_ratio, spread_ratio, close_location)
        state.phase = "D"
        _mark_follow_through(state.strength_event, row["datetime"])
    if item is not None:
        _append_event(state, item)
    state.phase_e_count = state.phase_e_count + 1 if row["close"] < support else 0
    if state.strength_event is not None and state.phase_e_count >= 2:
        state.phase = "E"
        _mark_follow_through(state.strength_event, row["datetime"])


def _candidate_score(
    state: StructureState,
    range_quality: dict[str, float | int],
    preferred_direction: str,
    opposing_event_count: int,
) -> dict[str, Any]:
    distinct_events = len({item["event"] for item in state.events})
    sequence_score = min(100.0, 20.0 + distinct_events * 14.0)
    if state.phase in {"D", "E"}:
        sequence_score = min(100.0, sequence_score + 10)
    if state.events:
        volume_values = [
            min(1.6, max(0.4, float(item["volume_ratio"]))) for item in state.events
        ]
        volume_score = min(100.0, float(np.mean(volume_values)) / 1.2 * 100)
    else:
        volume_score = 35.0
    confirmed = sum(
        item["confirmation_state"] == "follow_through_confirmed"
        for item in state.events
    )
    follow_score = min(100.0, confirmed * 35.0 + (15.0 if state.events else 0.0))
    range_score = float(range_quality["score"]) * 100
    context_bonus = 5.0 if state.direction == preferred_direction else 0.0
    conflict_penalty = min(20.0, opposing_event_count * 4.0)
    total = (
        range_score * 0.35
        + sequence_score * 0.35
        + volume_score * 0.15
        + follow_score * 0.15
        + context_bonus
        - conflict_penalty
    )
    return {
        "range_stability": round(range_score, 1),
        "event_sequence": round(sequence_score, 1),
        "volume_price_quality": round(volume_score, 1),
        "follow_through": round(follow_score, 1),
        "context_bonus": round(context_bonus, 1),
        "conflict_penalty": round(conflict_penalty, 1),
        "total": round(float(np.clip(total, 0, 100)), 1),
    }


def _preferred_direction(work: pd.DataFrame) -> str:
    if "OBV" in work:
        obv = pd.to_numeric(work["OBV"], errors="coerce")
        if len(obv.dropna()) >= 10:
            return "up" if obv.iloc[-1] >= obv.iloc[-10] else "down"
    close = pd.to_numeric(work["close"], errors="coerce")
    return "up" if close.iloc[-1] >= close.rolling(20).mean().iloc[-1] else "down"


def detect_wyckoff_structure(frame: pd.DataFrame) -> dict[str, Any]:
    """用当时可见数据返回稳定区间和吸筹/派发两个竞争候选。"""
    if len(frame) < LOOKBACK + 20 or "ATR14" not in frame:
        return {"status": "insufficient", "note": "至少需要 80 根 K 线识别威科夫结构。"}
    if "volume" not in frame:
        return {
            "status": "volume_unavailable",
            "note": "当前序列缺少可靠成交量，不能生成完整威科夫量价结构。",
        }
    volume = pd.to_numeric(frame["volume"], errors="coerce")
    if not bool((volume.notna() & (volume > 0)).mean() >= 0.8):
        return {
            "status": "volume_unavailable",
            "note": "当前序列缺少可靠成交量，不能生成完整威科夫量价结构。",
        }

    work = frame.reset_index(drop=True).copy()
    timeline = _range_timeline(work)
    current_range = timeline.iloc[-1]
    support = _finite(current_range["support"])
    resistance = _finite(current_range["resistance"])
    range_start = int(current_range["range_start"])
    if support is None or resistance is None or resistance <= support or range_start < 0:
        return {"status": "insufficient", "note": "当前无法形成稳定的威科夫交易区间。"}

    volume_ratio = volume / volume.shift(1).rolling(20, min_periods=10).mean()
    spread = work["high"] - work["low"]
    spread_ratio = spread / work["ATR14"].replace(0, np.nan)
    close_location = (work["close"] - work["low"]) / spread.replace(0, np.nan)
    prior_return = work["close"] / work["close"].shift(10) - 1
    accumulation = StructureState("accumulation", "up")
    distribution = StructureState("distribution", "down")
    for position in range(max(LOOKBACK, range_start), len(work)):
        range_row = timeline.iloc[position]
        if int(range_row["range_start"]) != range_start:
            continue
        values = (
            _finite(range_row["support"]),
            _finite(range_row["resistance"]),
            _finite(work["ATR14"].iloc[position]),
            _finite(volume_ratio.iloc[position]),
            _finite(spread_ratio.iloc[position]),
            _finite(close_location.iloc[position]),
            _finite(prior_return.iloc[position]),
        )
        if any(value is None for value in values):
            continue
        low, high, atr, vr, sr, location, prior = values
        assert low is not None and high is not None and atr is not None
        assert vr is not None and sr is not None and location is not None
        assert prior is not None
        kwargs = {
            "position": position,
            "row": work.iloc[position],
            "support": low,
            "resistance": high,
            "atr": atr,
            "volume_ratio": vr,
            "spread_ratio": sr,
            "close_location": location,
            "prior_return": prior,
        }
        _process_accumulation(accumulation, **kwargs)
        _process_distribution(distribution, **kwargs)

    quality = _range_quality(work, timeline, range_start)
    preferred = _preferred_direction(work)
    acc_score = _candidate_score(accumulation, quality, preferred, len(distribution.events))
    dist_score = _candidate_score(distribution, quality, preferred, len(accumulation.events))
    candidates: list[dict[str, Any]] = []
    for state, score in ((accumulation, acc_score), (distribution, dist_score)):
        candidates.append(
            {
                "structure": state.structure,
                "direction": state.direction,
                "phase": state.phase,
                "current_event": state.events[-1]["event"] if state.events else "Trading Range",
                "events": state.events[-10:],
                "score_components": score,
                "structural_fit": round(score["total"] / 100, 3),
            }
        )
    candidates.sort(key=lambda item: item["structural_fit"], reverse=True)
    selected = candidates[0]
    score_gap = selected["structural_fit"] - candidates[1]["structural_fit"]
    range_start_time = pd.Timestamp(work["datetime"].iloc[range_start]).isoformat()
    return {
        "status": "active",
        "version": "2.0",
        "structure": selected["structure"],
        "direction": selected["direction"],
        "phase": selected["phase"],
        "current_event": selected["current_event"],
        "range": {
            "support": round(support, 6),
            "resistance": round(resistance, 6),
            "start_position": range_start,
            "start_timestamp": range_start_time,
            "age_bars": len(work) - range_start,
            "quality": quality,
        },
        "events": selected["events"],
        "structural_fit": selected["structural_fit"],
        "score_components": selected["score_components"],
        "alternatives": candidates,
        "ambiguous": score_gap < 0.08,
        "score_gap": round(score_gap, 3),
        "volume_reliable": True,
    }
