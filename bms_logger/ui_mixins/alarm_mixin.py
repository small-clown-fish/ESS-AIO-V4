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





class AlarmMixin:
    def refresh_alarms(self, device_name: str) -> None:
        self.current_alarm_device = device_name
        self.alarm_device_label.setText(f"Current device: {device_name}")

        snapshot = self.latest_snapshots.get(device_name, {})
        parser = self.get_alarm_parser_for_device(device_name) if hasattr(self, "get_alarm_parser_for_device") else self.alarm_parser

        for i, addr in enumerate(range(0x0000, 0x0020)):
            key = f"alarm_0x{addr:04x}"
            value = snapshot.get(key, "-")

            self.alarm_table.item(i, 1).setText(str(value))

            if isinstance(value, int):
                self.alarm_table.item(i, 2).setText(f"0x{value:04x}")

                active_bits = []
                addr_key = f"0x{addr:04x}"

                for bit in range(16):
                    if value & (1 << bit):
                        bit_key = f"bit{bit}"
                        name = parser.alarm_map.get(addr_key, {}).get(bit_key, "Unknown")
                        active_bits.append(f"Bit{bit}: {name}")

                self.alarm_table.item(i, 3).setText("; ".join(active_bits) if active_bits else "-")
            else:
                self.alarm_table.item(i, 2).setText("-")
                self.alarm_table.item(i, 3).setText("-")

    def handle_load_alarm_history_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load alarm history CSV",
            str(Path.cwd()),
            "CSV Files (*.csv)",
        )

        if not path:
            return

        try:
            lines = []
            active_rows = 0
            first_alarm_time = ""
            last_alarm_time = ""

            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)

                for row in reader:
                    timestamp = row.get("timestamp", "")
                    device_name = row.get("device_name", "")
                    active_count = row.get("alarm_active_count", "")
                    text = row.get("active_alarm_text", "")

                    try:
                        count_int = int(active_count or 0)
                    except Exception:
                        count_int = 0

                    if count_int <= 0 and not text:
                        continue

                    active_rows += 1

                    if not first_alarm_time:
                        first_alarm_time = timestamp
                    last_alarm_time = timestamp

                    lines.append(
                        f"{timestamp} | {device_name} | count={active_count} | {text}"
                    )

            if not hasattr(self, "alarm_history_text"):
                QMessageBox.information(self, "Info", "Alarm history panel not available.")
                return

            if lines:
                summary = [
                    "Alarm History Summary",
                    f"Active rows: {active_rows}",
                    f"First alarm time: {first_alarm_time}",
                    f"Last alarm time: {last_alarm_time}",
                    "",
                    "Details:",
                ]
                self.alarm_history_text.setPlainText("\n".join(summary + lines))

                if hasattr(self, "history_start_edit") and hasattr(self, "history_end_edit"):
                    from datetime import datetime, timedelta

                    try:
                        first_dt = datetime.strptime(first_alarm_time, "%Y-%m-%d %H:%M:%S")
                        last_dt = datetime.strptime(last_alarm_time, "%Y-%m-%d %H:%M:%S")

                        start_dt = first_dt - timedelta(minutes=self.alarm_history_window_before_minutes)
                        end_dt = last_dt + timedelta(minutes=self.alarm_history_window_after_minutes)

                        start_text = start_dt.strftime("%Y-%m-%d %H:%M:%S")
                        end_text = end_dt.strftime("%Y-%m-%d %H:%M:%S")

                        self.history_start_edit.setText(start_text)
                        self.history_end_edit.setText(end_text)

                        self.log(
                            f"[INFO] History time filter filled from alarm CSV: "
                            f"{start_text} -> {end_text}"
                        )

                    except Exception:
                        self.history_start_edit.setText(first_alarm_time)
                        self.history_end_edit.setText(last_alarm_time)
                    self.log(
                        f"[INFO] History time filter filled from alarm CSV: "
                        f"{first_alarm_time} -> {last_alarm_time}"
                    )

            else:
                self.alarm_history_text.setPlainText("No active alarms found in this file.")

            self.log(f"[INFO] Loaded alarm history CSV: {path}, active_rows={active_rows}")

        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to load alarm history CSV:\n{exc}")
            self.log(f"[ERROR] Failed to load alarm history CSV: {exc}")

    def _fill_alarm_analysis(self, counter: Dict[str, int], summary: str, details: list[str]) -> None:
        if hasattr(self, "alarm_analysis_summary"):
            self.alarm_analysis_summary.setText(summary)
        if hasattr(self, "alarm_analysis_text"):
            self.alarm_analysis_text.setPlainText("\n".join(details))
        if hasattr(self, "alarm_analysis_table"):
            self.alarm_analysis_table.setRowCount(0)
            for alarm, count in sorted(counter.items(), key=lambda kv: kv[1], reverse=True)[:50]:
                row = self.alarm_analysis_table.rowCount()
                self.alarm_analysis_table.insertRow(row)
                values = [alarm, str(count), details[0] if details else "-"]
                for col, value in enumerate(values):
                    self.alarm_analysis_table.setItem(row, col, QTableWidgetItem(value))

    def handle_alarm_analysis_load_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load alarm CSV", str(self.current_profile_dir), "CSV Files (*.csv)")
        if not path:
            return
        counter: Dict[str, int] = {}
        active_rows = 0
        first_ts = ""
        last_ts = ""
        examples = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ts = row.get("timestamp", "")
                    text = row.get("active_alarm_text", "") or row.get("alarm_text", "")
                    count_text = row.get("alarm_active_count", "")
                    try:
                        count_int = int(count_text or 0)
                    except Exception:
                        count_int = 0
                    if count_int <= 0 and not text:
                        continue
                    active_rows += 1
                    if not first_ts:
                        first_ts = ts
                    last_ts = ts
                    if len(examples) < 20:
                        examples.append(f"{ts} | {row.get('device_name', '')} | {text}")
                    parts = [p.strip() for p in str(text).replace(";", "|").split("|") if p.strip()]
                    if not parts:
                        parts = ["Active alarm row"]
                    for part in parts:
                        counter[part] = counter.get(part, 0) + 1
            summary = f"Summary: active_rows={active_rows}, first={first_ts or '-'}, last={last_ts or '-'}, file={path}"
            self._fill_alarm_analysis(counter, summary, examples)
            self.log(f"[INFO] Alarm analysis loaded: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to analyze alarm CSV:\n{exc}")

    def handle_alarm_analysis_current(self) -> None:
        counter: Dict[str, int] = {}
        details = []
        active_devices = 0
        for device_name, snapshot in self.latest_snapshots.items():
            parser = self.get_alarm_parser_for_device(device_name) if hasattr(self, "get_alarm_parser_for_device") else self.alarm_parser
            parsed = parser.parse_snapshot(snapshot)
            active_count = int(parsed.get("active_count", 0))
            if active_count <= 0:
                continue
            active_devices += 1
            text = str(parsed.get("active_alarm_text", ""))
            details.append(f"{device_name}: count={active_count}, {text}")
            parts = [p.strip() for p in text.replace(";", "|").split("|") if p.strip()]
            for part in parts or ["Active alarm"]:
                counter[part] = counter.get(part, 0) + 1
        summary = f"Summary: active_devices={active_devices}, snapshot_devices={len(self.latest_snapshots)}"
        self._fill_alarm_analysis(counter, summary, details)
        self.log("[INFO] Current alarm analysis refreshed")

    # ========================
    # v2.1: Data Replay
    # ========================
