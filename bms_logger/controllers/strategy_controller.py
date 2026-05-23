from __future__ import annotations

from typing import Any


class StrategyController:
    """Strategy facade for UI/API entrypoints."""

    def __init__(self, app: Any) -> None:
        self.app = app

    def reload(self) -> None:
        if hasattr(self.app, "load_strategy_config"):
            self.app.load_strategy_config()

    def save(self) -> None:
        if hasattr(self.app, "save_strategy_config"):
            self.app.save_strategy_config()

    def reset(self) -> None:
        if hasattr(self.app, "reset_strategy_config"):
            self.app.reset_strategy_config()
