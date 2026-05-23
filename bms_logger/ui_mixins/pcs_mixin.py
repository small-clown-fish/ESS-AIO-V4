from __future__ import annotations

import json
import csv
import time
from collections import deque
from pathlib import Path
from typing import Any, Dict

from ..pcs_profiles import install_profile, list_profile_files, load_profile, merge_device_with_profile, profile_key_from_path

from PySide6.QtCharts import QChart, QLineSeries
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem, QInputDialog
from PySide6.QtGui import QColor
from ..recorder import CsvRecorder
from ..async_recorder import AsyncRecorderProxy
from ..worker import PcsPollingWorker
from ..paths import resource_path





class PcsConfigMixin:
    def get_pcs_profile_dirs(self) -> list[Path]:
        """Directories searched for PCS protocol profiles.

        A PCS profile is the vendor/model point table and command mapping. A PCS device
        instance stores only connection/runtime data plus a profile key.
        """
        dirs = [
            self.get_profile_path("pcs_profiles"),
            resource_path("pcs_profiles"),
            resource_path("config_templates"),
        ]
        # Best effort: ensure the profile-local folder exists for imported profiles.
        try:
            dirs[0].mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return dirs

    def get_available_pcs_profiles(self) -> dict[str, Path]:
        return list_profile_files(self.get_pcs_profile_dirs())

    def refresh_pcs_profile_combo(self) -> None:
        combo = getattr(self, "pcs_profile_combo", None)
        if combo is None:
            return
        profiles = self.get_available_pcs_profiles()
        current = combo.currentData() or combo.currentText() or self.pcs_config.get("profile") or "kehua_bcs1250"
        combo.blockSignals(True)
        combo.clear()
        for key, path in sorted(profiles.items()):
            display = key
            try:
                _, profile, _ = load_profile(key, self.get_pcs_profile_dirs())
                display = str(profile.get("display_name") or profile.get("name") or key)
            except Exception:
                pass
            combo.addItem(f"{display}  [{key}]", key)
        if combo.count() == 0:
            combo.addItem("No profile found - import one", "")
        idx = combo.findData(current)
        if idx < 0 and combo.count() > 0:
            idx = 0
        if idx >= 0:
            combo.setCurrentIndex(idx)
        combo.blockSignals(False)

    def resolve_pcs_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        cfg = dict(config)
        profile_key = str(cfg.get("profile") or cfg.get("profile_key") or "").strip()
        if not profile_key and cfg.get("points"):
            # Backward compatibility for old embedded configs.
            return cfg
        if not profile_key:
            profile_key = "kehua_bcs1250"
            cfg["profile"] = profile_key
        try:
            key, profile, _path = load_profile(profile_key, self.get_pcs_profile_dirs())
            cfg["profile"] = key
            return merge_device_with_profile(cfg, profile)
        except Exception as exc:
            # Return device config so the UI does not crash; control precheck will fail if no points exist.
            cfg.setdefault("points", {})
            if hasattr(self, "log"):
                self.log(f"[WARN] PCS profile resolve failed for '{profile_key}': {exc}")
            return cfg

    def save_pcs_config(self) -> None:
        path = self.get_profile_path("pcs_config.json")
        multi_path = self.get_profile_path("pcs_configs.json")
        # Save device instances. Empty PCS list is valid for BMS-only tests.
        if self.current_pcs_name and self.pcs_config:
            if "name" not in self.pcs_config:
                self.pcs_config["name"] = self.current_pcs_name
            self.pcs_configs[self.current_pcs_name] = self.pcs_config
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.pcs_config if self.pcs_configs else {}, f, ensure_ascii=False, indent=2)
        with open(multi_path, "w", encoding="utf-8") as f:
            json.dump(self.pcs_configs, f, ensure_ascii=False, indent=2)
        self.log(f"[INFO] Saved PCS current device: {path}")
        self.log(f"[INFO] Saved PCS device list: {multi_path}")

    def set_current_pcs_config(self, name: str, config: Dict[str, Any]) -> None:
        config = dict(config)
        config["name"] = name
        self.current_pcs_name = name
        self.pcs_config = config
        self.pcs_configs[name] = config

    def get_pcs_config_by_name(self, name: str) -> Dict[str, Any]:
        if name in getattr(self, "pcs_configs", {}):
            return self.resolve_pcs_config(self.pcs_configs[name])
        if self.pcs_config.get("name", "PCS-1") == name:
            return self.resolve_pcs_config(self.pcs_config)
        cfg = dict(self.pcs_config)
        cfg["name"] = name
        return self.resolve_pcs_config(cfg)

    def on_control_pcs_changed(self, name: str) -> None:
        """Keep the selected PCS in the Control page synchronized with the active device instance."""
        name = (name or "").strip()
        if not name or name not in getattr(self, "pcs_configs", {}):
            return
        self.current_pcs_name = name
        self.pcs_config = self.pcs_configs[name]
        if hasattr(self, "pcs_config_state_label"):
            resolved = self.resolve_pcs_config(self.pcs_config)
            self.pcs_config_state_label.setText("Loaded" if resolved.get("enabled", False) and resolved.get("points") else "Disabled / Missing")
        self.refresh_global_status_bar()
        self.log(f"[INFO] Current PCS selected: {name}")

    def set_selected_pcs_as_current(self) -> None:
        name = ""
        if hasattr(self, "pcs_device_table") and self.pcs_device_table.currentRow() >= 0:
            item = self.pcs_device_table.item(self.pcs_device_table.currentRow(), 0)
            if item:
                name = item.text().strip()
        if not name and hasattr(self, "pcs_name_edit"):
            name = self.pcs_name_edit.text().strip()
        if not name or name not in getattr(self, "pcs_configs", {}):
            QMessageBox.warning(self, "Warning", "Select an existing PCS first.")
            return
        self.current_pcs_name = name
        self.pcs_config = self.pcs_configs[name]
        self.save_pcs_config()
        self.refresh_pcs_view()
        self.refresh_global_status_bar()
        self.log(f"[INFO] Set current PCS: {name}")

    def load_pcs_config_from_file(self) -> None:
        """Import a vendor PCS profile JSON and make it selectable in the UI.

        The imported file should contain a 'points' section. The file is copied into the
        active profile folder as <profile_key>.json. Devices can then reference it.
        """
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import PCS Profile JSON",
            str(Path.cwd()),
            "JSON Files (*.json);;All Files (*)",
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to load PCS profile:\n{exc}")
            return
        if not isinstance(data, dict) or "points" not in data:
            QMessageBox.warning(self, "Warning", "This file is not a PCS profile: missing 'points'.")
            return
        profile_key = str(data.get("profile_key") or data.get("profile") or profile_key_from_path(path))
        try:
            key, target = install_profile(path, self.get_profile_path("pcs_profiles"), key=profile_key)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to install PCS profile:\n{exc}")
            return
        self.refresh_pcs_profile_combo()
        combo = getattr(self, "pcs_profile_combo", None)
        if combo is not None:
            idx = combo.findData(key)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        QMessageBox.information(self, "Profile Imported", f"PCS profile imported:\n{key}\n\n{target}")
        self.log(f"[INFO] Imported PCS profile '{key}' from: {path}")

    def ensure_pcs_controls_initialized(self) -> None:
        """Best-effort refresh after UI construction/profile loading."""
        try:
            self.refresh_pcs_profile_combo()
            self.refresh_pcs_view()
        except Exception as exc:
            self.log(f"[WARN] PCS view refresh skipped: {exc}")

    def _pcs_fmt_value(self, value: Any, unit: str = "") -> str:
        """Format numbers for UI without ugly trailing zeros.

        Examples:
            10.0000 -> 10
            10.5000 -> 10.5
            10.1250 -> 10.125
        """
        if value is None:
            return "-"
        try:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                num = float(value)
                if abs(num) < 1e-12:
                    num = 0.0
                txt = (f"{num:.3f}").rstrip("0").rstrip(".")
            else:
                txt = str(value)
        except Exception:
            txt = str(value)
        return f"{txt} {unit}".strip()

    def _pcs_fmt_cell_value(self, value: Any) -> str:
        """Compact value formatter for PCS tables/live register cells."""
        if value is None:
            return "-"
        try:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                num = float(value)
                if abs(num) < 1e-12:
                    num = 0.0
                return (f"{num:.3f}").rstrip("0").rstrip(".")
        except Exception:
            pass
        return str(value)

    def _pcs_point_value(self, snapshot: Dict[str, Any], *names: str) -> Any:
        points = (snapshot or {}).get("points", {}) or {}
        for name in names:
            if name in points:
                return points.get(name)
        return None

    def _pcs_point_raw(self, snapshot: Dict[str, Any], *names: str) -> Any:
        raw = (snapshot or {}).get("raw", {}) or {}
        points = (snapshot or {}).get("points", {}) or {}
        for name in names:
            if name in raw:
                return raw.get(name)
            if name in points:
                return points.get(name)
        return None

    def _pcs_point_label(self, cfg: dict, point_name: str, value: Any) -> str:
        if value is None:
            return "-"
        resolved = self.resolve_pcs_config(cfg)
        pcfg = (resolved.get("points", {}) or {}).get(point_name, {}) or {}
        enum = pcfg.get("enum") or {}
        raw_key = str(int(value)) if isinstance(value, (int, float)) and float(value).is_integer() else str(value)
        if raw_key in enum:
            return str(enum[raw_key])
        return str(value)

    def _pcs_table_values(self, name: str, cfg: Dict[str, Any]) -> tuple[list[str], str, str]:
        latest = getattr(self, "latest_pcs_snapshots", {}) or {}
        errors = getattr(self, "latest_pcs_errors", {}) or {}
        profile_key = str(cfg.get("profile") or cfg.get("profile_key") or ("embedded" if cfg.get("points") else "-"))
        snapshot = latest.get(name, {}) or {}
        is_polling = name in getattr(self, "pcs_workers", {})
        has_errors = bool(errors.get(name)) or bool((snapshot.get("point_errors", {}) or {}))

        online_value = self._pcs_point_value(snapshot, "online_status")
        online_text = "Yes" if snapshot and online_value is None else (self._pcs_point_label(cfg, "online_status", online_value) if online_value is not None else "-")
        connection_text = "Connected" if is_polling and snapshot else ("Connecting" if is_polling else "Disconnected")
        if has_errors and is_polling:
            connection_text = "Error"

        run_value = self._pcs_point_value(snapshot, "run_status")
        remote_value = self._pcs_point_value(snapshot, "remote_local_status")
        ac_value = self._pcs_point_value(snapshot, "ac_breaker_status")
        dc_value = self._pcs_point_value(snapshot, "dc_breaker_status")
        set_kw = self._pcs_point_value(snapshot, "set_active_power")
        charge_kw = self._pcs_point_value(snapshot, "charge_active_power", "active_power")
        discharge_kw = self._pcs_point_value(snapshot, "discharge_active_power")
        dc_voltage = self._pcs_point_value(snapshot, "dc_voltage")
        dc_current = self._pcs_point_value(snapshot, "dc_current")
        fault = self._pcs_point_raw(snapshot, "fault_status")
        alarm = self._pcs_point_raw(snapshot, "alarm_status")
        alarm_text = "-"
        if fault is not None or alarm is not None:
            alarm_text = f"F:{fault if fault is not None else '-'} / A:{alarm if alarm is not None else '-'}"
        if has_errors and alarm_text == "-":
            alarm_text = "Read error"

        values = [
            name,
            profile_key,
            str(cfg.get("host", "")),
            str(cfg.get("port", 502)),
            str(cfg.get("unit_id", 1)),
            "Yes" if cfg.get("enabled", False) else "No",
            connection_text,
            online_text,
            self._pcs_point_label(cfg, "run_status", run_value),
            self._pcs_point_label(cfg, "remote_local_status", remote_value),
            self._pcs_point_label(cfg, "ac_breaker_status", ac_value),
            self._pcs_point_label(cfg, "dc_breaker_status", dc_value),
            self._pcs_fmt_value(set_kw, "kW"),
            self._pcs_fmt_value(charge_kw, "kW"),
            self._pcs_fmt_value(discharge_kw, "kW"),
            self._pcs_fmt_value(dc_voltage, "V"),
            self._pcs_fmt_value(dc_current, "A"),
            alarm_text,
            str(snapshot.get("timestamp", "-")) if snapshot else "-",
        ]
        return values, connection_text, alarm_text

    def _set_pcs_table_item(self, row: int, col: int, value: str, connection_text: str = "", alarm_text: str = "") -> None:
        table = self.pcs_device_table
        old_item = table.item(row, col)
        text = str(value)
        if old_item is not None and old_item.text() == text:
            item = old_item
        else:
            item = QTableWidgetItem(text)
            table.setItem(row, col, item)
        # Keep PCS table readable on the dark theme.
        # Only the status columns get semantic colors; all other cells use the same
        # normal text color as the BMS table instead of inheriting a transparent/black brush.
        normal_fg = QColor("#e5e7eb")
        normal_bg = QColor("#020617")
        item.setBackground(normal_bg)
        item.setForeground(normal_fg)

        if col == 6:
            # Connection column: color text only, no heavy background fill.
            if connection_text == "Connected":
                item.setForeground(QColor("#22c55e"))
            elif connection_text == "Connecting":
                item.setForeground(QColor("#60a5fa"))
            elif connection_text == "Error":
                item.setForeground(QColor("#f87171"))
            else:
                item.setForeground(QColor("#94a3b8"))
        elif col == 17 and alarm_text not in {"-", "F:0 / A:0", "F:0.0 / A:0.0"}:
            item.setBackground(QColor("#451a03"))
            item.setForeground(QColor("#facc15"))

    def _find_pcs_table_row(self, name: str) -> int:
        if not hasattr(self, "pcs_device_table"):
            return -1
        for row in range(self.pcs_device_table.rowCount()):
            item = self.pcs_device_table.item(row, 0)
            if item and item.text() == name:
                return row
        return -1

    def update_pcs_table_row(self, name: str) -> None:
        if not hasattr(self, "pcs_device_table") or name not in getattr(self, "pcs_configs", {}):
            return
        row = self._find_pcs_table_row(name)
        if row < 0:
            self.refresh_pcs_view(full=True)
            return
        values, connection_text, alarm_text = self._pcs_table_values(name, self.pcs_configs[name])
        self.pcs_device_table.setUpdatesEnabled(False)
        try:
            for col, value in enumerate(values):
                self._set_pcs_table_item(row, col, value, connection_text, alarm_text)
        finally:
            self.pcs_device_table.setUpdatesEnabled(True)

    def refresh_pcs_view(self, full: bool = True) -> None:
        if not hasattr(self, "pcs_device_table"):
            return

        # Profile scanning is relatively expensive; only do it on full structural refresh.
        if full:
            self.refresh_pcs_profile_combo()

        if self.current_pcs_name and self.pcs_config and self.current_pcs_name not in self.pcs_configs:
            self.pcs_configs[self.current_pcs_name] = self.pcs_config

        table = self.pcs_device_table
        table.setUpdatesEnabled(False)
        try:
            if full:
                table.setRowCount(0)
                for name, cfg in sorted(self.pcs_configs.items()):
                    row = table.rowCount()
                    table.insertRow(row)
                    values, connection_text, alarm_text = self._pcs_table_values(name, cfg)
                    for col, value in enumerate(values):
                        self._set_pcs_table_item(row, col, value, connection_text, alarm_text)
            else:
                for name in sorted(self.pcs_configs.keys()):
                    self.update_pcs_table_row(name)
        finally:
            table.setUpdatesEnabled(True)

        # Refresh PCS combo boxes used by Site and Control pages only on structural changes.
        if full:
            names = sorted(self.pcs_configs.keys())
            for combo_name in ["cluster_pcs_combo", "control_pcs_combo", "cluster_dispatch_combo"]:
                combo = getattr(self, combo_name, None)
                if combo is None:
                    continue
                current = combo.currentText() or self.current_pcs_name
                combo.blockSignals(True)
                combo.clear()
                for name in names:
                    combo.addItem(name)
                if current in names:
                    combo.setCurrentText(current)
                combo.blockSignals(False)



    def choose_pcs_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Choose PCS output directory")
        if directory and hasattr(self, "pcs_output_dir_edit"):
            self.pcs_output_dir_edit.setText(directory)

    def _pcs_default_output_dir(self, name: str | None = None) -> Path:
        cfg = {}
        if name and name in getattr(self, "pcs_configs", {}):
            cfg = self.pcs_configs.get(name, {}) or {}
        output_dir = str(cfg.get("output_dir") or "").strip()
        path = Path(output_dir) if output_dir else (self.get_profile_path("output") / "pcs")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _pcs_poll_point_names_from_config(self, cfg: dict) -> list[str]:
        resolved = self.resolve_pcs_config(cfg)
        points = resolved.get("points", {}) or {}
        preferred = [
            "heartbeat",
            "set_active_power",
            "run_status",
            "remote_local_status",
            "ac_breaker_status",
            "dc_breaker_status",
            "active_power",
            "charge_active_power",
            "discharge_active_power",
            "reactive_power",
            "dc_voltage",
            "dc_current",
            "ac_voltage",
            "ac_current",
            "frequency",
            "power_factor",
            "fault_status",
            "alarm_status",
            "mode",
            "online_status",
        ]
        names = [name for name in preferred if name in points]
        for name in sorted(points.keys()):
            if name in names:
                continue
            pcfg = points.get(name, {}) or {}
            access = str(pcfg.get("access", "")).upper()
            # Do not poll write-only commands. RW setpoints are useful to display, but keep the list compact.
            if access in {"WO"} or name.endswith("_cmd"):
                continue
            if len(names) >= 60:
                break
            names.append(name)
        return names

    def start_pcs_polling_by_name(self, name: str) -> None:
        if not name or name not in getattr(self, "pcs_configs", {}):
            QMessageBox.warning(self, "Warning", f"PCS not found: {name}")
            return
        if name in getattr(self, "pcs_workers", {}):
            self.log(f"[INFO] PCS already polling: {name}")
            return
        cfg = self.get_pcs_config_by_name(name)
        client = self.create_pcs_client_for_pcs_name(name)
        point_names = self._pcs_poll_point_names_from_config(cfg)
        if not point_names:
            QMessageBox.warning(self, "Warning", f"No readable PCS points configured for {name}.")
            return
        interval = float(cfg.get("poll_interval", cfg.get("interval", 2.0)))
        worker = PcsPollingWorker(
            pcs_name=name,
            client=client,
            interval=interval,
            point_names=point_names,
            callback=lambda dn, data: self.bridge.pcs_data_received.emit(dn, data),
            error_callback=lambda dn, err: self.bridge.pcs_error_received.emit(dn, err),
            status_callback=lambda dn, status: self.bridge.task_status_received.emit(dn, status),
        )
        self.pcs_workers[name] = worker
        worker.start()
        self.log(f"[INFO] Started PCS polling: {name} ({len(point_names)} points, {interval}s)")
        self.refresh_pcs_view()

    def stop_pcs_polling_by_name(self, name: str) -> None:
        worker = getattr(self, "pcs_workers", {}).pop(name, None)
        if worker:
            worker.stop()
            worker.join(timeout=3.0)
        self._stop_pcs_csv_for_device(name)
        self.log(f"[INFO] Stopped PCS polling: {name}")
        self.refresh_pcs_view()

    def start_selected_pcs_polling(self) -> None:
        name = ""
        if hasattr(self, "pcs_device_table") and self.pcs_device_table.currentRow() >= 0:
            item = self.pcs_device_table.item(self.pcs_device_table.currentRow(), 0)
            if item:
                name = item.text().strip()
        if not name and hasattr(self, "pcs_name_edit"):
            name = self.pcs_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Warning", "Select one PCS first.")
            return
        self.start_pcs_polling_by_name(name)

    def stop_selected_pcs_polling(self) -> None:
        name = ""
        if hasattr(self, "pcs_device_table") and self.pcs_device_table.currentRow() >= 0:
            item = self.pcs_device_table.item(self.pcs_device_table.currentRow(), 0)
            if item:
                name = item.text().strip()
        if not name and hasattr(self, "pcs_name_edit"):
            name = self.pcs_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Warning", "Select one PCS first.")
            return
        self.stop_pcs_polling_by_name(name)

    def start_all_pcs_polling(self) -> None:
        for name in sorted(getattr(self, "pcs_configs", {}).keys()):
            cfg = self.pcs_configs.get(name, {})
            if cfg.get("enabled", False):
                self.start_pcs_polling_by_name(name)

    def stop_all_pcs_polling(self) -> None:
        for name in list(getattr(self, "pcs_workers", {}).keys()):
            self.stop_pcs_polling_by_name(name)

    def _selected_pcs_name_or_all(self) -> list[str]:
        names: list[str] = []
        if hasattr(self, "pcs_device_table") and self.pcs_device_table.currentRow() >= 0:
            item = self.pcs_device_table.item(self.pcs_device_table.currentRow(), 0)
            if item and item.text().strip():
                names = [item.text().strip()]
        if not names:
            names = sorted(getattr(self, "pcs_configs", {}).keys())
        return [n for n in names if n]

    def update_pcs_csv_status_label(self) -> None:
        active = sorted(getattr(self, "pcs_csv_recording_devices", set()))
        label = getattr(self, "pcs_csv_status_label", None)
        if label is None:
            return
        if active:
            shown = ", ".join(active[:3])
            if len(active) > 3:
                shown += f" +{len(active)-3}"
            label.setText(f"PCS CSV: Recording ON ({shown})")
            label.setStyleSheet("color: #16803a; font-weight: 700;")
        else:
            label.setText("PCS CSV: Recording OFF")
            label.setStyleSheet("color: #777; font-weight: 600;")

    def start_pcs_csv_recording(self) -> None:
        names = self._selected_pcs_name_or_all()
        if not names:
            QMessageBox.information(self, "Info", "No PCS device configured.")
            return
        if not hasattr(self, "pcs_recorders"):
            self.pcs_recorders = {}
        started = []
        for name in names:
            if name not in getattr(self, "pcs_configs", {}):
                continue
            if name not in self.pcs_recorders:
                self.pcs_recorders[name] = AsyncRecorderProxy(
                    CsvRecorder(output_dir=self._pcs_default_output_dir(name), device_name=f"pcs_{name}")
                )
            self.pcs_csv_recording_devices.add(name)
            started.append(name)
        if started:
            dirs = []
            for name in started:
                try:
                    dirs.append(str(self._pcs_default_output_dir(name)))
                except Exception:
                    pass
            self.update_pcs_csv_status_label()
            self.log(f"[CSV] PCS CSV recording ON: {', '.join(started)}")
            if dirs:
                self.log(f"[CSV] PCS CSV output dir(s): {', '.join(sorted(set(dirs)))}")
            self.statusBar().showMessage(f"PCS CSV recording ON: {', '.join(started)}", 5000)
        else:
            self.update_pcs_csv_status_label()
            QMessageBox.warning(self, "Warning", "No valid PCS selected for CSV recording.")

    def _stop_pcs_csv_for_device(self, name: str) -> None:
        self.pcs_csv_recording_devices.discard(name)
        rec = getattr(self, "pcs_recorders", {}).pop(name, None)
        if rec:
            try:
                rec.close()
            except Exception:
                pass
        self.update_pcs_csv_status_label()

    def stop_pcs_csv_recording(self) -> None:
        names = self._selected_pcs_name_or_all()
        if not names:
            names = list(getattr(self, "pcs_csv_recording_devices", set()))
        stopped = []
        for name in names:
            if name in getattr(self, "pcs_csv_recording_devices", set()) or name in getattr(self, "pcs_recorders", {}):
                self._stop_pcs_csv_for_device(name)
                stopped.append(name)
        self.update_pcs_csv_status_label()
        if stopped:
            self.log(f"[CSV] PCS CSV recording OFF: {', '.join(stopped)}")
            self.statusBar().showMessage(f"PCS CSV recording OFF: {', '.join(stopped)}", 5000)
        else:
            self.log("[CSV] No active PCS CSV recording to stop.")

    def on_pcs_data_received(self, pcs_name: str, snapshot: Dict[str, Any]) -> None:
        if not hasattr(self, "latest_pcs_snapshots"):
            self.latest_pcs_snapshots = {}
        if not hasattr(self, "latest_pcs_errors"):
            self.latest_pcs_errors = {}
        self.latest_pcs_snapshots[pcs_name] = snapshot
        self.latest_pcs_errors.pop(pcs_name, None)
        rec = getattr(self, "pcs_recorders", {}).get(pcs_name)
        if rec and pcs_name in getattr(self, "pcs_csv_recording_devices", set()):
            rec.write_row(snapshot)
        # Update only the changed PCS row instead of rebuilding the whole PCS table.
        self.update_pcs_table_row(pcs_name)

        # Update live register table only for the selected PCS and throttle UI writes.
        selected = ""
        try:
            selected = self._get_selected_pcs_name()
        except Exception:
            selected = self.current_pcs_name
        now = time.time()
        last_live = getattr(self, "_last_pcs_live_table_update_ts", 0.0)
        if selected == pcs_name and hasattr(self, "pcs_live_table") and now - last_live >= 1.0:
            self._last_pcs_live_table_update_ts = now
            rows = []
            cfg = self.get_pcs_config_by_name(pcs_name)
            points_cfg = cfg.get("points", {}) or {}
            for point_name, value in (snapshot.get("points", {}) or {}).items():
                pcfg = points_cfg.get(point_name, {}) or {}
                raw = (snapshot.get("raw", {}) or {}).get(point_name, "-")
                address = pcfg.get("address", "")
                unit = pcfg.get("unit", "")
                title = pcfg.get("name_cn") or pcfg.get("name_en") or pcfg.get("description") or point_name
                meaning = self._format_pcs_point_meaning(pcfg, raw) if hasattr(self, "_format_pcs_point_meaning") else ""
                rows.append([point_name, address, title, raw, value, unit, meaning])
            self.pcs_live_table.setUpdatesEnabled(False)
            try:
                self.pcs_live_table.setRowCount(len(rows))
                for row_idx, row in enumerate(rows):
                    for col, value in enumerate(row):
                        text = self._pcs_fmt_cell_value(value)
                        old_item = self.pcs_live_table.item(row_idx, col)
                        if old_item is None or old_item.text() != text:
                            self.pcs_live_table.setItem(row_idx, col, QTableWidgetItem(text))
            finally:
                self.pcs_live_table.setUpdatesEnabled(True)

    def on_pcs_error_received(self, pcs_name: str, error: str) -> None:
        if not hasattr(self, "latest_pcs_errors"):
            self.latest_pcs_errors = {}
        self.latest_pcs_errors[pcs_name] = error
        self.log(f"[ERROR] PCS {pcs_name}: {error}")
        self.refresh_pcs_view()

    def on_pcs_table_clicked(self, row: int, column: int) -> None:
        _ = column
        item = self.pcs_device_table.item(row, 0) if hasattr(self, "pcs_device_table") else None
        if item is None:
            return
        name = item.text()
        cfg = self.pcs_configs.get(name)
        if not cfg:
            return
        self.pcs_name_edit.setText(name)
        self.pcs_host_edit.setText(str(cfg.get("host", "")))
        self.pcs_port_spin.setValue(int(cfg.get("port", 502)))
        self.pcs_unit_spin.setValue(int(cfg.get("unit_id", 1)))
        self.pcs_enabled_combo.setCurrentText("Enabled" if cfg.get("enabled", False) else "Disabled")
        self.pcs_fake_scenario_combo.setCurrentText(str(cfg.get("fake_scenario", "normal")))
        if hasattr(self, "pcs_output_dir_edit"):
            self.pcs_output_dir_edit.setText(str(cfg.get("output_dir", str(self.get_profile_path("output") / "pcs"))))
        profile_key = str(cfg.get("profile") or cfg.get("profile_key") or "")
        combo = getattr(self, "pcs_profile_combo", None)
        if combo is not None:
            idx = combo.findData(profile_key)
            if idx >= 0:
                combo.setCurrentIndex(idx)

    def add_or_update_pcs(self) -> None:
        if not hasattr(self, "pcs_name_edit"):
            return
        name = self.pcs_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Warning", "PCS name cannot be empty.")
            return
        profile_key = ""
        combo = getattr(self, "pcs_profile_combo", None)
        if combo is not None:
            profile_key = str(combo.currentData() or "")
        if not profile_key:
            QMessageBox.warning(self, "Warning", "Select a PCS profile first. Import a profile if the list is empty.")
            return

        cfg = {
            "name": name,
            "enabled": self.pcs_enabled_combo.currentText() == "Enabled",
            "host": self.pcs_host_edit.text().strip(),
            "port": int(self.pcs_port_spin.value()),
            "unit_id": int(self.pcs_unit_spin.value()),
            "timeout": float(self.pcs_config.get("timeout", 3.0)),
            "fake_scenario": self.pcs_fake_scenario_combo.currentText(),
            "driver": getattr(self, "pcs_driver_key", "generic_modbus_pcs"),
            "profile": profile_key,
            "output_dir": self.pcs_output_dir_edit.text().strip() if hasattr(self, "pcs_output_dir_edit") else str(self.get_profile_path("output") / "pcs"),
        }
        self.pcs_configs[name] = cfg
        self.set_current_pcs_config(name, cfg)
        self.save_pcs_config()
        self.refresh_pcs_view()
        self.refresh_site_view()
        self.refresh_global_status_bar()
        self.log(f"[INFO] Added/updated PCS: {name} profile={profile_key} (not connected; use Connect selected PCS manually)")

    def remove_selected_pcs(self) -> None:
        name = ""
        if hasattr(self, "pcs_device_table") and self.pcs_device_table.currentRow() >= 0:
            item = self.pcs_device_table.item(self.pcs_device_table.currentRow(), 0)
            if item:
                name = item.text()
        if not name and hasattr(self, "pcs_name_edit"):
            name = self.pcs_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Warning", "No PCS selected.")
            return
        self.stop_pcs_polling_by_name(name)
        self.pcs_configs.pop(name, None)
        for cluster in self.site.clusters:
            if hasattr(cluster, "pcs_devices"):
                cluster.pcs_devices = [pcs for pcs in cluster.pcs_devices if pcs.name != name]
            elif cluster.pcs_device and cluster.pcs_device.name == name:
                cluster.pcs_device = None
        if self.current_pcs_name == name:
            if self.pcs_configs:
                self.current_pcs_name = next(iter(self.pcs_configs.keys()))
                self.pcs_config = self.pcs_configs[self.current_pcs_name]
            else:
                self.current_pcs_name = ""
                self.pcs_config = {}
        self.save_site_config()
        self.save_pcs_config()
        self.refresh_pcs_view()
        self.refresh_site_view()
        self.refresh_overview()
        self.log(f"[INFO] Removed PCS: {name}")

