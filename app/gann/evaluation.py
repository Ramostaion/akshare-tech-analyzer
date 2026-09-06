"""兼容入口：江恩历史验证已迁移到独立 backtest 模块。"""

from app.gann.backtest import evaluate_gann_history

__all__ = ["evaluate_gann_history"]
