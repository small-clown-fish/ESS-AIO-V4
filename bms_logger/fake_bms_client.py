from __future__ import annotations

import random
from typing import Any, Dict


class FakeBmsClient:
    def __init__(self, config: Dict[str, Any] | None = None):
        self.config = config or {}
        self.connected = False
        self.heartbeat = 0
        self.scenario = str(self.config.get("fake_scenario", self.config.get("host", "normal"))).lower()
        self.driver_key = "fake_bms"

    def connect(self):
        if "offline" in self.scenario:
            return False
        self.connected = True
        return True

    def close(self):
        self.connected = False

    def _voltages(self):
        if "high" in self.scenario or "over" in self.scenario:
            return 3680, 3200
        if "low" in self.scenario:
            return 3300, 2450
        return random.uniform(3450, 3580), random.uniform(3150, 3350)

    def read_telemetry_snapshot(self):
        max_v, min_v = self._voltages()
        self.heartbeat = (self.heartbeat + 1) % 256
        alarms = {f"alarm_0x{i:04x}": 0 for i in range(0x20)}
        if "alarm" in self.scenario:
            alarms["alarm_0x0010"] = 1
        return {
            **alarms,
            "bms_heartbeat": self.heartbeat,
            "bms_power_on": 1,
            "bms_status": 1 if "fault" not in self.scenario else 5,
            "number_of_racks": 8,
            "soc": round(random.uniform(35, 85), 1),
            "soh": 99.0,
            "system_voltage": round(random.uniform(650, 760), 1),
            "system_current": round(random.uniform(-80, 80), 1),
            "system_power": round(random.uniform(-50, 50), 1),
            "max_cell_voltage": round(max_v, 1),
            "min_cell_voltage": round(min_v, 1),
            "avg_cell_voltage": round((max_v + min_v) / 2, 1),
            "max_cell_temperature": round(random.uniform(25, 36), 1),
            "min_cell_temperature": round(random.uniform(18, 25), 1),
            "avg_cell_temperature": round(random.uniform(22, 30), 1),
            "max_charge_current_allowed": 120,
            "max_discharge_current_allowed": 120,
            "max_charge_power_allowed": 100,
            "max_discharge_power_allowed": 100,
        }

    def read_bms_status(self):
        return 1

    def read_bms_power_on(self):
        return 1

    def clear_fault(self) -> bool:
        return True

    def write_heartbeat(self, value: int) -> bool:
        self.heartbeat = int(value) % 256
        return True

    def write_ems_cmd(self, value: int) -> bool:
        return True

    def write_ems_cmd_power_on(self):
        return True

    def write_ems_cmd_stay(self):
        return True

    def write_ems_cmd_power_off(self):
        return True

    def get_point_catalog(self):
        units = {
            "soc": "%", "soh": "%", "system_voltage": "V", "system_current": "A",
            "system_power": "kW", "max_cell_voltage": "mV", "min_cell_voltage": "mV",
            "avg_cell_voltage": "mV", "max_cell_temperature": "°C",
            "min_cell_temperature": "°C", "avg_cell_temperature": "°C",
        }
        keys = [
            "bms_heartbeat", "bms_power_on", "bms_status", "number_of_racks",
            "soc", "soh", "system_voltage", "system_current", "system_power",
            "max_cell_voltage", "min_cell_voltage", "avg_cell_voltage",
            "max_cell_temperature", "min_cell_temperature", "avg_cell_temperature",
            "max_charge_current_allowed", "max_discharge_current_allowed",
            "max_charge_power_allowed", "max_discharge_power_allowed",
        ]
        catalog = {key: {"label": key.replace("_", " ").title(), "unit": units.get(key, "")} for key in keys}
        for addr in range(0x20):
            key = f"alarm_0x{addr:04x}"
            catalog[key] = {"label": key, "unit": "bitfield"}
        return catalog

    def read_debug_status(self):
        return {
            "fake": True,
            "scenario": self.scenario,
            "bms_status_0x0302": self.read_bms_status(),
            "bms_power_on_0x0301": self.read_bms_power_on(),
            "bms_heartbeat_0x0300": self.heartbeat,
        }

    def read_software_version(self):
        return {
            "MBMU Software": "FAKE-MBMU-SW-V1.0",
            "MBMU Hardware": "FAKE-MBMU-HW-V1.0",
            "ETH Software": "FAKE-ETH-SW-V1.0",
            "ETH Hardware": "FAKE-ETH-HW-V1.0",
        }
