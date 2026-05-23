from __future__ import annotations

import random
from typing import Any, Dict


_FAKE_PCS_STATE: Dict[str, Dict[str, Any]] = {}


class FakePcsClient:
    def __init__(self, config: dict):
        self.config = config or {}
        self.name = str(self.config.get("name", "PCS-1"))
        self.scenario = str(self.config.get("fake_scenario", self.config.get("host", "normal"))).lower()
        self.connected = False
        state = _FAKE_PCS_STATE.setdefault(
            self.name,
            {
                "active_power": 0.0,
                "target_power": 0.0,
                "target_reactive_power": 0.0,
                "dc_breaker_closed": True,
                "online": True,
                "fault": False,
            },
        )
        self.state = state

    def connect(self) -> bool:
        if "offline" in self.scenario:
            return False
        self.connected = True
        return True

    def close(self):
        self.connected = False

    def get_active_power(self) -> float:
        if "deviation" in self.scenario:
            return float(self.state["active_power"])
        diff = float(self.state["target_power"]) - float(self.state["active_power"])
        self.state["active_power"] = float(self.state["active_power"]) + diff * 0.25 + random.uniform(-0.5, 0.5)
        return float(self.state["active_power"])

    def is_dc_breaker_open(self) -> bool:
        if "breaker_open" in self.scenario:
            return True
        return not bool(self.state["dc_breaker_closed"])

    def is_dc_breaker_closed(self) -> bool:
        if "breaker_open" in self.scenario:
            return False
        return bool(self.state["dc_breaker_closed"])

    def get_fault_status(self) -> int:
        return 1 if ("fault" in self.scenario or self.state.get("fault")) else 0

    def is_online(self) -> bool:
        return "offline" not in self.scenario

    def get_run_status(self):
        return "Running"

    def get_alarm_status(self):
        return 1 if "alarm" in self.scenario else 0

    def get_mode(self):
        return "Grid"

    def get_remote_local_status(self):
        return "Remote"

    def set_active_power(self, value: float) -> bool:
        self.state["target_power"] = float(value)
        return True

    def enable_reactive_power_remote(self) -> bool:
        self.state["reactive_power_remote_enable"] = 1
        return True

    def set_reactive_power(self, value: float) -> bool:
        self.enable_reactive_power_remote()
        self.state["target_reactive_power"] = float(value)
        return True

    def start_with_confirm(self) -> bool:
        return True

    def stop_with_confirm(self) -> bool:
        self.state["target_power"] = 0.0
        return True

    def stop(self) -> bool:
        return self.stop_with_confirm()

    def start(self) -> bool:
        return self.start_with_confirm()

    def reset_fault(self) -> bool:
        self.state["fault"] = False
        return True

    def hv_on(self) -> bool:
        self.state["dc_breaker_closed"] = True
        return True

    def hv_off(self) -> bool:
        self.state["dc_breaker_closed"] = False
        self.state["target_power"] = 0.0
        return True

    def close_dc_breaker(self) -> bool:
        self.state["dc_breaker_closed"] = True
        return True

    def open_dc_breaker(self) -> bool:
        self.state["dc_breaker_closed"] = False
        return True

    def precheck_control_ready(self, action: str = ""):
        return []

    def validate_config(self):
        return []

    def execute_command_with_debug(self, pcs_method_name: str):
        method = getattr(self, pcs_method_name, None)
        ok = method() if callable(method) else False
        return {"command": pcs_method_name, "success": ok, "error": "" if ok else "method missing", "debug_status": self.read_debug_status()}

    def read_debug_status(self):
        return {
            "fake": True,
            "name": self.name,
            "scenario": self.scenario,
            "active_power": self.get_active_power(),
            "target_power": self.state["target_power"],
            "target_reactive_power": self.state.get("target_reactive_power", 0.0),
            "dc_breaker_closed": self.is_dc_breaker_closed(),
            "fault_status": self.get_fault_status(),
        }
