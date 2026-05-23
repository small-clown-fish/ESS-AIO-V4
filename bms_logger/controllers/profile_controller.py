from __future__ import annotations

from pathlib import Path
from typing import Any


class ProfileController:
    """Profile persistence facade used by UI and future API/CLI entrypoints."""

    def __init__(self, app: Any) -> None:
        self.app = app

    @property
    def current_dir(self) -> Path:
        return self.app.current_profile_dir

    def path(self, filename: str) -> Path:
        self.current_dir.mkdir(parents=True, exist_ok=True)
        return self.current_dir / filename

    def save_all(self) -> None:
        self.app.save_devices_to_default()
        self.app.save_site_config()
        self.app.save_runtime_config()
        if hasattr(self.app, "save_pcs_configs"):
            self.app.save_pcs_configs()
        if hasattr(self.app, "save_driver_config"):
            self.app.save_driver_config()
        if hasattr(self.app, "save_strategy_config"):
            self.app.save_strategy_config()

    def load_startup(self) -> None:
        self.app.auto_load_startup_configs()
