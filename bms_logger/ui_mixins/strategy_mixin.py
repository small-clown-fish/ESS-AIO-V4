from __future__ import annotations

import json
import csv
import time
from collections import deque
from pathlib import Path
from typing import Any, Dict

from PySide6.QtCharts import QChart, QLineSeries
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem, QInputDialog
from PySide6.QtGui import QColor





class StrategyMixin:
    def refresh_strategy_view(self) -> None:
        if not hasattr(self, "strategy_editor"):
            return

        try:
            self.strategy_engine.set_profile_dir(self.current_profile_dir)
            data = self.strategy_engine.load()
            self.strategy_editor.setPlainText(json.dumps(data, ensure_ascii=False, indent=2))

            name = data.get("name", "-")
            version = data.get("version", "-")
            enabled = data.get("enabled", True)
            self.strategy_status_label.setText(
                f"Strategy: {name} | version={version} | enabled={enabled} | file={self.strategy_engine.strategy_path}"
            )

            if hasattr(self, "strategy_test_combo"):
                self.strategy_test_combo.blockSignals(True)
                self.strategy_test_combo.clear()
                for test in self.strategy_engine.fake_tests():
                    self.strategy_test_combo.addItem(str(test.get("name", "Unnamed")))
                self.strategy_test_combo.blockSignals(False)

        except Exception as exc:
            self.log(f"[ERROR] Failed to refresh strategy view: {exc}")

    def reload_strategy_config(self) -> None:
        try:
            self.strategy_engine.set_profile_dir(self.current_profile_dir)
            self.strategy_engine.load()
            self.refresh_strategy_view()
            self.log("[INFO] Strategy reloaded")
        except Exception as exc:
            QMessageBox.critical(self, "Strategy", f"Failed to reload strategy:\n{exc}")

    def save_strategy_from_editor(self) -> None:
        if not hasattr(self, "strategy_editor"):
            return

        try:
            data = json.loads(self.strategy_editor.toPlainText())
            errors = self.strategy_engine.validate(data)
            if errors:
                QMessageBox.warning(self, "Invalid Strategy", "\n".join(errors))
                return

            self.strategy_engine.save(data)
            self.refresh_strategy_view()
            self.log(f"[INFO] Strategy saved: {self.strategy_engine.strategy_path}")

        except Exception as exc:
            QMessageBox.critical(self, "Strategy", f"Failed to save strategy:\n{exc}")

    def import_strategy_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import strategy JSON",
            str(Path.cwd()),
            "JSON Files (*.json)",
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            errors = self.strategy_engine.validate(data)
            if errors:
                QMessageBox.warning(self, "Invalid Strategy", "\n".join(errors))
                return
            self.strategy_engine.save(data)
            self.refresh_strategy_view()
            self.log(f"[INFO] Strategy imported: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Strategy", f"Failed to import strategy:\n{exc}")

    def export_strategy_json(self) -> None:
        default_path = self.current_profile_dir / "strategy_export.json"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export strategy JSON",
            str(default_path),
            "JSON Files (*.json)",
        )
        if not path:
            return

        try:
            self.strategy_engine.save(json.loads(self.strategy_editor.toPlainText()))
            import shutil
            shutil.copy2(self.strategy_engine.strategy_path, Path(path))
            self.log(f"[INFO] Strategy exported: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Strategy", f"Failed to export strategy:\n{exc}")

    def reset_default_strategy(self) -> None:
        reply = QMessageBox.question(
            self,
            "Reset Strategy",
            "Reset current profile strategy.json to default?",
        )
        if reply != QMessageBox.Yes:
            return

        try:
            from .strategy_engine import DEFAULT_STRATEGY
            self.strategy_engine.save(DEFAULT_STRATEGY)
            self.refresh_strategy_view()
            self.log("[INFO] Strategy reset to default")
        except Exception as exc:
            QMessageBox.critical(self, "Strategy", f"Failed to reset strategy:\n{exc}")

    def _selected_strategy_fake_test(self) -> dict:
        if not hasattr(self, "strategy_test_combo"):
            return {}
        name = self.strategy_test_combo.currentText()
        for test in self.strategy_engine.fake_tests():
            if str(test.get("name", "")) == name:
                return test
        return {}

    def apply_selected_strategy_fake_test(self) -> None:
        test = self._selected_strategy_fake_test()
        if not test:
            QMessageBox.information(self, "Strategy Test", "No fake test selected.")
            return

        bms_scenario = str(test.get("bms_scenario", "normal"))
        pcs_scenario = str(test.get("pcs_scenario", "normal"))

        self.fake_mode = True
        if hasattr(self, "fake_mode_combo"):
            self.fake_mode_combo.setCurrentText("Fake")

        for dev in self.devices:
            dev["fake_scenario"] = bms_scenario

        for cfg in self.pcs_configs.values():
            cfg["fake_scenario"] = pcs_scenario

        try:
            self.save_devices_to_default()
            self.save_pcs_config()
            self.save_runtime_config()
        except Exception:
            pass

        if hasattr(self, "bms_fake_scenario_combo"):
            self.bms_fake_scenario_combo.setCurrentText(bms_scenario)
        if hasattr(self, "pcs_fake_scenario_combo"):
            self.pcs_fake_scenario_combo.setCurrentText(pcs_scenario)

        if hasattr(self, "strategy_test_result_text"):
            self.strategy_test_result_text.setPlainText(
                f"Applied fake test: {test.get('name')}\n"
                f"BMS scenario: {bms_scenario}\n"
                f"PCS scenario: {pcs_scenario}\n"
                "Mode switched to Fake. Use Start All to run the test."
            )

        self.log(
            f"[INFO] Strategy fake test applied: {test.get('name')} "
            f"(BMS={bms_scenario}, PCS={pcs_scenario})"
        )
        self.refresh_global_status_bar()

    def run_selected_strategy_fake_test(self) -> None:
        self.apply_selected_strategy_fake_test()
        self.start_all()

    def reset_fake_scenarios(self) -> None:
        for dev in self.devices:
            dev["fake_scenario"] = "normal"
        for cfg in self.pcs_configs.values():
            cfg["fake_scenario"] = "normal"

        try:
            self.save_devices_to_default()
            self.save_pcs_config()
        except Exception:
            pass

        if hasattr(self, "bms_fake_scenario_combo"):
            self.bms_fake_scenario_combo.setCurrentText("normal")
        if hasattr(self, "pcs_fake_scenario_combo"):
            self.pcs_fake_scenario_combo.setCurrentText("normal")
        if hasattr(self, "strategy_test_result_text"):
            self.strategy_test_result_text.setPlainText("Fake scenarios reset to normal.")

        self.log("[INFO] Fake scenarios reset to normal")

    # =========================
    # v3.0 Driver management
    # =========================

