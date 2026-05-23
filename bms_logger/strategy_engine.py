from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_STRATEGY: Dict[str, Any] = {
    "name": "Default Safety Strategy",
    "version": "1.0",
    "enabled": True,
    "description": "Profile-level strategy overrides for cutoff, derating, tracking and protection.",
    "overrides": {
        "charge_cutoff_max_cell_voltage": 3650.0,
        "discharge_cutoff_min_cell_voltage": 2500.0,
        "derating_margin_mv": 50.0,
        "derating_power_kw": 10.0,
        "cutoff_mode": "Alarm Only",
        "pcs_fault_protection_mode": "Alarm Only",
        "power_tracking_tolerance_kw": 5.0,
    },
    "fake_tests": [
        {"name": "Normal", "bms_scenario": "normal", "pcs_scenario": "normal"},
        {"name": "High Voltage Derating/Cutoff", "bms_scenario": "high_voltage", "pcs_scenario": "normal"},
        {"name": "Low Voltage Discharge Cutoff", "bms_scenario": "low_voltage", "pcs_scenario": "normal"},
        {"name": "PCS Fault", "bms_scenario": "normal", "pcs_scenario": "fault"},
        {"name": "PCS Offline", "bms_scenario": "normal", "pcs_scenario": "offline"},
        {"name": "PCS Power Deviation", "bms_scenario": "normal", "pcs_scenario": "deviation"}
    ]
}


class StrategyEngine:
    """Profile-scoped strategy configuration helper.

    v2.2 is intentionally conservative: the engine provides config-driven
    parameter overrides and fake test definitions, while the existing Service
    keeps executing the proven control flow.
    """

    def __init__(self, profile_dir: Path) -> None:
        self.profile_dir = Path(profile_dir)
        self.strategy: Dict[str, Any] = dict(DEFAULT_STRATEGY)
        self.load()

    def set_profile_dir(self, profile_dir: Path) -> None:
        self.profile_dir = Path(profile_dir)
        self.load()

    @property
    def strategy_path(self) -> Path:
        return self.profile_dir / "strategy.json"

    def ensure_default(self) -> None:
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        if not self.strategy_path.exists():
            self.save(DEFAULT_STRATEGY)

    def load(self) -> Dict[str, Any]:
        self.ensure_default()
        try:
            with open(self.strategy_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self.strategy = self._merge_defaults(data)
            else:
                self.strategy = dict(DEFAULT_STRATEGY)
        except Exception:
            self.strategy = dict(DEFAULT_STRATEGY)
        return self.strategy

    def save(self, strategy: Dict[str, Any] | None = None) -> None:
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        if strategy is not None:
            self.strategy = self._merge_defaults(strategy)
        with open(self.strategy_path, "w", encoding="utf-8") as f:
            json.dump(self.strategy, f, ensure_ascii=False, indent=2)

    def _merge_defaults(self, data: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(DEFAULT_STRATEGY)
        merged.update({k: v for k, v in data.items() if k not in ["overrides", "fake_tests"]})
        overrides = dict(DEFAULT_STRATEGY.get("overrides", {}))
        overrides.update(data.get("overrides", {}) if isinstance(data.get("overrides"), dict) else {})
        merged["overrides"] = overrides
        fake_tests = data.get("fake_tests")
        merged["fake_tests"] = fake_tests if isinstance(fake_tests, list) else list(DEFAULT_STRATEGY["fake_tests"])
        return merged

    def is_enabled(self) -> bool:
        return bool(self.strategy.get("enabled", True))

    def get(self, key: str, default: Any) -> Any:
        if not self.is_enabled():
            return default
        overrides = self.strategy.get("overrides", {})
        if not isinstance(overrides, dict):
            return default
        return overrides.get(key, default)

    def get_float(self, key: str, default: float) -> float:
        try:
            return float(self.get(key, default))
        except Exception:
            return float(default)

    def get_str(self, key: str, default: str) -> str:
        try:
            return str(self.get(key, default))
        except Exception:
            return str(default)

    def fake_tests(self) -> List[Dict[str, Any]]:
        tests = self.strategy.get("fake_tests", [])
        return tests if isinstance(tests, list) else []

    def validate(self, strategy: Dict[str, Any] | None = None) -> List[str]:
        data = strategy if strategy is not None else self.strategy
        errors: List[str] = []
        if not isinstance(data, dict):
            return ["Strategy root must be a JSON object."]
        if not isinstance(data.get("overrides", {}), dict):
            errors.append("overrides must be an object.")
        allowed_cutoff_modes = {"Disabled", "Alarm Only", "Stop PCS", "HV Off"}
        cutoff_mode = str(data.get("overrides", {}).get("cutoff_mode", "Alarm Only"))
        if cutoff_mode not in allowed_cutoff_modes:
            errors.append(f"cutoff_mode must be one of {sorted(allowed_cutoff_modes)}")
        if not isinstance(data.get("fake_tests", []), list):
            errors.append("fake_tests must be a list.")
        return errors
