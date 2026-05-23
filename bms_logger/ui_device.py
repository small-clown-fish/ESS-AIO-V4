from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem

from .client_factory import create_bms_client
from .recorder import AlarmRecorder, CsvRecorder
from .async_recorder import AsyncRecorderProxy
from .worker import DeviceWorker
from .models import Site, Cluster, Device
from .release_manager import ensure_profile
from .alarm_parser import AlarmParser
from .bms_profiles import list_bms_profiles, load_bms_profile, install_bms_profile
from .paths import resource_path


class UiDeviceMixin:

    def get_bms_profile_dirs(self) -> list[Path]:
        """Directories searched for BMS profiles.

        Bundled profiles live in <app>/bms_profiles. Imported/user profiles
        can live under the active project profile folder.
        """
        dirs = [
            self.get_profile_path("bms_profiles"),
            resource_path("bms_profiles"),
        ]
        try:
            dirs[0].mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return dirs

    def get_available_bms_profiles(self) -> dict[str, Path]:
        return list_bms_profiles(self.get_bms_profile_dirs())

    def refresh_bms_profile_combo(self) -> None:
        combo = getattr(self, "bms_profile_combo", None)
        if combo is None:
            return
        profiles = self.get_available_bms_profiles()
        current = combo.currentData() or combo.currentText() or "catl_v22"
        combo.blockSignals(True)
        combo.clear()
        for key, path in sorted(profiles.items()):
            display = key
            try:
                _, meta, _ = load_bms_profile(key, self.get_bms_profile_dirs())
                display = str(meta.get("display_name") or key)
            except Exception:
                pass
            combo.addItem(f"{display}  [{key}]", key)
        if combo.count() == 0:
            combo.addItem("No BMS profile found", "")
        idx = combo.findData(current)
        if idx < 0 and combo.count() > 0:
            idx = 0
        if idx >= 0:
            combo.setCurrentIndex(idx)
        combo.blockSignals(False)

    def resolve_bms_profile(self, profile_key: str | None) -> tuple[str, dict, Path]:
        key = str(profile_key or "").strip() or "catl_v22"
        return load_bms_profile(key, self.get_bms_profile_dirs())

    def get_bms_config_by_name(self, device_name: str) -> dict:
        return next((d for d in self.devices if d.get("name") == device_name), {})

    def get_alarm_parser_for_device(self, device_name: str) -> AlarmParser:
        if not hasattr(self, "bms_alarm_parsers"):
            self.bms_alarm_parsers = {}
        dev = self.get_bms_config_by_name(device_name)
        profile_key = str(dev.get("profile") or dev.get("bms_profile") or "catl_v22")
        try:
            key, meta, _ = self.resolve_bms_profile(profile_key)
            alarm_map_path = Path(meta.get("alarm_map_path") or "")
        except Exception:
            key = profile_key
            alarm_map_path = self.current_profile_dir / "alarm_map.json"
        cache_key = str(alarm_map_path)
        if cache_key not in self.bms_alarm_parsers:
            self.bms_alarm_parsers[cache_key] = AlarmParser(alarm_map_path)
        return self.bms_alarm_parsers[cache_key]

    def choose_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Choose output directory")
        if directory:
            self.output_dir_edit.setText(directory)

    def add_device(self) -> None:
        device = {
            "name": self.name_edit.text().strip(),
            "host": self.host_edit.text().strip(),
            "port": int(self.port_spin.value()),
            "unit_id": int(self.unit_spin.value()),
            "interval": float(self.interval_spin.value()),
            "output_dir": self.output_dir_edit.text().strip(),
            "fake_scenario": self.bms_fake_scenario_combo.currentText() if hasattr(self, "bms_fake_scenario_combo") else "normal",
            "profile": (self.bms_profile_combo.currentData() if hasattr(self, "bms_profile_combo") else None) or "catl_v22",
        }

        if not device["name"]:
            QMessageBox.warning(self, "Warning", "Device name cannot be empty.")
            return

        if not device["host"]:
            QMessageBox.warning(self, "Warning", "Host cannot be empty.")
            return

        if any(d["name"] == device["name"] for d in self.devices):
            QMessageBox.warning(self, "Warning", f"Device name '{device['name']}' already exists.")
            return

        dev = Device(
            name=device["name"],
            device_type="BMS",
            config=device,
        )

        self.default_cluster.bms_devices.append(dev)
        self.devices.append(device)  # 保留原逻辑

        row = self.device_table.rowCount()
        self.device_table.insertRow(row)
        self.device_rows[device["name"]] = row

        values = [
            device["name"],
            device["host"],
            str(device["port"]),
            str(device["unit_id"]),
            str(device["interval"]),
            "-",
            "-",
            "-",
            "-",
            "-",
            "-",
            "Idle",
            "Unknown",
        ]

        for col, value in enumerate(values):
            self.device_table.setItem(row, col, QTableWidgetItem(value))

        self.curve_device_combo.addItem(device["name"])
        if hasattr(self, "driver_points_device_combo"):
            self.driver_points_device_combo.addItem(device["name"])
        self.detail_device_combo.addItem(device["name"])
        self.alarm_device_combo.addItem(device["name"])
        self.control_device_combo.addItem(device["name"])

        if self.current_curve_device is None:
            self.current_curve_device = device["name"]
            self.curve_device_combo.setCurrentText(device["name"])
            self.curve_device_label.setText(f"Current device: {device['name']}")

        if self.current_detail_device is None:
            self.current_detail_device = device["name"]
            self.detail_device_combo.setCurrentText(device["name"])
            self.detail_device_label.setText(f"Current device: {device['name']}")

        if self.current_alarm_device is None:
            self.current_alarm_device = device["name"]
            self.alarm_device_combo.setCurrentText(device["name"])
            self.alarm_device_label.setText(f"Current device: {device['name']}")

        if self.current_control_device is None:
            self.current_control_device = device["name"]
            self.control_device_combo.setCurrentText(device["name"])
            self.control_device_label.setText(f"Current device: {device['name']}")

        self.refresh_global_status_bar()
        self.refresh_site_view()

        self.log(
            f"[INFO] Added device: {device['name']} "
            f"({device['host']}:{device['port']}, unit={device['unit_id']}, profile={device.get('profile', '-')})"
        )
        # During startup/import loading, add_device() is used as a UI population helper.
        # Do not overwrite the existing site_config.json before load_site_config()
        # has a chance to restore the real cluster bindings.
        if not getattr(self, "_loading_devices_from_config", False):
            self.save_devices_to_default()
            self.save_site_config()


    def remove_selected_device(self) -> None:
        row = self.device_table.currentRow() if hasattr(self, "device_table") else -1
        device_name = ""
        if row >= 0:
            item = self.device_table.item(row, 0)
            if item:
                device_name = item.text()
        if not device_name:
            device_name = self.current_control_device or ""
        if not device_name:
            QMessageBox.warning(self, "Warning", "No BMS device selected.")
            return

        if device_name in self.device_workers:
            self.device_workers[device_name].stop()
            self.device_workers[device_name].join(timeout=3.0)
            self.device_workers.pop(device_name, None)

        if device_name in self.heartbeat_workers:
            self.heartbeat_workers[device_name].stop()
            self.heartbeat_workers[device_name].join(timeout=3.0)
            self.heartbeat_workers.pop(device_name, None)

        self._stop_bms_csv_for_device(device_name)

        self.devices = [d for d in self.devices if d.get("name") != device_name]
        for cluster in self.site.clusters:
            cluster.bms_devices = [dev for dev in cluster.bms_devices if dev.name != device_name]

        row = self.device_rows.pop(device_name, None)
        if row is not None:
            self.device_table.removeRow(row)
            self.device_rows = {}
            for r in range(self.device_table.rowCount()):
                item = self.device_table.item(r, 0)
                if item:
                    self.device_rows[item.text()] = r

        combos = [self.curve_device_combo, self.detail_device_combo, self.alarm_device_combo, self.control_device_combo]
        if hasattr(self, "driver_points_device_combo"):
            combos.append(self.driver_points_device_combo)
        for combo in combos:
            idx = combo.findText(device_name)
            if idx >= 0:
                combo.removeItem(idx)

        if hasattr(self, "task_status_store"):
            self.task_status_store.remove(device_name)
            self.refresh_task_status_view()

        self.latest_snapshots.pop(device_name, None)
        self.recent_buffers.pop(device_name, None)
        self.series_buffers.pop(device_name, None)
        self.sample_index.pop(device_name, None)

        self.current_curve_device = self.curve_device_combo.currentText() or None
        self.current_detail_device = self.detail_device_combo.currentText() or None
        self.current_alarm_device = self.alarm_device_combo.currentText() or None
        self.current_control_device = self.control_device_combo.currentText() or None

        self.save_devices_to_default()
        self.save_site_config()
        self.refresh_site_view()
        self.refresh_global_status_bar()
        self.log(f"[INFO] Removed BMS device: {device_name}")

    def save_devices_to_default(self) -> None:
        default_path = self.get_profile_path("devices.json")
        with open(default_path, "w", encoding="utf-8") as f:
            json.dump(self.devices, f, ensure_ascii=False, indent=2)

    def _ensure_bms_recorders(self, dev: dict) -> None:
        """Create BMS CSV/alarm recorders if missing.

        This keeps CSV output alive for both Start All and single-device start.
        """
        name = dev["name"]
        output_dir = Path(dev.get("output_dir") or str(self.get_profile_path("output")))
        output_dir.mkdir(parents=True, exist_ok=True)
        if name not in self.recorders:
            self.recorders[name] = AsyncRecorderProxy(
                CsvRecorder(output_dir=output_dir, device_name=name)
            )
        if name not in self.alarm_recorders:
            self.alarm_recorders[name] = AsyncRecorderProxy(
                AlarmRecorder(output_dir=output_dir, device_name=name)
            )

    def _selected_bms_name_or_all(self) -> list[str]:
        """Return selected BMS name, or all configured BMS names if no row is selected."""
        names: list[str] = []
        row = self.device_table.currentRow() if hasattr(self, "device_table") else -1
        if row >= 0:
            item = self.device_table.item(row, 0)
            if item and item.text().strip():
                names = [item.text().strip()]
        if not names:
            names = [str(d.get("name", "")).strip() for d in self.devices if d.get("name")]
        return [n for n in names if n]

    def update_bms_csv_status_label(self) -> None:
        active = sorted(getattr(self, "bms_csv_recording_devices", set()))
        label = getattr(self, "bms_csv_status_label", None)
        if label is None:
            return
        if active:
            shown = ", ".join(active[:3])
            if len(active) > 3:
                shown += f" +{len(active)-3}"
            label.setText(f"BMS CSV: Recording ON ({shown})")
            label.setStyleSheet("color: #16803a; font-weight: 700;")
        else:
            label.setText("BMS CSV: Recording OFF")
            label.setStyleSheet("color: #777; font-weight: 600;")

    def start_bms_csv_recording(self) -> None:
        names = self._selected_bms_name_or_all()
        if not names:
            QMessageBox.information(self, "Info", "No BMS device configured.")
            return
        started = []
        for name in names:
            dev = next((d for d in self.devices if d.get("name") == name), None)
            if not dev:
                continue
            self._ensure_bms_recorders(dev)
            self.bms_csv_recording_devices.add(name)
            started.append(name)
        if started:
            dirs = []
            for name in started:
                dev = next((d for d in self.devices if d.get("name") == name), {})
                dirs.append(str(dev.get("output_dir") or self.get_profile_path("output")))
            self.update_bms_csv_status_label()
            self.log(f"[CSV] BMS CSV recording ON: {', '.join(started)}")
            self.log(f"[CSV] BMS CSV output dir(s): {', '.join(sorted(set(dirs)))}")
            self.statusBar().showMessage(f"BMS CSV recording ON: {', '.join(started)}", 5000)
        else:
            self.update_bms_csv_status_label()
            QMessageBox.warning(self, "Warning", "No valid BMS selected for CSV recording.")

    def _stop_bms_csv_for_device(self, name: str) -> None:
        self.bms_csv_recording_devices.discard(name)
        for mapping in [self.recorders, self.alarm_recorders]:
            obj = mapping.pop(name, None)
            if obj:
                try:
                    obj.close()
                except Exception:
                    pass
        self.update_bms_csv_status_label()

    def stop_bms_csv_recording(self) -> None:
        names = self._selected_bms_name_or_all()
        if not names:
            names = list(getattr(self, "bms_csv_recording_devices", set()))
        stopped = []
        for name in names:
            if name in getattr(self, "bms_csv_recording_devices", set()) or name in self.recorders or name in self.alarm_recorders:
                self._stop_bms_csv_for_device(name)
                stopped.append(name)
        self.update_bms_csv_status_label()
        if stopped:
            self.log(f"[CSV] BMS CSV recording OFF: {', '.join(stopped)}")
            self.statusBar().showMessage(f"BMS CSV recording OFF: {', '.join(stopped)}", 5000)
        else:
            self.log("[CSV] No active BMS CSV recording to stop.")

    def start_device_by_name(self, name: str) -> None:
        dev = next((d for d in self.devices if d.get("name") == name), None)
        if not dev:
            QMessageBox.warning(self, "Warning", f"BMS device not found: {name}")
            return
        if name in self.device_workers:
            self.log(f"[INFO] BMS already running: {name}")
            return

        try:
            client = create_bms_client(dev, fake_mode=self.fake_mode)
        except Exception as exc:
            QMessageBox.critical(self, "BMS Start Failed", f"Failed to create BMS client for {name}:\n{exc}")
            self.log(f"[ERROR] Failed to create BMS client for {name}: {exc}")
            return
        start_index = len(self.device_workers)
        initial_delay = start_index * float(getattr(self, "worker_start_stagger_seconds", 0.25))
        worker = DeviceWorker(
            device_name=name,
            client=client,
            interval=float(dev.get("interval", 2.0)),
            callback=lambda dn, data: self.bridge.data_received.emit(dn, data),
            error_callback=lambda dn, err: self.bridge.error_received.emit(dn, err),
            status_callback=lambda dn, status: self.bridge.task_status_received.emit(dn, status),
            initial_delay=initial_delay,
        )
        self.device_workers[name] = worker
        self.on_task_status_received(name, {"status": "Scheduled", "last_message": f"Start delay {initial_delay:.1f}s"})
        worker.start()
        row = self.device_rows.get(name)
        if row is not None and self.device_table.item(row, 11):
            self.device_table.item(row, 11).setText("Running")
        self.last_sampling_status = "Running"
        self.refresh_global_status_bar()
        self.log(f"[INFO] Started BMS device: {name}")

    def stop_device_by_name(self, name: str) -> None:
        worker = self.device_workers.pop(name, None)
        if worker:
            worker.stop()
            worker.join(timeout=3.0)
        hb_worker = self.heartbeat_workers.pop(name, None)
        if hb_worker:
            hb_worker.stop()
            hb_worker.join(timeout=3.0)
        hv_worker = self.hv_workers.pop(name, None)
        if hv_worker:
            hv_worker.stop()
            hv_worker.join(timeout=3.0)
        self._stop_bms_csv_for_device(name)
        row = self.device_rows.get(name)
        if row is not None:
            stopped_item = QTableWidgetItem("Stopped")
            self._set_table_item_color(stopped_item, "Stopped")
            self.device_table.setItem(row, 11, stopped_item)
        if hasattr(self, "task_status_store"):
            self.on_task_status_received(name, {"status": "Stopped", "last_message": "Stopped by user"})
        self.refresh_global_status_bar()
        self.log(f"[INFO] Stopped BMS device: {name}")

    def start_selected_device(self) -> None:
        row = self.device_table.currentRow() if hasattr(self, "device_table") else -1
        if row < 0:
            QMessageBox.warning(self, "Warning", "Select one BMS device first.")
            return
        item = self.device_table.item(row, 0)
        if not item:
            return
        self.start_device_by_name(item.text())

    def stop_selected_device(self) -> None:
        row = self.device_table.currentRow() if hasattr(self, "device_table") else -1
        if row < 0:
            QMessageBox.warning(self, "Warning", "Select one BMS device first.")
            return
        item = self.device_table.item(row, 0)
        if not item:
            return
        self.stop_device_by_name(item.text())

    def start_all(self) -> None:
        if not self.devices:
            QMessageBox.information(self, "Info", "No devices configured.")
            return

        for dev in self.devices:
            self.start_device_by_name(dev["name"])

        self.last_sampling_status = "Running"
        self.refresh_global_status_bar()
        self.log("[INFO] Started all BMS devices.")

    def stop_all(self) -> None:
        for _, worker in list(self.device_workers.items()):
            worker.stop()
            worker.join(timeout=3.0)
        self.device_workers.clear()
        if hasattr(self, "task_status_store"):
            for dev in self.devices:
                self.on_task_status_received(dev["name"], {"status": "Stopped", "last_message": "Stopped by user"})

        for _, hb_worker in list(self.heartbeat_workers.items()):
            hb_worker.stop()
            hb_worker.join(timeout=3.0)
        self.heartbeat_workers.clear()

        for _, hv_worker in list(self.hv_workers.items()):
            hv_worker.stop()
            hv_worker.join(timeout=3.0)
        self.hv_workers.clear()

        if hasattr(self, "stop_cluster_strategy"):
            try:
                for _cluster_name in list(getattr(self, "cluster_strategy_workers", {}).keys()):
                    if hasattr(self, "cluster_strategy_combo"):
                        self.cluster_strategy_combo.setCurrentText(_cluster_name)
                    self.stop_cluster_strategy()
            except Exception as exc:
                self.log(f"[WARN] Stop cluster strategy skipped: {exc}")

        if hasattr(self, "stop_all_pcs_polling"):
            try:
                self.stop_all_pcs_polling()
            except Exception as exc:
                self.log(f"[WARN] Stop all PCS polling skipped: {exc}")
        if hasattr(self, "fleet_manager"):
            try:
                stopped = self.fleet_manager.stop()
                if stopped:
                    self.log(f"[INFO] Stopped fleet heartbeat workers: {stopped}")
            except Exception as exc:
                self.log(f"[WARN] Stop fleet workers skipped: {exc}")

        for dev_name in list(getattr(self, "bms_csv_recording_devices", set())):
            self._stop_bms_csv_for_device(dev_name)

        for dev in self.devices:
            row = self.device_rows[dev["name"]]
            stopped_item = QTableWidgetItem("Stopped")
            self._set_table_item_color(stopped_item, "Stopped")
            self.device_table.setItem(row, 11, stopped_item)

        self.heartbeat_state_label.setText("Stopped")
        self.last_sampling_status = "Stopped"
        self.last_heartbeat_status = "Stopped"
        self.last_hv_status = "Idle"
        self.refresh_global_status_bar()
        self.log("[INFO] Stopped all devices.")

    def save_devices(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save devices",
            str(self.get_profile_path("devices.json")),
            "JSON Files (*.json)",
        )
        if not path:
            return

        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.devices, f, ensure_ascii=False, indent=2)

        self.log(f"[INFO] Saved device config to: {path}")
        default_path = self.get_profile_path("devices.json")
        with open(default_path, "w", encoding="utf-8") as f:
            json.dump(self.devices, f, ensure_ascii=False, indent=2)

        self.log(f"[INFO] Updated default device config: {default_path}")

    def load_devices(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load devices",
            str(self.current_profile_dir),
            "JSON Files (*.json)",
        )
        if not path:
            return

        self._load_devices_from_path(Path(path))
        self.log(f"[INFO] Loaded device config from: {path}")

    def _load_devices_from_path(self, path: Path) -> None:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.devices.clear()
        self.device_rows.clear()
        self.device_table.setRowCount(0)

        self.curve_device_combo.clear()
        if hasattr(self, "driver_points_device_combo"):
            self.driver_points_device_combo.clear()
        self.detail_device_combo.clear()
        self.alarm_device_combo.clear()
        self.control_device_combo.clear()

        self.current_curve_device = None
        self.current_detail_device = None
        self.current_alarm_device = None
        self.current_control_device = None

        self.default_cluster.bms_devices.clear()

        self._loading_devices_from_config = True
        try:
            for dev in data:
                self.name_edit.setText(dev.get("name", ""))
                self.host_edit.setText(dev.get("host", ""))
                self.port_spin.setValue(int(dev.get("port", 502)))
                self.unit_spin.setValue(int(dev.get("unit_id", 1)))
                self.interval_spin.setValue(float(dev.get("interval", 2.0)))
                if hasattr(self, "bms_fake_scenario_combo"):
                    self.bms_fake_scenario_combo.setCurrentText(str(dev.get("fake_scenario", "normal")))
                if hasattr(self, "bms_profile_combo"):
                    idx = self.bms_profile_combo.findData(str(dev.get("profile", "catl_v22")))
                    if idx >= 0:
                        self.bms_profile_combo.setCurrentIndex(idx)
                self.output_dir_edit.setText(dev.get("output_dir", str(self.get_profile_path("output"))))
                self.add_device()
        finally:
            self._loading_devices_from_config = False

    def handle_open_output_folder(self) -> None:
        import os
        import subprocess
        import sys
        from pathlib import Path

        if self.devices:
            output_dir = Path(self.devices[0].get("output_dir", str(self.get_profile_path("output"))))
        else:
            output_dir = self.get_profile_path("output")

        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            if sys.platform.startswith("win"):
                os.startfile(str(output_dir))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(output_dir)])
            else:
                subprocess.Popen(["xdg-open", str(output_dir)])

            self.log(f"[INFO] Opened output folder: {output_dir}")

        except Exception as exc:
            self.log(f"[ERROR] Failed to open output folder: {exc}")

    def save_site_config(self) -> None:
        # Persist the selected Strategy UI values before serializing the site.
        # This restores the operator's project setup after restarting the app/EXE,
        # but it does NOT auto-connect devices or auto-start any strategy.
        try:
            if hasattr(self, "capture_selected_cluster_strategy_from_ui"):
                self.capture_selected_cluster_strategy_from_ui()
        except Exception as exc:
            self.log(f"[WARN] Could not capture current cluster strategy UI values: {exc}")

        data = {
            "site": self.site.name,
            "clusters": [],
        }

        for cluster in self.site.clusters:
            cluster_data = {
                "name": cluster.name,
                "bms_devices": [dev.name for dev in cluster.bms_devices],
                "pcs_device": cluster.pcs_device.name if cluster.pcs_device else "",
                "pcs_devices": [pcs.name for pcs in getattr(cluster, "pcs_devices", [])],
                "allocation_mode": getattr(cluster, "allocation_mode", "equal_split"),
                "fault_strategy": getattr(cluster, "fault_strategy", "stop_all"),
            }
            strategy = getattr(cluster, "strategy", None)
            if isinstance(strategy, dict):
                cluster_data["strategy"] = strategy
            data["clusters"].append(cluster_data)

        path = self.get_profile_path("site_config.json")

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        self.log(f"[INFO] Saved site config: {path}")

    def load_site_config(self) -> None:
        path = self.get_profile_path("site_config.json")

        if not path.exists():
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.log(f"[INFO] Loaded site config: {path}")

            # 先只加载 cluster 名称和关系，后面再做完整 UI 管理
            # 当前版本主要用于检查，不覆盖现有 self.devices
            self.site.name = data.get("site", self.site.name)
            clusters_data = data.get("clusters", [])

            if clusters_data:
                from .models import Cluster, Device

                self.site.clusters.clear()

                for i, cluster_data in enumerate(clusters_data):
                    cluster = Cluster(
                        name=cluster_data.get("name", f"Cluster-{i + 1}")
                    )

                    cluster.allocation_mode = cluster_data.get("allocation_mode", getattr(cluster, "allocation_mode", "equal_split"))
                    cluster.fault_strategy = cluster_data.get("fault_strategy", getattr(cluster, "fault_strategy", "stop_all"))
                    # Strategy settings are project configuration only. Restore
                    # them into UI/runtime data, but never auto-start strategy.
                    cluster.strategy = dict(cluster_data.get("strategy") or {})
                    pcs_names = cluster_data.get("pcs_devices") or ([cluster_data.get("pcs_device", "")] if cluster_data.get("pcs_device", "") else [])
                    for pcs_name in pcs_names:
                        if pcs_name:
                            cluster.pcs_devices.append(Device(
                                name=pcs_name,
                                device_type="PCS",
                                config=self.get_pcs_config_by_name(pcs_name),
                            ))

                    saved_bms_names = set(cluster_data.get("bms_devices", []))

                    for dev_cfg in self.devices:
                        dev_name = dev_cfg.get("name", "")
                        if dev_name in saved_bms_names:
                            cluster.bms_devices.append(
                                Device(
                                    name=dev_name,
                                    device_type="BMS",
                                    config=dev_cfg,
                                )
                            )

                    self.site.clusters.append(cluster)

                self.default_cluster = self.site.clusters[0]
            elif not self.site.clusters:
                self.site.clusters.append(self.default_cluster)


        except Exception as exc:

            self.log(f"[ERROR] Failed to load site config: {exc}")

        if hasattr(self, "site_cluster_table"):
            self.refresh_site_view()
        if hasattr(self, "pcs_device_table"):
            self.refresh_pcs_view()
        if hasattr(self, "strategy_editor"):
            self.refresh_strategy_view()
        if hasattr(self, "refresh_cluster_strategy_controls"):
            self.refresh_cluster_strategy_controls()
        if hasattr(self, "apply_selected_cluster_strategy_to_ui"):
            self.apply_selected_cluster_strategy_to_ui()
        if hasattr(self, "point_template_table"):
            self.refresh_point_template_view()

        if hasattr(self, "status_selected_device_label"):
            self.refresh_global_status_bar()

    def auto_load_startup_configs(self) -> None:
        try:
            self.startup_self_check_result = ensure_profile(self.current_profile_dir, resource_path("."))
        except Exception as exc:
            self.log(f"[ERROR] Startup self check failed: {exc}")

        try:
            self.pcs_config = self.load_pcs_config() or self.pcs_config
            if self.pcs_config:
                if "name" not in self.pcs_config and self.current_pcs_name:
                    self.pcs_config["name"] = self.current_pcs_name
                self.current_pcs_name = self.pcs_config.get("name", self.current_pcs_name)
                if self.current_pcs_name:
                    self.pcs_configs[self.current_pcs_name] = self.pcs_config
            self.alarm_parser.map_path = self.get_profile_path("alarm_map.json")
            self.alarm_parser.load()
            if hasattr(self, "strategy_engine"):
                self.strategy_engine.set_profile_dir(self.current_profile_dir)
                self.strategy_engine.load()
        except Exception as exc:
            self.log(f"[ERROR] Auto load profile common config failed: {exc}")

        devices_path = self.get_profile_path("devices.json")

        if devices_path.exists():
            try:
                self._load_devices_from_path(devices_path)
                self.log(f"[INFO] Auto loaded devices: {devices_path}")
            except Exception as exc:
                self.log(f"[ERROR] Auto load devices failed: {exc}")

        try:
            self.load_site_config()
        except Exception as exc:
            self.log(f"[ERROR] Auto load site config failed: {exc}")

        if hasattr(self, "site_cluster_table"):
            self.refresh_site_view()
        if hasattr(self, "pcs_device_table"):
            self.refresh_pcs_view()

        if hasattr(self, "status_selected_device_label"):
            self.refresh_global_status_bar()