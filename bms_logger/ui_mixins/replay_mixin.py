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





class ReplayMixin:
    def handle_replay_load_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load main CSV for replay", str(self.current_profile_dir), "CSV Files (*.csv)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                self.replay_rows = list(reader)
                fieldnames = list(reader.fieldnames or [])
            self.replay_index = 0
            self.replay_csv_path = path

            # Dynamic replay table: show the first useful columns instead of only fixed CATL fields.
            preferred = ["timestamp", "soc", "system_voltage", "system_current", "system_power", "max_cell_voltage", "min_cell_voltage"]
            replay_columns = [c for c in preferred if c in fieldnames]
            for c in fieldnames:
                if c not in replay_columns and c not in {"raw", "points", "point_meta"}:
                    replay_columns.append(c)
                if len(replay_columns) >= 12:
                    break
            self.replay_columns = replay_columns

            self.replay_table.setColumnCount(len(replay_columns) + 1)
            self.replay_table.setHorizontalHeaderLabels(["Index"] + replay_columns)
            self.replay_table.setRowCount(0)
            for idx, row_data in enumerate(self.replay_rows[:500]):
                row = self.replay_table.rowCount()
                self.replay_table.insertRow(row)
                values = [idx] + [row_data.get(col, "-") for col in replay_columns]
                for col, value in enumerate(values):
                    self.replay_table.setItem(row, col, QTableWidgetItem(str(value)))
            self.replay_info_label.setText(f"Replay: rows={len(self.replay_rows)}, columns={len(fieldnames)}, file={path}")
            self.log(f"[INFO] Replay CSV loaded: {path}, rows={len(self.replay_rows)}, columns={len(fieldnames)}")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to load replay CSV:\n{exc}")

    def _convert_replay_row_to_snapshot(self, row: Dict[str, str]) -> Dict[str, Any]:
        snapshot: Dict[str, Any] = {}
        points: Dict[str, Any] = {}
        for key, value in row.items():
            if value is None:
                continue
            text = str(value).strip()
            if text == "":
                continue
            try:
                converted = float(text) if "." in text else int(text)
            except Exception:
                converted = text
            snapshot[key] = converted
            if key not in {"timestamp", "device_name", "host", "port", "unit_id"}:
                points[key] = converted
        for key in ["soc", "system_voltage", "system_current", "system_power", "max_cell_voltage", "min_cell_voltage", "bms_heartbeat", "bms_status", "number_of_racks"]:
            snapshot.setdefault(key, 0)
            points.setdefault(key, snapshot.get(key, 0))
        for i in range(0x20):
            snapshot.setdefault(f"alarm_0x{i:04x}", 0)
            points.setdefault(f"alarm_0x{i:04x}", snapshot.get(f"alarm_0x{i:04x}", 0))
        snapshot["points"] = points
        snapshot["point_meta"] = {key: {"label": key, "unit": "", "address": ""} for key in points.keys()}
        snapshot.setdefault("driver_key", "csv_replay")
        snapshot.setdefault("device_type", "BMS")
        return snapshot

    def handle_replay_next_row(self) -> None:
        rows = getattr(self, "replay_rows", [])
        if not rows:
            QMessageBox.information(self, "Info", "No replay CSV loaded.")
            return
        if getattr(self, "replay_index", 0) >= len(rows):
            self.replay_index = 0
        row = rows[self.replay_index]
        self.replay_index += 1
        device_name = self.replay_device_name_edit.text().strip() if hasattr(self, "replay_device_name_edit") else "Replay-BMS"
        if not device_name:
            device_name = "Replay-BMS"
        snapshot = self._convert_replay_row_to_snapshot(row)
        self.on_data_received(device_name, snapshot)
        if hasattr(self, "replay_info_label"):
            self.replay_info_label.setText(f"Replay: {self.replay_index}/{len(rows)} rows, device={device_name}")

    def handle_replay_start(self) -> None:
        if not getattr(self, "replay_rows", []):
            QMessageBox.information(self, "Info", "No replay CSV loaded.")
            return
        if not hasattr(self, "replay_timer") or self.replay_timer is None:
            self.replay_timer = QTimer(self)
            self.replay_timer.timeout.connect(self.handle_replay_next_row)
        self.replay_timer.start(int(self.replay_interval_spin.value()))
        self.log("[INFO] Replay started")

    def handle_replay_stop(self) -> None:
        timer = getattr(self, "replay_timer", None)
        if timer is not None:
            timer.stop()
        self.log("[INFO] Replay stopped")

    # ========================
    # v2.2 Strategy Engine
    # ========================
