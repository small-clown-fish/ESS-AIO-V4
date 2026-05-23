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





class DiagnosticsMixin:
    def _add_diagnosis_row(self, category: str, item: str, status: str, detail: str) -> None:
        if not hasattr(self, "diagnosis_summary_table"):
            return
        row = self.diagnosis_summary_table.rowCount()
        self.diagnosis_summary_table.insertRow(row)
        values = [category, item, status, detail]
        for col, value in enumerate(values):
            table_item = QTableWidgetItem(str(value))
            if col == 2:
                self._set_table_item_color(table_item, str(value))
            self.diagnosis_summary_table.setItem(row, col, table_item)

    def run_quick_diagnosis(self) -> None:
        if not hasattr(self, "diagnosis_summary_table"):
            return
        self.diagnosis_summary_table.setRowCount(0)
        lines = []

        profile_text = f"{self.current_profile_name} ({self.current_profile_dir})"
        self._add_diagnosis_row("Profile", "Current", "Normal", profile_text)
        lines.append(f"Profile: {profile_text}")

        bms_total = len(self.devices)
        running = len(self.device_workers)
        online = 0
        stale = 0
        for name, row in self.device_rows.items():
            item = self.device_table.item(row, 12)
            state = item.text() if item else "Unknown"
            if state == "Online":
                online += 1
            elif state == "Stale":
                stale += 1
        bms_status = "Normal" if bms_total == 0 or online == bms_total else ("Warning" if online > 0 else "Error")
        self._add_diagnosis_row("BMS", "Devices", bms_status, f"total={bms_total}, running={running}, online={online}, stale={stale}")
        lines.append(f"BMS: total={bms_total}, running={running}, online={online}, stale={stale}")

        pcs_count = len(getattr(self, "pcs_configs", {}))
        enabled_pcs = sum(1 for cfg in getattr(self, "pcs_configs", {}).values() if cfg.get("enabled", False))
        pcs_status = "Normal" if enabled_pcs > 0 else "Warning"
        self._add_diagnosis_row("PCS", "Configured", pcs_status, f"total={pcs_count}, enabled={enabled_pcs}, current={getattr(self, 'current_pcs_name', '-')}")
        lines.append(f"PCS: total={pcs_count}, enabled={enabled_pcs}, current={getattr(self, 'current_pcs_name', '-')}")

        for cluster in getattr(self, "site", None).clusters if hasattr(self, "site") else []:
            bms_names = ", ".join(dev.name for dev in cluster.bms_devices) or "-"
            pcs_name = cluster.pcs_device.name if cluster.pcs_device else "-"
            cutoff = self.cutoff_alarm_states.get(cluster.name, {})
            derating = self.derating_state.get(cluster.name, {})
            state = "Warning" if cutoff.get("charge_cutoff") or cutoff.get("discharge_cutoff") or derating.get("active") else "Normal"
            self._add_diagnosis_row("Cluster", cluster.name, state, f"BMS={bms_names}; PCS={pcs_name}")
            lines.append(f"Cluster {cluster.name}: BMS={bms_names}; PCS={pcs_name}; cutoff={cutoff}; derating={derating}")

        alarm_active = 0
        for snapshot in self.latest_snapshots.values():
            parsed = self.alarm_parser.parse_snapshot(snapshot)
            alarm_active += int(parsed.get("active_count", 0))
        alarm_status = "Normal" if alarm_active == 0 else "Warning"
        self._add_diagnosis_row("Alarm", "Current Active", alarm_status, f"active_count={alarm_active}")
        lines.append(f"Current active alarms: {alarm_active}")

        self._add_diagnosis_row("System", "Sampling", self.last_sampling_status, f"HV={self.last_hv_status}, Heartbeat={self.last_heartbeat_status}")
        lines.append(f"Sampling={self.last_sampling_status}, HV={self.last_hv_status}, Heartbeat={self.last_heartbeat_status}")
        lines.append(f"Last error: {self.last_error_message}")

        if hasattr(self, "diagnosis_text"):
            self.diagnosis_text.setPlainText("\n".join(lines))
        self.log("[INFO] Quick diagnosis completed")

    def export_quick_diagnosis(self) -> None:
        if not hasattr(self, "diagnosis_text"):
            return
        default_path = self.get_profile_path("diagnosis_report.txt")
        path, _ = QFileDialog.getSaveFileName(self, "Export diagnosis", str(default_path), "Text Files (*.txt)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.diagnosis_text.toPlainText())
            self.log(f"[INFO] Diagnosis exported: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to export diagnosis:\n{exc}")

    # ========================
    # v2.1: Register Debug
    # ========================
    def refresh_register_debug_targets(self) -> None:
        if not hasattr(self, "reg_target_combo"):
            return
        target_type = self.reg_target_type_combo.currentText() if hasattr(self, "reg_target_type_combo") else "BMS"
        current = self.reg_target_combo.currentText()
        self.reg_target_combo.blockSignals(True)
        self.reg_target_combo.clear()
        if target_type == "PCS":
            for name in sorted(getattr(self, "pcs_configs", {}).keys()):
                self.reg_target_combo.addItem(name)
        else:
            for dev in self.devices:
                self.reg_target_combo.addItem(dev.get("name", ""))
        if current:
            self.reg_target_combo.setCurrentText(current)
        self.reg_target_combo.blockSignals(False)

    def _parse_register_address(self, text: str) -> int:
        text = text.strip().lower()
        if text.startswith("0x"):
            return int(text, 16)
        return int(text)

    def _fake_register_values(self, address: int, count: int) -> list[int]:
        values = []
        for i in range(count):
            addr = address + i
            if addr == 0x0302:
                values.append(1)
            elif addr == 0x0022:
                values.append(750)
            elif addr == 0x0024:
                values.append(3550)
            elif addr == 0x0025:
                values.append(3250)
            else:
                values.append((addr * 7) % 65536)
        return values

    def _read_raw_registers(self, target_type: str, target_name: str, table: str, address: int, count: int) -> list[int]:
        if self.fake_mode:
            return self._fake_register_values(address, count)

        if target_type == "PCS":
            cfg = self.pcs_configs.get(target_name, self.pcs_config)
            client = self.create_pcs_client_for_pcs_name(target_name) if hasattr(self, "create_pcs_client_for_pcs_name") else self.create_pcs_client()
            try:
                if not client.connect():
                    raise RuntimeError("PCS connect failed")
                read_fn = client.client.read_input_registers if table == "input" else client.client.read_holding_registers
                rr = read_fn(address=address, count=count, device_id=int(cfg.get("unit_id", 1)))
                if rr.isError():
                    raise RuntimeError("PCS register read error")
                return list(rr.registers)
            finally:
                try:
                    client.close()
                except Exception:
                    pass

        dev_cfg = next((dev for dev in self.devices if dev.get("name") == target_name), None)
        if dev_cfg is None:
            raise RuntimeError(f"BMS not found: {target_name}")
        from ..client_factory import create_bms_client
        client = create_bms_client(dev_cfg, fake_mode=False)
        try:
            if not client.connect():
                raise RuntimeError("BMS connect failed")
            if table == "input":
                rr = client.client.read_input_registers(address=address, count=count, device_id=int(dev_cfg.get("unit_id", 1)))
                if rr.isError():
                    raise RuntimeError("BMS input register read error")
                return list(rr.registers)
            regs = client._read_holding_block(address, count)
            if regs is None:
                raise RuntimeError("BMS holding register read error")
            return list(regs)
        finally:
            try:
                client.close()
            except Exception:
                pass

    def _write_raw_register(self, target_type: str, target_name: str, address: int, value: int) -> bool:
        if self.fake_mode:
            return True
        if target_type == "PCS":
            client = self.create_pcs_client_for_pcs_name(target_name) if hasattr(self, "create_pcs_client_for_pcs_name") else self.create_pcs_client()
            cfg = self.pcs_configs.get(target_name, self.pcs_config)
            try:
                if not client.connect():
                    raise RuntimeError("PCS connect failed")
                rr = client.client.write_register(address=address, value=int(value), device_id=int(cfg.get("unit_id", 1)))
                return not rr.isError()
            finally:
                try:
                    client.close()
                except Exception:
                    pass
        dev_cfg = next((dev for dev in self.devices if dev.get("name") == target_name), None)
        if dev_cfg is None:
            raise RuntimeError(f"BMS not found: {target_name}")
        from ..client_factory import create_bms_client
        client = create_bms_client(dev_cfg, fake_mode=False)
        try:
            if not client.connect():
                raise RuntimeError("BMS connect failed")
            return bool(client.write_single_register(address, int(value)))
        finally:
            try:
                client.close()
            except Exception:
                pass

    def handle_register_debug_read(self) -> None:
        try:
            self.refresh_register_debug_targets()
            target_type = self.reg_target_type_combo.currentText()
            target_name = self.reg_target_combo.currentText()
            table = self.reg_table_combo.currentText()
            address = self._parse_register_address(self.reg_address_edit.text())
            count = int(self.reg_count_spin.value())
            regs = self._read_raw_registers(target_type, target_name, table, address, count)
            self.register_debug_table.setRowCount(0)
            for i, raw in enumerate(regs):
                row = self.register_debug_table.rowCount()
                self.register_debug_table.insertRow(row)
                ascii_text = ""
                try:
                    ascii_text = bytes([(int(raw) >> 8) & 0xFF, int(raw) & 0xFF]).decode("ascii", errors="ignore").replace("\x00", "")
                except Exception:
                    ascii_text = ""
                values = [f"0x{address + i:04x}", str(raw), f"0x{int(raw):04x}", ascii_text]
                for col, value in enumerate(values):
                    self.register_debug_table.setItem(row, col, QTableWidgetItem(value))
            self.register_debug_log.append(f"[READ] {target_type} {target_name} {table} 0x{address:04x} count={count} -> {regs}")
        except Exception as exc:
            QMessageBox.critical(self, "Register Read Error", str(exc))
            if hasattr(self, "register_debug_log"):
                self.register_debug_log.append(f"[ERROR] {exc}")

    def handle_register_debug_write(self) -> None:
        try:
            target_type = self.reg_target_type_combo.currentText()
            target_name = self.reg_target_combo.currentText()
            address = self._parse_register_address(self.reg_address_edit.text())
            value = int(self.reg_value_spin.value())
            ok = self._write_raw_register(target_type, target_name, address, value)
            msg = f"[WRITE] {target_type} {target_name} 0x{address:04x}={value} -> {'OK' if ok else 'FAILED'}"
            self.register_debug_log.append(msg)
            self.log(msg)
        except Exception as exc:
            QMessageBox.critical(self, "Register Write Error", str(exc))
            if hasattr(self, "register_debug_log"):
                self.register_debug_log.append(f"[ERROR] {exc}")

    # ========================
    # v2.1: Alarm Analysis
    # ========================