# =========================
# v3.11 Cluster charge/discharge strategy runtime
# =========================
def _cluster_strategy_cluster_names(self) -> list[str]:
    clusters = getattr(getattr(self, "site", None), "clusters", []) or []
    return [str(c.name) for c in clusters if getattr(c, "name", "")]


def _cluster_strategy_get_cluster(self, name: str):
    for cluster in getattr(getattr(self, "site", None), "clusters", []) or []:
        if str(getattr(cluster, "name", "")) == str(name):
            return cluster
    return None


def _cluster_strategy_refresh_controls(self) -> None:
    if not hasattr(self, "cluster_strategy_combo"):
        return
    current = self.cluster_strategy_combo.currentText()
    self.cluster_strategy_combo.blockSignals(True)
    self.cluster_strategy_combo.clear()
    names = self._cluster_strategy_cluster_names()
    self.cluster_strategy_combo.addItems(names)
    if current and current in names:
        self.cluster_strategy_combo.setCurrentText(current)
    elif names:
        self.cluster_strategy_combo.setCurrentText(names[0])
    self.cluster_strategy_combo.blockSignals(False)
    if hasattr(self, "apply_selected_cluster_strategy_to_ui"):
        self.apply_selected_cluster_strategy_to_ui()
    self.refresh_cluster_strategy_status_text()


