"""候选浪的条件目标区与结构失效位。"""

from __future__ import annotations

from app.wave.pivots import WavePivot


def _zone(anchor: float, move: float, direction: int, ratios: tuple[float, float]) -> list[float]:
    values = [anchor + direction * move * ratio for ratio in ratios]
    return [round(value, 4) for value in sorted(values)]


def _invalidation_rule(direction: int, subject: str) -> str:
    verb = "跌破" if direction > 0 else "升破"
    return f"收盘{verb}该结构边界后，{subject}失效并重新计浪"


def _confirmation_rule(direction: int, subject: str) -> str:
    verb = "突破" if direction > 0 else "跌破"
    return f"收盘{verb}该确认位后，才把{subject}视为已确认"


def project_candidate(
    pattern: str,
    pivots: list[WavePivot],
    direction: int,
) -> dict[str, object]:
    """按结构状态给出条件区间；横轴与到达时间不属于计算结果。"""
    if len(pivots) < 3:
        return {
            "primary_zone": [],
            "invalidation": None,
            "status": "insufficient",
            "path_direction": "neutral",
        }
    prices = [item.price for item in pivots]
    path_direction = "up" if direction > 0 else "down"

    if pattern == "unfinished_impulse":
        base_move = abs(prices[1] - prices[0])
        anchor = prices[-1]
        return {
            "primary_zone": _zone(anchor, base_move, direction, (0.618, 1.0)),
            "invalidation": round(anchor, 4),
            "status": "developing",
            "path_direction": path_direction,
            "confirmation": round(prices[-2], 4),
            "confirmation_label": "第五浪延续确认位",
            "confirmation_rule": _confirmation_rule(direction, "第五浪延续"),
            "target_label": "第五浪延续目标观察区",
            "invalidation_label": "第五浪候选失效位",
            "invalidation_rule": _invalidation_rule(direction, "第五浪延续候选"),
        }

    if pattern == "unfinished_abc":
        first_leg = abs(prices[1] - prices[0])
        anchor = prices[-1]
        return {
            "primary_zone": _zone(anchor, first_leg, direction, (0.618, 1.0)),
            "invalidation": round(prices[0], 4),
            "status": "developing",
            "path_direction": path_direction,
            "confirmation": round(prices[1], 4),
            "confirmation_label": "C 浪延续确认位",
            "confirmation_rule": _confirmation_rule(direction, "C 浪延续"),
            "target_label": "C 浪条件目标观察区",
            "invalidation_label": "C 浪候选失效位",
            "invalidation_rule": _invalidation_rule(direction, "当前 ABC 候选"),
        }

    # 完整五浪或 ABC 的最后一个 Pivot 已经右侧确认，不能再把它描述成
    # “当前浪仍在延续”。此处只展示下一阶段的反向观察区。
    anchor = prices[-1]
    reverse_direction = -direction
    structure_move = abs(anchor - prices[0])
    structure_move = structure_move or abs(prices[1] - prices[0])
    structure_name = "五浪" if pattern == "impulse" else "ABC"
    target_zones = [
        {
            "label": f"{structure_name}完成后的第一反向观察区（23.6%–38.2%）",
            "zone": _zone(anchor, structure_move, reverse_direction, (0.236, 0.382)),
        },
        {
            "label": f"{structure_name}完成后的第二反向观察区（50.0%–61.8%）",
            "zone": _zone(anchor, structure_move, reverse_direction, (0.5, 0.618)),
        },
        {
            "label": f"{structure_name}完成后的深度反向观察区（61.8%–78.6%）",
            "zone": _zone(anchor, structure_move, reverse_direction, (0.618, 0.786)),
        },
        {
            "label": f"{structure_name}完成后的完全回撤观察区（78.6%–100%）",
            "zone": _zone(anchor, structure_move, reverse_direction, (0.786, 1.0)),
        },
    ]
    return {
        "primary_zone": target_zones[0]["zone"],
        "target_zones": target_zones,
        "zone_stage": 1,
        "invalidation": round(anchor, 4),
        "status": "completed",
        "path_direction": "up" if reverse_direction > 0 else "down",
        "confirmation": round(prices[-2], 4),
        "confirmation_label": f"{structure_name}完成后的反向确认位",
        "confirmation_rule": _confirmation_rule(reverse_direction, "下一阶段反向路径"),
        "target_label": target_zones[0]["label"],
        "invalidation_label": "反向情景失效位",
        "invalidation_rule": _invalidation_rule(reverse_direction, "反向情景"),
    }
