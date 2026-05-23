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





class PointsMixin:
    def _point_category(self, key: str, value: Any, meta: Dict[str, Any]) -> str:
        text = f"{key} {meta.get('label', '')} {meta.get('description', '')}".lower()
        if any(token in text for token in ["alarm", "fault", "warning", "protect"]):
            return "Alarm/Fault"
        try:
            float(value)
            return "Numeric"
        except (TypeError, ValueError):
            return "Text"

    def refresh_driver_points(self, device_name: str) -> None:
        if not hasattr(self, "driver_points_table"):
            return

        self.driver_points_device_label.setText(f"Current device: {device_name or '-'}")
        snapshot = self.latest_snapshots.get(device_name, {}) if device_name else {}
        points = snapshot.get("points", {}) if isinstance(snapshot.get("points"), dict) else {}
        point_meta = snapshot.get("point_meta", {}) if isinstance(snapshot.get("point_meta"), dict) else {}

        filter_text = ""
        if hasattr(self, "driver_points_filter_edit"):
            filter_text = self.driver_points_filter_edit.text().strip().lower()

        category_filter = "All"
        if hasattr(self, "driver_points_category_combo"):
            category_filter = self.driver_points_category_combo.currentText()

        rows = []
        for key in sorted(points.keys()):
            meta = point_meta.get(key, {}) if isinstance(point_meta.get(key, {}), dict) else {}
            label = str(meta.get("label", key))
            unit = str(meta.get("unit", ""))
            address = str(meta.get("address", ""))
            value = points.get(key, "")
            category = self._point_category(key, value, meta)
            favorite_mark = "★" if key in self.favorite_points else ""

            if category_filter == "Favorites" and key not in self.favorite_points:
                continue
            if category_filter == "Alarm/Fault" and category != "Alarm/Fault":
                continue
            if category_filter == "Numeric" and category != "Numeric":
                continue

            haystack = f"{key} {label} {unit} {address} {value} {category}".lower()
            if filter_text and filter_text not in haystack:
                continue
            rows.append((favorite_mark, key, value, unit, address, label, category))

        self.driver_points_table.setRowCount(0)
        for row_values in rows:
            row = self.driver_points_table.rowCount()
            self.driver_points_table.insertRow(row)
            for col, value in enumerate(row_values):
                item = QTableWidgetItem(str(value))
                if col == 0 and value == "★":
                    item.setForeground(QColor("#f59e0b"))
                if col == 6 and value == "Alarm/Fault":
                    item.setForeground(QColor("#ef4444"))
                self.driver_points_table.setItem(row, col, item)

    def refresh_current_driver_points(self) -> None:
        if hasattr(self, "driver_points_device_combo"):
            self.refresh_driver_points(self.driver_points_device_combo.currentText())

    def on_driver_points_device_changed(self, device_name: str) -> None:
        if device_name:
            self.refresh_driver_points(device_name)