def _cluster_strategy_status_line(self, name: str, state) -> str:
    allocation = getattr(state, "allocation", {}) or {}
    alloc_text = ", ".join(f"{k}={v:.1f}kW" for k, v in allocation.items()) or "-"
    return (
        f"{name}: {getattr(state, 'status', '-')}; "
        f"target={getattr(state, 'target_signed_kw', 0):.1f}kW; "
        f"current={getattr(state, 'current_signed_kw', 0):.1f}kW; "
        f"allowed={getattr(state, 'allowed_total_kw', 0):.1f}kW; "
        f"PCS=[{alloc_text}]; reason={getattr(state, 'last_reason', '')}"
    )


def _cluster_strategy_refresh_status_text(self) -> None:
    if not hasattr(self, "cluster_strategy_status_text"):
        return
    states = getattr(self, "cluster_strategy_states", {})
    workers = getattr(self, "cluster_strategy_workers", {})
    lines: list[str] = []
    for name, state in states.items():
        lines.append(self._cluster_strategy_status_line(name, state))
    if not lines:
        cluster_name = self.cluster_strategy_combo.currentText() if hasattr(self, "cluster_strategy_combo") else ""
        cluster = self._cluster_strategy_get_cluster(cluster_name) if cluster_name else None
        if cluster is not None:
            bms = [d.name for d in getattr(cluster, "bms_devices", [])]
            pcs = [d.name for d in getattr(cluster, "pcs_devices", [])]
            lines.append(f"Selected {cluster_name}: BMS={bms or '-'} PCS={pcs or '-'} running={cluster_name in workers}")
        else:
            lines.append("No cluster selected. Configure Site / Cluster first.")
    self.cluster_strategy_status_text.setPlainText("\n".join(lines))


def _cluster_strategy_on_state(self, cluster_name: str, state) -> None:
    if not hasattr(self, "cluster_strategy_states"):
        self.cluster_strategy_states = {}
    self.cluster_strategy_states[cluster_name] = state
    try:
        self.bridge.task_status_received.emit(cluster_name, {
            "status": f"ClusterStrategy:{getattr(state, 'status', '-')}",
            "last_message": getattr(state, "last_reason", ""),
            "device_type": "Cluster",
        })
    except Exception:
        pass


def _cluster_strategy_dispatch_power(self, pcs_name: str, power_kw: float, label: str = "cluster_strategy") -> bool:
    # Reuse persistent PCS worker / command queue. If the operator has not started PCS
    # heartbeats yet, start the selected PCS worker before queueing commands.
    try:
        self.fleet_manager.start_pcs_command_workers(
            [pcs_name],
            lambda name: self.pcs_controller.create_client_for_pcs_name(name),
            interval_s=float(getattr(self, "heartbeat_interval", 1.0)),
        )
        count = self.fleet_manager.enqueue_pcs_command(
            [pcs_name],
            "set_active_power",
            float(power_kw),
            label=f"{label}: set_active_power={float(power_kw):.1f}kW",
        )
        return count > 0
    except Exception as exc:
        self.control_log(f"[CLUSTER_STRATEGY][ERROR] dispatch {pcs_name} {power_kw}kW failed: {exc}")
        return False


