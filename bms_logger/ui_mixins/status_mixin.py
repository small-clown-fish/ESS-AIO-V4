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





class StatusMixin:
    def refresh_global_status_bar(self) -> None:
        if not hasattr(self, "status_selected_device_label"):
            return
        selected_device = self.current_control_device or "-"
        self.status_selected_device_label.setText(selected_device)
        self.status_sampling_label.setText(self.last_sampling_status)
        self.status_heartbeat_label.setText(self.last_heartbeat_status)
        self.status_hv_label.setText(self.last_hv_status)
        self.status_pcs_label.setText(
            "Loaded" if self.pcs_config.get("enabled", False) else "Disabled / Missing"
        )
        self.status_last_error_label.setText(self.last_error_message)

        active_cutoff = []
        for dev_name, states in self.cutoff_alarm_states.items():
            if states.get("charge_cutoff", False):
                active_cutoff.append(f"{dev_name}: charge")
            if states.get("discharge_cutoff", False):
                active_cutoff.append(f"{dev_name}: discharge")

        self.status_cutoff_label.setText("; ".join(active_cutoff) if active_cutoff else "Normal")
        self._set_label_status_color(self.status_sampling_label, self.last_sampling_status)
        self._set_label_status_color(self.status_heartbeat_label, self.last_heartbeat_status)
        self._set_label_status_color(self.status_hv_label, self.last_hv_status)
        self._set_label_status_color(self.status_pcs_label, self.status_pcs_label.text())
        self._set_label_status_color(self.status_cutoff_label, self.status_cutoff_label.text())
        self.refresh_overview()

    def _set_table_item_color(self, item: QTableWidgetItem, value: str) -> None:
        text = str(value).lower()

        if text in ["online", "running", "normal"]:
            item.setForeground(QColor("green"))
        elif text in ["stale", "scheduled", "timeout", "delay"]:
            item.setForeground(QColor("orange"))
        elif text in ["offline", "error", "failed", "active", "charge", "discharge"]:
            item.setForeground(QColor("red"))
        elif text in ["stopped", "idle"]:
            item.setForeground(QColor("gray"))

    def _set_label_status_color(self, label, value: str) -> None:
        text = str(value).lower()

        if "running" in text or text in ["online", "loaded", "success", "normal"]:
            label.setStyleSheet("color: green;")
        elif "stale" in text or "timeout" in text or "warning" in text:
            label.setStyleSheet("color: orange;")
        elif "error" in text or "failed" in text or "offline" in text or "charge" in text or "discharge" in text:
            label.setStyleSheet("color: red;")
        elif "stopped" in text or "idle" in text or "disabled" in text:
            label.setStyleSheet("color: gray;")
        else:
            label.setStyleSheet("")

    def _get_cluster_voltage_stats_for_ui(self, cluster):
        max_list = []
        min_list = []

        for dev in cluster.bms_devices:
            snapshot = self.latest_snapshots.get(dev.name)
            if not snapshot:
                continue

            try:
                max_v = float(snapshot.get("max_cell_voltage"))
                min_v = float(snapshot.get("min_cell_voltage"))
            except Exception:
                continue

            max_list.append(max_v)
            min_list.append(min_v)

        if not max_list or not min_list:
            return "-", "-"

        return max(max_list), min(min_list)

    def refresh_overview(self) -> None:
        if not hasattr(self, "overview_total_devices_label"):
            return

        total_devices = len(self.devices)
        running_devices = len(self.device_workers)

        online_devices = 0
        for name, row in self.device_rows.items():
            item = self.device_table.item(row, 12)
            if item is not None and item.text() == "Online":
                online_devices += 1

        self.overview_total_devices_label.setText(str(total_devices))
        self.overview_running_devices_label.setText(str(running_devices))
        self.overview_online_devices_label.setText(str(online_devices))
        self.overview_sampling_label.setText(self.last_sampling_status)
        self.overview_heartbeat_label.setText(self.last_heartbeat_status)
        self.overview_hv_label.setText(self.last_hv_status)

        active_cutoff = []
        for dev_name, states in self.cutoff_alarm_states.items():
            if states.get("charge_cutoff", False):
                active_cutoff.append(f"{dev_name}: charge")
            if states.get("discharge_cutoff", False):
                active_cutoff.append(f"{dev_name}: discharge")

        self.overview_cutoff_label.setText("; ".join(active_cutoff) if active_cutoff else "Normal")
        self.overview_last_error_label.setText(self.last_error_message)

        if hasattr(self, "overview_device_table"):
            self.overview_device_table.setRowCount(0)

            for dev in self.devices:
                name = dev["name"]
                row_idx = self.overview_device_table.rowCount()
                self.overview_device_table.insertRow(row_idx)

                device_row = self.device_rows.get(name)
                snapshot = self.latest_snapshots.get(name, {})

                online = "-"
                run_state = "-"

                if device_row is not None:
                    online_item = self.device_table.item(device_row, 12)
                    run_item = self.device_table.item(device_row, 11)

                    if online_item is not None:
                        online = online_item.text()
                    if run_item is not None:
                        run_state = run_item.text()

                values = [
                    name,
                    online,
                    run_state,
                    str(snapshot.get("soc", "-")),
                    str(snapshot.get("system_voltage", "-")),
                    str(snapshot.get("system_current", "-")),
                    str(snapshot.get("system_power", "-")),
                ]

                for col, value in enumerate(values):
                    item = QTableWidgetItem(value)

                    if col in [1, 2]:  # Online / Run State
                        self._set_table_item_color(item, value)

                    self.overview_device_table.setItem(row_idx, col, item)

        if hasattr(self, "overview_cluster_table") and hasattr(self, "site"):
            self.overview_cluster_table.setRowCount(0)

            for cluster in self.site.clusters:
                row_idx = self.overview_cluster_table.rowCount()
                self.overview_cluster_table.insertRow(row_idx)

                max_v, min_v = self._get_cluster_voltage_stats_for_ui(cluster)

                pcs_name = cluster.pcs_device.name if cluster.pcs_device else "-"
                derating_state = self.derating_state.get(cluster.name, {})
                cutoff_state = self.cutoff_alarm_states.get(cluster.name, {})

                derating_text = "Active" if derating_state.get("active", False) else "Normal"

                active_cutoffs = []
                if cutoff_state.get("charge_cutoff", False):
                    active_cutoffs.append("Charge")
                if cutoff_state.get("discharge_cutoff", False):
                    active_cutoffs.append("Discharge")
                cutoff_text = ", ".join(active_cutoffs) if active_cutoffs else "Normal"

                values = [
                    cluster.name,
                    str(len(cluster.bms_devices)),
                    pcs_name,
                    str(max_v),
                    str(min_v),
                    derating_text,
                    cutoff_text,
                ]

                for col, value in enumerate(values):
                    item = QTableWidgetItem(value)

                    if col in [5, 6]:
                        self._set_table_item_color(item, value)

                    self.overview_cluster_table.setItem(row_idx, col, item)

