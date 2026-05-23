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





class DriverConfigMixin:
    def get_driver_config_path(self) -> Path:
        return self.get_profile_path("driver_config.json")

    def load_driver_config(self) -> None:
        path = self.get_driver_config_path()
        if not path.exists():
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.bms_driver_key = str(data.get("bms_driver", getattr(self, "bms_driver_key", "catl_v17_bms")))
            self.pcs_driver_key = str(data.get("pcs_driver", getattr(self, "pcs_driver_key", "generic_modbus_pcs")))

            for dev in self.devices:
                dev.setdefault("driver", self.bms_driver_key)
            for cfg in self.pcs_configs.values():
                cfg.setdefault("driver", self.pcs_driver_key)

            self.log(f"[INFO] Loaded driver config: {path}")
        except Exception as exc:
            self.log(f"[ERROR] Failed to load driver config: {exc}")

    def save_driver_config(self) -> None:
        path = self.get_driver_config_path()
        data = {
            "bms_driver": getattr(self, "bms_driver_key", "catl_v17_bms"),
            "pcs_driver": getattr(self, "pcs_driver_key", "generic_modbus_pcs"),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.log(f"[INFO] Saved driver config: {path}")

    def refresh_driver_view(self) -> None:
        if not hasattr(self, "bms_driver_combo"):
            return
        try:
            from .drivers import list_bms_drivers, list_pcs_drivers

            current_bms = getattr(self, "bms_driver_key", "catl_v17_bms")
            current_pcs = getattr(self, "pcs_driver_key", "generic_modbus_pcs")

            self.bms_driver_combo.blockSignals(True)
            self.pcs_driver_combo.blockSignals(True)
            self.bms_driver_combo.clear()
            self.pcs_driver_combo.clear()

            for info in list_bms_drivers():
                self.bms_driver_combo.addItem(f"{info.name} ({info.key})", info.key)
            for info in list_pcs_drivers():
                self.pcs_driver_combo.addItem(f"{info.name} ({info.key})", info.key)

            idx = self.bms_driver_combo.findData(current_bms)
            if idx >= 0:
                self.bms_driver_combo.setCurrentIndex(idx)
            idx = self.pcs_driver_combo.findData(current_pcs)
            if idx >= 0:
                self.pcs_driver_combo.setCurrentIndex(idx)

            self.bms_driver_combo.blockSignals(False)
            self.pcs_driver_combo.blockSignals(False)

            if hasattr(self, "template_info_label"):
                self.template_info_label.setText(
                    f"Active drivers: BMS={current_bms}, PCS={current_pcs}. "
                    "Point tables are stored per Profile."
                )
        except Exception as exc:
            self.log(f"[ERROR] Refresh driver view failed: {exc}")

    def apply_driver_binding(self) -> None:
        if not hasattr(self, "bms_driver_combo"):
            return
        bms_key = self.bms_driver_combo.currentData() or self.bms_driver_combo.currentText()
        pcs_key = self.pcs_driver_combo.currentData() or self.pcs_driver_combo.currentText()
        self.bms_driver_key = str(bms_key)
        self.pcs_driver_key = str(pcs_key)

        for dev in self.devices:
            dev["driver"] = self.bms_driver_key
        for cfg in self.pcs_configs.values():
            cfg["driver"] = self.pcs_driver_key
        if hasattr(self, "pcs_config"):
            self.pcs_config["driver"] = self.pcs_driver_key

        self.save_driver_config()
        try:
            self.save_devices_to_default()
            self.save_pcs_config()
        except Exception as exc:
            self.log(f"[WARN] Saving driver binding to device configs failed: {exc}")

        self.refresh_driver_view()
        self.log(f"[INFO] Driver binding applied: BMS={self.bms_driver_key}, PCS={self.pcs_driver_key}")