def _cluster_strategy_start(self) -> None:
    from ..cluster_strategy_runtime import ClusterStrategySettings, ClusterStrategyWorker
    from PySide6.QtWidgets import QMessageBox

    cluster_name = self.cluster_strategy_combo.currentText().strip() if hasattr(self, "cluster_strategy_combo") else ""
    cluster = self._cluster_strategy_get_cluster(cluster_name)
    if cluster is None:
        QMessageBox.warning(self, "Cluster Strategy", "No cluster selected. Configure Site / Cluster first.")
        return
    if cluster_name in getattr(self, "cluster_strategy_workers", {}):
        QMessageBox.warning(self, "Cluster Strategy", f"Strategy already running: {cluster_name}")
        return

    bms_names = [d.name for d in getattr(cluster, "bms_devices", []) if getattr(d, "name", "")]
    pcs_names = [d.name for d in getattr(cluster, "pcs_devices", []) if getattr(d, "name", "")]
    if not bms_names or not pcs_names:
        QMessageBox.warning(self, "Cluster Strategy", f"Cluster needs at least one BMS and one PCS.\nBMS={bms_names}\nPCS={pcs_names}")
        return

    # Validate BMS data before starting. Strategy must not create or touch BMS
    # Modbus connections; it only consumes snapshots from the normal BMS polling workers.
    snapshots = getattr(self, "latest_snapshots", {}) or {}
    timeout_s = float(self.cluster_strategy_timeout_spin.value()) if hasattr(self, "cluster_strategy_timeout_spin") else 5.0
    stale: list[str] = []
    missing: list[str] = []
    now_wall = time.time()
    for bms_name in bms_names:
        snap = snapshots.get(bms_name)
        if not snap:
            missing.append(bms_name)
            continue
        ts = snap.get("_received_ts") or snap.get("received_ts") or snap.get("last_ok_ts")
        try:
            age = now_wall - float(ts)
        except Exception:
            age = timeout_s + 999.0
        if age > timeout_s:
            stale.append(f"{bms_name}({age:.1f}s)")
    if missing or stale:
        QMessageBox.warning(
            self,
            "Cluster Strategy",
            "BMS data is not ready. Start BMS monitoring first and wait for fresh data.\n"
            f"Missing: {missing or '-'}\n"
            f"Stale: {stale or '-'}\n"
            f"Timeout: {timeout_s:.1f}s",
        )
        return

    # Ensure PCS persistent command workers exist. PCS heartbeat is intentionally
    # disabled during current site testing; workers are used only as serial queues.
    self.fleet_manager.start_pcs_command_workers(
        pcs_names,
        lambda name: self.pcs_controller.create_client_for_pcs_name(name),
        interval_s=float(getattr(self, "heartbeat_interval", 1.0)),
    )

    # Strong pre-start validation: command workers must really connect before the
    # strategy enters RUNNING. Otherwise enqueue_pcs_command() can appear to
    # succeed while no power is actually written to the PCS.
    deadline = time.time() + 2.5
    online_pcs: set[str] = set()
    while time.time() < deadline:
        try:
            fleet_snaps = self.fleet_manager.snapshots()
            online_pcs = {
                key.split(":", 1)[1]
                for key, snap in fleet_snaps.items()
                if key.startswith("PCS:") and key.split(":", 1)[1] in pcs_names and snap.get("online")
            }
        except Exception:
            online_pcs = set()
        if len(online_pcs) >= len(pcs_names):
            break
        time.sleep(0.1)
    missing_pcs = [name for name in pcs_names if name not in online_pcs]
    if missing_pcs:
        QMessageBox.warning(
            self,
            "Cluster Strategy",
            "PCS command worker is not online. Strategy was not started.\n"
            "Connect/check PCS first, then start strategy.\n\n"
            f"Offline PCS: {missing_pcs}",
        )
        return

    # Persist latest UI values into the selected cluster before starting and saving.
    try:
        if hasattr(self, "capture_selected_cluster_strategy_from_ui"):
            self.capture_selected_cluster_strategy_from_ui()
            self.save_site_config()
    except Exception as exc:
        self.control_log(f"[CLUSTER_STRATEGY][WARN] Could not save strategy settings before start: {exc}")

    positive_text = self.cluster_strategy_positive_combo.currentText() if hasattr(self, "cluster_strategy_positive_combo") else "+ = discharge"
    settings = ClusterStrategySettings(
        cluster_name=cluster_name,
        mode=self.cluster_strategy_mode_combo.currentText().strip().lower() if hasattr(self, "cluster_strategy_mode_combo") else "discharge",
        target_power_kw=float(self.cluster_strategy_target_spin.value()) if hasattr(self, "cluster_strategy_target_spin") else 0.0,
        ramp_step_kw=float(self.cluster_strategy_ramp_step_spin.value()) if hasattr(self, "cluster_strategy_ramp_step_spin") else 50.0,
        ramp_interval_s=float(self.cluster_strategy_ramp_interval_spin.value()) if hasattr(self, "cluster_strategy_ramp_interval_spin") else 5.0,
        monitor_interval_s=1.0,
        bms_response_timeout_s=float(self.cluster_strategy_timeout_spin.value()) if hasattr(self, "cluster_strategy_timeout_spin") else 5.0,
        charge_stop_max_cell_mv=float(self.cluster_strategy_charge_cutoff_spin.value()) if hasattr(self, "cluster_strategy_charge_cutoff_spin") else 3550.0,
        discharge_stop_min_cell_mv=float(self.cluster_strategy_discharge_cutoff_spin.value()) if hasattr(self, "cluster_strategy_discharge_cutoff_spin") else 2800.0,
        positive_power_means="charge" if "charge" in positive_text and "discharge" not in positive_text.split("=")[-1] else "discharge",
        allocation_mode=self.cluster_strategy_allocation_combo.currentText().strip() if hasattr(self, "cluster_strategy_allocation_combo") else getattr(cluster, "allocation_mode", "equal_split"),
        timeout_action=self.cluster_strategy_timeout_action_combo.currentText().strip() if hasattr(self, "cluster_strategy_timeout_action_combo") else "immediate_zero",
    )

    worker = ClusterStrategyWorker(
        settings=settings,
        bms_names=bms_names,
        pcs_names=pcs_names,
        pcs_configs=getattr(self, "pcs_configs", {}),
        snapshot_provider=lambda name: getattr(self, "latest_snapshots", {}).get(name),
        dispatch_power=self._cluster_strategy_dispatch_power,
        log=lambda msg: self.control_log(msg),
        state_callback=self._cluster_strategy_on_state,
    )
    self.cluster_strategy_workers[cluster_name] = worker
    worker.start()
    self.control_log(f"[CLUSTER_STRATEGY] Started {cluster_name}: target={settings.target_power_kw}kW, BMS={bms_names}, PCS={pcs_names}")
    self.refresh_cluster_strategy_status_text()


