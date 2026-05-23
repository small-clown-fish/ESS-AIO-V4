from __future__ import annotations

from typing import Any

from ..client_factory import create_bms_client


class DeviceController:
    """Device/BMS lifecycle facade.

    This first controller layer intentionally wraps the existing UI-owned state so behavior stays unchanged.
    Later phases can move add/remove/start/stop internals here without touching pages.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    def find_config(self, device_name: str) -> dict[str, Any] | None:
        return next((d for d in self.app.devices if d.get("name") == device_name), None)

    def create_bms_client(self, device_name: str):
        cfg = self.find_config(device_name)
        if not cfg:
            raise ValueError(f"Device config not found: {device_name}")
        return create_bms_client(cfg, fake_mode=getattr(self.app, "fake_mode", False))

    def configured_names(self) -> list[str]:
        return [str(d.get("name", "")) for d in self.app.devices if d.get("name")]

    def running_names(self) -> list[str]:
        return list(getattr(self.app, "device_workers", {}).keys())
