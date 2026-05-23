from __future__ import annotations

import json
import csv
from collections import deque
from pathlib import Path
from typing import Any, Dict

from PySide6.QtCharts import QChart, QLineSeries
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem, QInputDialog
from PySide6.QtGui import QColor





class ConfigMixin:
    def load_pcs_config(self) -> Dict[str, Any]:
        config_path = self.get_profile_path("pcs_config.json")
        multi_config_path = self.get_profile_path("pcs_configs.json")

        def _safe_log(message: str) -> None:
            if hasattr(self, "log_text"):
                self.log(message)
            else:
                print(message)

        if multi_config_path.exists():
            try:
                with open(multi_config_path, "r", encoding="utf-8") as f:
                    multi_data = json.load(f)
                if isinstance(multi_data, dict) and multi_data:
                    self.pcs_configs = multi_data
                    first_name = next(iter(multi_data.keys()))
                    self.current_pcs_name = first_name
                    cfg = dict(multi_data[first_name])
                    cfg["name"] = first_name
                    self.pcs_configs[first_name] = cfg
                    _safe_log(f"[INFO] Loaded PCS configs: {multi_config_path}")
                    return cfg
            except Exception as exc:
                _safe_log(f"[ERROR] Failed to load PCS configs: {exc}")

        if not config_path.exists():
            # First run should be a clean BMS-only state. We intentionally do not
            # auto-create an enabled/default PCS device, otherwise service checks
            # may keep trying to connect to a placeholder/unreachable IP.
            _safe_log(f"[INFO] No PCS config found yet. Start with no PCS: {config_path}")
            return {}

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data and "name" not in data:
                data["name"] = "PCS-1"
            _safe_log(f"[INFO] Loaded PCS config: {config_path}")
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            _safe_log(f"[ERROR] Failed to load PCS config: {exc}")
            return {}

    def reload_pcs_config(self) -> None:
        self.pcs_config = self.load_pcs_config()
        self.pcs_config_state_label.setText(
            "Loaded" if self.pcs_config.get("enabled", False) else "Disabled / Missing"
        )
        self.refresh_global_status_bar()
        self.log("[INFO] PCS config reloaded")
        self.save_site_config()

    def reload_alarm_map(self) -> None:
        self.alarm_parser.map_path = self.get_profile_path("alarm_map.json")
        self.alarm_parser.load()
        self.log("[INFO] Alarm map reloaded")
        self.control_log("[INFO] Alarm map reloaded")
        if self.current_alarm_device:
            self.refresh_alarms(self.current_alarm_device)

    def load_runtime_config(self) -> None:
        config_path = self.get_profile_path("runtime_config.json")

        if not config_path.exists():
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.heartbeat_interval = float(data.get("heartbeat_interval", self.heartbeat_interval))
            self.hv_step_timeout = float(data.get("hv_step_timeout", self.hv_step_timeout))
            self.hv_poll_interval = float(data.get("hv_poll_interval", self.hv_poll_interval))
            self.pcs_zero_power_threshold = float(data.get("pcs_zero_power_threshold", self.pcs_zero_power_threshold))
            self.charge_cutoff_max_cell_voltage = float(
                data.get("charge_cutoff_max_cell_voltage", self.charge_cutoff_max_cell_voltage)
            )
            self.discharge_cutoff_min_cell_voltage = float(
                data.get("discharge_cutoff_min_cell_voltage", self.discharge_cutoff_min_cell_voltage)
            )
            self.cutoff_mode = str(data.get("cutoff_mode", self.cutoff_mode))
            self.cutoff_trigger_confirm_count = int(
                data.get("cutoff_trigger_confirm_count", self.cutoff_trigger_confirm_count)
            )
            self.cutoff_recover_confirm_count = int(
                data.get("cutoff_recover_confirm_count", self.cutoff_recover_confirm_count)
            )
            self.alarm_history_window_before_minutes = int(
                data.get("alarm_history_window_before_minutes", self.alarm_history_window_before_minutes)
            )
            self.alarm_history_window_after_minutes = int(
                data.get("alarm_history_window_after_minutes", self.alarm_history_window_after_minutes)
            )
            self.power_tracking_enabled = bool(
                data.get("power_tracking_enabled", self.power_tracking_enabled)
            )
            self.power_tracking_tolerance_kw = float(
                data.get("power_tracking_tolerance_kw", self.power_tracking_tolerance_kw)
            )
            self.power_tracking_confirm_count = int(
                data.get("power_tracking_confirm_count", self.power_tracking_confirm_count)
            )
            self.pcs_fault_protection_mode = str(
                data.get("pcs_fault_protection_mode", self.pcs_fault_protection_mode)
            )
            self.pcs_fault_protection_enabled = self.pcs_fault_protection_mode != "Disabled"
            self.pcs_fault_confirm_count = int(
                data.get("pcs_fault_confirm_count", self.pcs_fault_confirm_count)
            )
            self.pcs_control_ui_enabled = bool(data.get("pcs_control_ui_enabled", self.pcs_control_ui_enabled))
            self.fake_mode = bool(data.get("fake_mode", self.fake_mode))
            self.worker_start_stagger_seconds = float(
                data.get("worker_start_stagger_seconds", self.worker_start_stagger_seconds)
            )
            self.ui_refresh_interval = float(
                data.get("ui_refresh_interval", self.ui_refresh_interval)
            )

            self.log("[INFO] Runtime config loaded")

        except Exception as exc:
            self.log(f"[ERROR] Failed to load runtime config: {exc}")

    def save_runtime_config(self) -> None:
        config_path = self.get_profile_path("runtime_config.json")

        data = {
            "heartbeat_interval": self.heartbeat_interval,
            "hv_step_timeout": self.hv_step_timeout,
            "hv_poll_interval": self.hv_poll_interval,
            "pcs_zero_power_threshold": self.pcs_zero_power_threshold,
            "charge_cutoff_max_cell_voltage": self.charge_cutoff_max_cell_voltage,
            "discharge_cutoff_min_cell_voltage": self.discharge_cutoff_min_cell_voltage,
            "cutoff_mode": self.cutoff_mode,
            "cutoff_trigger_confirm_count": self.cutoff_trigger_confirm_count,
            "cutoff_recover_confirm_count": self.cutoff_recover_confirm_count,
            "alarm_history_window_before_minutes": self.alarm_history_window_before_minutes,
            "alarm_history_window_after_minutes": self.alarm_history_window_after_minutes,
            "power_tracking_enabled": self.power_tracking_enabled,
            "power_tracking_tolerance_kw": self.power_tracking_tolerance_kw,
            "power_tracking_confirm_count": self.power_tracking_confirm_count,
            "pcs_fault_protection_mode": self.pcs_fault_protection_mode,
            "pcs_fault_confirm_count": self.pcs_fault_confirm_count,
            "pcs_control_ui_enabled": self.pcs_control_ui_enabled,
            "fake_mode": self.fake_mode,
            "worker_start_stagger_seconds": self.worker_start_stagger_seconds,
            "ui_refresh_interval": self.ui_refresh_interval,
        }

        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            self.log("[INFO] Runtime config saved")

        except Exception as exc:
            self.log(f"[ERROR] Failed to save runtime config: {exc}")