def _cluster_strategy_stop(self) -> None:
    cluster_name = self.cluster_strategy_combo.currentText().strip() if hasattr(self, "cluster_strategy_combo") else ""
    workers = getattr(self, "cluster_strategy_workers", {})
    if cluster_name:
        selected = [(cluster_name, workers.pop(cluster_name, None))]
    else:
        selected = list(workers.items())
        workers.clear()
    stopped = []
    for name, worker in selected:
        if worker is None:
            continue
        try:
            worker.stop()
            worker.join(timeout=3.0)
            stopped.append(name)
        except Exception as exc:
            self.control_log(f"[CLUSTER_STRATEGY][ERROR] Stop {name} failed: {exc}")
    if stopped:
        self.control_log(f"[CLUSTER_STRATEGY] Stopped: {', '.join(stopped)}")
    self.refresh_cluster_strategy_status_text()


# Attach methods to StrategyMixin without disturbing older definitions above.
StrategyMixin._cluster_strategy_cluster_names = _cluster_strategy_cluster_names
StrategyMixin._cluster_strategy_get_cluster = _cluster_strategy_get_cluster
StrategyMixin.refresh_cluster_strategy_controls = _cluster_strategy_refresh_controls
StrategyMixin.refresh_cluster_strategy_status_text = _cluster_strategy_refresh_status_text
StrategyMixin._cluster_strategy_status_line = _cluster_strategy_status_line
StrategyMixin._cluster_strategy_on_state = _cluster_strategy_on_state
StrategyMixin._cluster_strategy_dispatch_power = _cluster_strategy_dispatch_power
StrategyMixin.start_cluster_strategy = _cluster_strategy_start
StrategyMixin.stop_cluster_strategy = _cluster_strategy_stop
