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





class CurvesMixin:
    def refresh_curves(self, device_name: str) -> None:
        self.current_curve_device = device_name
        self.curve_device_label.setText(f"Current device: {device_name}")

        self._fill_series(self.soc_series, self.series_buffers[device_name]["soc"], self.soc_chart)
        self._fill_series(
            self.voltage_series,
            self.series_buffers[device_name]["system_voltage"],
            self.voltage_chart,
        )
        self._fill_series(
            self.current_series,
            self.series_buffers[device_name]["system_current"],
            self.current_chart,
        )
        self._fill_series(
            self.online_series,
            self.series_buffers[device_name]["online"],
            self.online_chart,
        )

        self.refresh_dynamic_point_options(device_name)
        self.refresh_selected_dynamic_points_list()
        self.refresh_dynamic_chart(device_name)


    # ========================
    # v3.0 phase 3: dynamic driver point curves
    # ========================
    def refresh_dynamic_point_options(self, device_name: str) -> None:
        if not hasattr(self, "dynamic_point_combo"):
            return

        current = self.dynamic_point_combo.currentText()
        point_keys = sorted(self.dynamic_point_buffers.get(device_name, {}).keys())

        # Prefer current snapshot keys so new points appear before enough history exists.
        snapshot = self.latest_snapshots.get(device_name, {})
        points = snapshot.get("points", {}) if isinstance(snapshot.get("points"), dict) else {}
        for key, value in points.items():
            try:
                float(value)
            except (TypeError, ValueError):
                continue
            if key not in point_keys:
                point_keys.append(key)

        self.dynamic_point_combo.blockSignals(True)
        self.dynamic_point_combo.clear()
        self.dynamic_point_combo.addItems(sorted(point_keys))
        if current and self.dynamic_point_combo.findText(current) >= 0:
            self.dynamic_point_combo.setCurrentText(current)
        self.dynamic_point_combo.blockSignals(False)

    def add_dynamic_point_from_combo(self) -> None:
        if not hasattr(self, "dynamic_point_combo"):
            return

        point_key = self.dynamic_point_combo.currentText().strip()
        if not point_key:
            return

        if point_key not in self.selected_dynamic_points:
            if len(self.selected_dynamic_points) >= len(getattr(self, "dynamic_point_series", [])):
                QMessageBox.information(self, "Info", "You can plot up to 4 dynamic points at once.")
                return
            self.selected_dynamic_points.append(point_key)

        self.refresh_selected_dynamic_points_list()
        self.refresh_dynamic_chart(self.current_curve_device or "")

    def add_selected_driver_point_to_curve(self) -> None:
        if not hasattr(self, "driver_points_table"):
            return
        row = self.driver_points_table.currentRow()
        if row < 0:
            return
        item = self.driver_points_table.item(row, 1)
        if item is None:
            return
        point_key = item.text().strip()
        if not point_key:
            return
        if point_key not in self.selected_dynamic_points:
            if len(self.selected_dynamic_points) >= len(getattr(self, "dynamic_point_series", [])):
                QMessageBox.information(self, "Info", "You can plot up to 4 dynamic points at once.")
                return
            self.selected_dynamic_points.append(point_key)
        self.refresh_selected_dynamic_points_list()
        self.refresh_dynamic_point_options(self.current_curve_device or self.driver_points_device_combo.currentText())
        self.refresh_dynamic_chart(self.current_curve_device or self.driver_points_device_combo.currentText())

    def clear_dynamic_points(self) -> None:
        self.selected_dynamic_points.clear()
        self.refresh_selected_dynamic_points_list()
        self.refresh_dynamic_chart(self.current_curve_device or "")

    def refresh_selected_dynamic_points_list(self) -> None:
        if not hasattr(self, "dynamic_selected_points_list"):
            return
        self.dynamic_selected_points_list.clear()
        for key in self.selected_dynamic_points:
            self.dynamic_selected_points_list.addItem(key)

    def refresh_dynamic_chart(self, device_name: str) -> None:
        if not hasattr(self, "dynamic_point_series"):
            return

        buffers = self.dynamic_point_buffers.get(device_name, {})
        all_values = []
        all_x = []
        for idx, series in enumerate(self.dynamic_point_series):
            series.clear()
            if idx >= len(self.selected_dynamic_points):
                series.setName(f"Point {idx + 1}")
                continue
            point_key = self.selected_dynamic_points[idx]
            series.setName(point_key)
            data = list(buffers.get(point_key, []))
            for x, y in data:
                series.append(x, y)
                all_x.append(x)
                all_values.append(y)

        if not all_x or not all_values:
            return

        min_x, max_x = min(all_x), max(all_x)
        min_y, max_y = min(all_values), max(all_values)
        if min_y == max_y:
            min_y -= 1
            max_y += 1
        self.dynamic_axis_x.setRange(min_x, max(max_x, min_x + 10))
        self.dynamic_axis_y.setRange(min_y, max_y)

    def toggle_selected_driver_point_favorite(self) -> None:
        if not hasattr(self, "driver_points_table"):
            return
        row = self.driver_points_table.currentRow()
        if row < 0:
            return
        item = self.driver_points_table.item(row, 1)
        if item is None:
            return
        point_key = item.text().strip()
        if not point_key:
            return
        if point_key in self.favorite_points:
            self.favorite_points.remove(point_key)
        else:
            self.favorite_points.add(point_key)
        self.refresh_current_driver_points()


    # ========================
    # v3.7: CAN decoded signal curves / unified timeline
    # ========================
    def rebuild_can_signal_buffers(self, records=None) -> None:
        """Build curve buffers from decoded CAN records.

        Keys are stable and human readable: CAN:<MessageOrId>.<Signal>.
        X axis is the CAN log timestamp in seconds, preserving the imported
        capture/ASC time base.
        """
        if records is None:
            records = getattr(self, "can_records", [])

        self.can_signal_buffers.clear()
        for rec in records or []:
            decoded = getattr(rec, "decoded", "") or ""
            if not decoded:
                continue
            source = getattr(rec, "message_name", "") or getattr(rec, "can_id", "CAN")
            for signal_name, value in self._parse_decoded_signal_values(decoded).items():
                key = f"CAN:{source}.{signal_name}"
                try:
                    ts = float(getattr(rec, "timestamp", 0.0))
                    self.can_signal_buffers[key].append((ts, float(value)))
                except Exception:
                    continue

        self.refresh_can_signal_options()
        self.refresh_selected_can_signals_list()
        self.refresh_can_signal_chart()

    def _parse_decoded_signal_values(self, decoded: str) -> dict[str, float]:
        values: dict[str, float] = {}
        for part in str(decoded).split(";"):
            part = part.strip()
            if not part or "=" not in part:
                continue
            name, raw_value = part.split("=", 1)
            name = name.strip()
            raw_value = raw_value.strip()
            # Accept forms like 56.3%, -12.5A, 1.2e3V.
            import re
            m = re.match(r"^([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)", raw_value)
            if not name or not m:
                continue
            try:
                values[name] = float(m.group(1))
            except Exception:
                continue
        return values

    def refresh_can_signal_options(self) -> None:
        if not hasattr(self, "can_signal_combo"):
            return
        current = self.can_signal_combo.currentText()
        keys = sorted(self.can_signal_buffers.keys())
        self.can_signal_combo.blockSignals(True)
        self.can_signal_combo.clear()
        self.can_signal_combo.addItems(keys)
        if current and self.can_signal_combo.findText(current) >= 0:
            self.can_signal_combo.setCurrentText(current)
        self.can_signal_combo.blockSignals(False)

    def add_can_signal_from_combo(self) -> None:
        if not hasattr(self, "can_signal_combo"):
            return
        signal_key = self.can_signal_combo.currentText().strip()
        if not signal_key:
            return
        if signal_key not in self.selected_can_signals:
            if len(self.selected_can_signals) >= len(getattr(self, "can_signal_series", [])):
                QMessageBox.information(self, "Info", "You can plot up to 4 CAN signals at once.")
                return
            self.selected_can_signals.append(signal_key)
        self.refresh_selected_can_signals_list()
        self.refresh_can_signal_chart()

    def clear_can_signals(self) -> None:
        self.selected_can_signals.clear()
        self.refresh_selected_can_signals_list()
        self.refresh_can_signal_chart()

    def refresh_selected_can_signals_list(self) -> None:
        if not hasattr(self, "can_selected_signals_list"):
            return
        self.can_selected_signals_list.clear()
        for key in self.selected_can_signals:
            self.can_selected_signals_list.addItem(key)

    def refresh_can_signal_chart(self) -> None:
        if not hasattr(self, "can_signal_series"):
            return

        all_x = []
        all_y = []
        for idx, series in enumerate(self.can_signal_series):
            series.clear()
            if idx >= len(self.selected_can_signals):
                series.setName(f"CAN Signal {idx + 1}")
                continue
            key = self.selected_can_signals[idx]
            series.setName(key.replace("CAN:", ""))
            for x, y in self.can_signal_buffers.get(key, []):
                series.append(x, y)
                all_x.append(x)
                all_y.append(y)

        if not all_x or not all_y:
            return

        min_x, max_x = min(all_x), max(all_x)
        min_y, max_y = min(all_y), max(all_y)
        if min_x == max_x:
            max_x = min_x + 1
        if min_y == max_y:
            min_y -= 1
            max_y += 1
        self.can_signal_axis_x.setRange(min_x, max_x)
        self.can_signal_axis_y.setRange(min_y, max_y)

    def export_can_signals_csv(self) -> None:
        if not getattr(self, "can_signal_buffers", None):
            QMessageBox.information(self, "CAN Signals", "No decoded CAN signals to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export CAN signals CSV",
            str(self.get_profile_path("can_decoded_signals.csv") if hasattr(self, "get_profile_path") else Path.cwd() / "can_decoded_signals.csv"),
            "CSV Files (*.csv)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["signal", "timestamp", "value"])
                for key in sorted(self.can_signal_buffers.keys()):
                    for ts, value in self.can_signal_buffers[key]:
                        writer.writerow([key, ts, value])
            self.log(f"[CAN] Exported decoded signals: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "CAN Signals", f"Failed to export CAN signals:\n{exc}")

    def _fill_series(self, series: QLineSeries, data: deque, chart: QChart) -> None:
        series.clear()

        if not data:
            return

        min_x = data[0][0]
        max_x = data[-1][0]
        min_y = min(v for _, v in data)
        max_y = max(v for _, v in data)

        if min_y == max_y:
            min_y -= 1
            max_y += 1

        for x, y in data:
            series.append(x, y)

        axis_x = chart.axes(Qt.Horizontal)[0]
        axis_y = chart.axes(Qt.Vertical)[0]
        axis_x.setRange(min_x, max(max_x, min_x + 10))
        axis_y.setRange(min_y, max_y)

    def handle_load_history_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load history CSV",
            str(Path.cwd()),
            "CSV Files (*.csv)",
        )

        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                self.history_rows = list(reader)
                self.history_csv_path = path

            self._plot_history_rows(self.history_rows)
            first_ts = self.history_rows[0].get("timestamp", "-") if self.history_rows else "-"
            last_ts = self.history_rows[-1].get("timestamp", "-") if self.history_rows else "-"

            self.log(
                f"[INFO] Loaded history CSV: {path}, "
                f"rows={len(self.history_rows)}, first={first_ts}, last={last_ts}"
            )

        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to load history CSV:\n{exc}")
            self.log(f"[ERROR] Failed to load history CSV: {exc}")

    def _parse_history_time(self, text: str):
        from datetime import datetime

        text = text.strip()
        if not text:
            return None

        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(text, fmt)
            except Exception:
                pass

        raise ValueError(f"Invalid time format: {text}")

    def _plot_history_rows(self, rows: list[dict[str, str]]) -> None:
        device_name = "History"

        self.series_buffers[device_name]["soc"].clear()
        self.series_buffers[device_name]["system_voltage"].clear()
        self.series_buffers[device_name]["system_current"].clear()
        self.series_buffers[device_name]["online"].clear()
        self.dynamic_point_buffers[device_name].clear()

        def _float_value(row: dict[str, str], key: str, default: float = 0.0) -> float:
            try:
                return float(row.get(key, default) or default)
            except Exception:
                return default

        for idx, row in enumerate(rows):
            self.series_buffers[device_name]["soc"].append(
                (idx, _float_value(row, "soc"))
            )
            self.series_buffers[device_name]["system_voltage"].append(
                (idx, _float_value(row, "system_voltage"))
            )
            self.series_buffers[device_name]["system_current"].append(
                (idx, _float_value(row, "system_current"))
            )
            self.series_buffers[device_name]["online"].append((idx, 1.0))

            for key, value in row.items():
                if key in {"timestamp", "device_name", "host", "port", "unit_id"}:
                    continue
                try:
                    numeric_value = float(value)
                except (TypeError, ValueError):
                    continue
                self.dynamic_point_buffers[device_name][key].append((idx, numeric_value))

        if self.curve_device_combo.findText(device_name) < 0:
            self.curve_device_combo.addItem(device_name)

        self.current_curve_device = device_name
        self.curve_device_combo.setCurrentText(device_name)
        self.curve_device_label.setText(f"Current device: {device_name}")

        self.refresh_curves(device_name)
        self.refresh_dynamic_point_options(device_name)
        self.refresh_dynamic_chart(device_name)
        if hasattr(self, "history_info_label"):
            first_ts = rows[0].get("timestamp", "-") if rows else "-"
            last_ts = rows[-1].get("timestamp", "-") if rows else "-"
            self.history_info_label.setText(
                f"History: rows={len(rows)}, first={first_ts}, last={last_ts}"
            )

    def apply_history_time_filter(self) -> None:
        if not self.history_rows:
            QMessageBox.information(self, "Info", "No history CSV loaded.")
            return

        try:
            start_dt = self._parse_history_time(self.history_start_edit.text())
            end_dt = self._parse_history_time(self.history_end_edit.text())
        except Exception as exc:
            QMessageBox.warning(self, "Invalid Time", str(exc))
            return

        from datetime import datetime

        filtered = []

        for row in self.history_rows:
            ts = row.get("timestamp", "").strip()
            if not ts:
                continue

            try:
                row_dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            except Exception:
                continue

            if start_dt is not None and row_dt < start_dt:
                continue

            if end_dt is not None and row_dt > end_dt:
                continue

            filtered.append(row)

        if not filtered:
            QMessageBox.information(self, "Info", "No data in selected time range.")
            return

        self._plot_history_rows(filtered)
        self.log(
            f"[INFO] Applied history time filter: rows={len(filtered)}, "
            f"start={self.history_start_edit.text()}, end={self.history_end_edit.text()}"
        )

    def handle_clear_history(self) -> None:
        device_name = "History"

        self.history_rows = []
        self.history_csv_path = ""

        if device_name in self.series_buffers:
            self.series_buffers[device_name]["soc"].clear()
            self.series_buffers[device_name]["system_voltage"].clear()
            self.series_buffers[device_name]["system_current"].clear()
            self.series_buffers[device_name]["online"].clear()

        index = self.curve_device_combo.findText(device_name)
        if index >= 0:
            self.curve_device_combo.removeItem(index)

        if self.devices:
            first_device = self.devices[0]["name"]
            self.current_curve_device = first_device
            self.curve_device_combo.setCurrentText(first_device)
            self.refresh_curves(first_device)
            self.curve_device_label.setText(f"Current device: {first_device}")
        else:
            self.current_curve_device = None
            self.curve_device_label.setText("Current device: -")

            self.soc_series.clear()
            self.voltage_series.clear()
            self.current_series.clear()
            self.online_series.clear()

        if hasattr(self, "history_info_label"):
            self.history_info_label.setText("History: -")

        if hasattr(self, "history_start_edit"):
            self.history_start_edit.clear()

        if hasattr(self, "history_end_edit"):
            self.history_end_edit.clear()

        self.log("[INFO] History cleared")

