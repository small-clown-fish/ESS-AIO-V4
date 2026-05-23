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





class SiteMixin:
    def get_cluster_by_device(self, device_name: str):
        if not hasattr(self, "site"):
            return None

        for cluster in self.site.clusters:
            for dev in cluster.bms_devices:
                if dev.name == device_name:
                    return cluster

            for pcs in getattr(cluster, "pcs_devices", []):
                if pcs.name == device_name:
                    return cluster

        return None

    def refresh_site_view(self) -> None:
        if not hasattr(self, "site_cluster_table"):
            return

        self.site_name_label.setText(f"Site: {self.site.name}")
        if hasattr(self, "active_cluster_combo"):
            current = self.default_cluster.name if hasattr(self, "default_cluster") else ""

            self.active_cluster_combo.blockSignals(True)
            self.active_cluster_combo.clear()

            for cluster in self.site.clusters:
                self.active_cluster_combo.addItem(cluster.name)

            if current:
                self.active_cluster_combo.setCurrentText(current)

            self.active_cluster_combo.blockSignals(False)
        if hasattr(self, "cluster_binding_target_combo"):
            current = self.cluster_binding_target_combo.currentText()
            fallback = self.default_cluster.name if hasattr(self, "default_cluster") else ""

            self.cluster_binding_target_combo.blockSignals(True)
            self.cluster_binding_target_combo.clear()

            for cluster in self.site.clusters:
                self.cluster_binding_target_combo.addItem(cluster.name)

            if current:
                self.cluster_binding_target_combo.setCurrentText(current)
            elif fallback:
                self.cluster_binding_target_combo.setCurrentText(fallback)

            self.cluster_binding_target_combo.blockSignals(False)

        if hasattr(self, "move_bms_target_cluster_combo"):
            current = self.move_bms_target_cluster_combo.currentText()

            self.move_bms_target_cluster_combo.blockSignals(True)
            self.move_bms_target_cluster_combo.clear()

            for cluster in self.site.clusters:
                self.move_bms_target_cluster_combo.addItem(cluster.name)

            if current:
                self.move_bms_target_cluster_combo.setCurrentText(current)

            self.move_bms_target_cluster_combo.blockSignals(False)
        if hasattr(self, "cluster_dispatch_combo"):
            current = self.cluster_dispatch_combo.currentText()
            self.cluster_dispatch_combo.blockSignals(True)
            self.cluster_dispatch_combo.clear()
            for cluster in self.site.clusters:
                self.cluster_dispatch_combo.addItem(cluster.name)
            if current:
                self.cluster_dispatch_combo.setCurrentText(current)
            elif hasattr(self, "default_cluster"):
                self.cluster_dispatch_combo.setCurrentText(self.default_cluster.name)
            self.cluster_dispatch_combo.blockSignals(False)
        if hasattr(self, "cluster_pcs_combo"):
            current_pcs = self.default_cluster.pcs_device.name if self.default_cluster.pcs_device else self.current_pcs_name
            self.cluster_pcs_combo.blockSignals(True)
            self.cluster_pcs_combo.clear()
            for pcs_name in sorted(self.pcs_configs.keys()) or [self.current_pcs_name]:
                self.cluster_pcs_combo.addItem(pcs_name)
            self.cluster_pcs_combo.setCurrentText(current_pcs)
            self.cluster_pcs_combo.blockSignals(False)
        if hasattr(self, "site_name_edit"):
            self.site_name_edit.setText(self.site.name)
        if hasattr(self, "cluster_name_edit") and self.site.clusters:
            active = self.default_cluster if hasattr(self, "default_cluster") else self.site.clusters[0]
            self.cluster_name_edit.setText(active.name)
        self.site_cluster_table.setRowCount(0)

        for cluster in self.site.clusters:
            row = self.site_cluster_table.rowCount()
            self.site_cluster_table.insertRow(row)

            bms_names = ", ".join(dev.name for dev in cluster.bms_devices) or "-"
            pcs_name = ", ".join(pcs.name for pcs in getattr(cluster, "pcs_devices", [])) or "-"

            values = [
                cluster.name,
                bms_names,
                pcs_name,
                str(len(cluster.bms_devices)),
            ]

            for col, value in enumerate(values):
                self.site_cluster_table.setItem(row, col, QTableWidgetItem(value))

    def apply_cluster_name(self) -> None:
        if not hasattr(self, "cluster_name_edit"):
            return

        new_name = self.cluster_name_edit.text().strip()
        if not new_name:
            QMessageBox.warning(self, "Warning", "Cluster name cannot be empty.")
            return

        if not hasattr(self, "default_cluster"):
            return

        old_name = self.default_cluster.name
        self.default_cluster.name = new_name

        self.log(f"[INFO] Cluster renamed: {old_name} -> {new_name}")

        self.save_site_config()
        self.refresh_site_view()
        self.refresh_overview()

    def apply_site_name(self) -> None:
        if not hasattr(self, "site_name_edit"):
            return

        new_name = self.site_name_edit.text().strip()
        if not new_name:
            QMessageBox.warning(self, "Warning", "Site name cannot be empty.")
            return

        old_name = self.site.name
        self.site.name = new_name

        self.log(f"[INFO] Site renamed: {old_name} -> {new_name}")

        self.save_site_config()
        self.refresh_site_view()
        self.refresh_overview()

    def _get_selected_binding_cluster(self):
        """Return the cluster selected in the PCS Binding Cluster combo.

        Older versions always used self.default_cluster, which made every PCS
        bind to Cluster-1 after refresh. This helper makes the target explicit.
        """
        target_name = ""
        if hasattr(self, "cluster_binding_target_combo"):
            target_name = self.cluster_binding_target_combo.currentText().strip()
        if not target_name and hasattr(self, "active_cluster_combo"):
            target_name = self.active_cluster_combo.currentText().strip()
        if not target_name and hasattr(self, "default_cluster"):
            target_name = self.default_cluster.name

        for cluster in getattr(self.site, "clusters", []):
            if cluster.name == target_name:
                return cluster
        return getattr(self, "default_cluster", None)

    def apply_cluster_pcs_binding(self) -> None:
        if not hasattr(self, "cluster_pcs_combo"):
            return

        pcs_name = self.cluster_pcs_combo.currentText().strip()
        if not pcs_name:
            QMessageBox.warning(self, "Warning", "PCS name cannot be empty.")
            return

        target_cluster = self._get_selected_binding_cluster()
        if target_cluster is None:
            QMessageBox.warning(self, "Warning", "Please select a target cluster first.")
            return

        from ..models import Device

        pcs_dev = Device(
            name=pcs_name,
            device_type="PCS",
            config=self.get_pcs_config_by_name(pcs_name),
        )

        # A PCS should normally belong to one cluster. Remove it from other
        # clusters first to avoid duplicated dispatch targets.
        for cluster in self.site.clusters:
            if cluster is target_cluster:
                continue
            if hasattr(cluster, "pcs_devices"):
                cluster.pcs_devices = [p for p in cluster.pcs_devices if p.name != pcs_name]

        if not hasattr(target_cluster, "pcs_devices"):
            target_cluster.pcs_devices = []
        if not any(p.name == pcs_name for p in target_cluster.pcs_devices):
            target_cluster.pcs_devices.append(pcs_dev)
            self.log(f"[INFO] Added PCS to cluster: {target_cluster.name} -> {pcs_name}")
        else:
            self.log(f"[INFO] PCS already bound to cluster: {target_cluster.name} -> {pcs_name}")

        self.save_site_config()
        self.refresh_site_view()
        self.refresh_overview()

    def remove_cluster_pcs_binding(self) -> None:
        if not hasattr(self, "cluster_pcs_combo"):
            return
        pcs_name = self.cluster_pcs_combo.currentText().strip()
        target_cluster = self._get_selected_binding_cluster()
        if not pcs_name or target_cluster is None or not hasattr(target_cluster, "pcs_devices"):
            return
        before = len(target_cluster.pcs_devices)
        target_cluster.pcs_devices = [p for p in target_cluster.pcs_devices if p.name != pcs_name]
        if len(target_cluster.pcs_devices) != before:
            self.log(f"[INFO] Removed PCS from cluster: {target_cluster.name} -> {pcs_name}")
            self.save_site_config()
            self.refresh_site_view()
            self.refresh_overview()

    def on_active_cluster_changed(self, cluster_name: str) -> None:
        if not cluster_name:
            return

        for cluster in self.site.clusters:
            if cluster.name == cluster_name:
                self.default_cluster = cluster

                if hasattr(self, "cluster_name_edit"):
                    self.cluster_name_edit.setText(cluster.name)

                if hasattr(self, "cluster_binding_target_combo"):
                    self.cluster_binding_target_combo.setCurrentText(cluster.name)

                if hasattr(self, "cluster_pcs_combo"):
                    pcs_name = ""
                    if getattr(cluster, "pcs_devices", []):
                        pcs_name = cluster.pcs_devices[0].name
                    elif getattr(cluster, "pcs_device", None):
                        pcs_name = cluster.pcs_device.name
                    if pcs_name:
                        if self.cluster_pcs_combo.findText(pcs_name) < 0:
                            self.cluster_pcs_combo.addItem(pcs_name)
                        self.cluster_pcs_combo.setCurrentText(pcs_name)

                self.log(f"[INFO] Active cluster changed: {cluster_name}")
                return

    def move_bms_to_cluster(self) -> None:
        if not hasattr(self, "move_bms_name_edit"):
            return

        bms_name = self.move_bms_name_edit.text().strip()
        target_cluster_name = self.move_bms_target_cluster_combo.currentText().strip()

        if not bms_name:
            QMessageBox.warning(self, "Warning", "BMS name cannot be empty.")
            return

        if not target_cluster_name:
            QMessageBox.warning(self, "Warning", "Target cluster cannot be empty.")
            return

        target_cluster = None
        moving_device = None

        for cluster in self.site.clusters:
            for dev in list(cluster.bms_devices):
                if dev.name == bms_name:
                    moving_device = dev
                    cluster.bms_devices.remove(dev)
                    break

            if cluster.name == target_cluster_name:
                target_cluster = cluster

        if target_cluster is None:
            QMessageBox.warning(self, "Warning", f"Target cluster '{target_cluster_name}' not found.")
            return

        if moving_device is None:
            QMessageBox.warning(self, "Warning", f"BMS '{bms_name}' not found.")
            return

        target_cluster.bms_devices.append(moving_device)

        self.log(f"[INFO] Moved BMS {bms_name} to {target_cluster_name}")

        self.save_site_config()
        self.refresh_site_view()
        self.refresh_overview()




# =========================
# Site config management helpers
# =========================
def _site_selected_cluster_name(self) -> str:
    if hasattr(self, "active_cluster_combo") and self.active_cluster_combo.currentText().strip():
        return self.active_cluster_combo.currentText().strip()
    if hasattr(self, "cluster_binding_target_combo") and self.cluster_binding_target_combo.currentText().strip():
        return self.cluster_binding_target_combo.currentText().strip()
    return getattr(getattr(self, "default_cluster", None), "name", "")


def _delete_selected_cluster(self) -> None:
    name = self._site_selected_cluster_name()
    if not name:
        QMessageBox.warning(self, "Delete Cluster", "No cluster selected.")
        return
    if len(getattr(self.site, "clusters", [])) <= 1:
        QMessageBox.warning(self, "Delete Cluster", "At least one cluster must remain.")
        return
    reply = QMessageBox.question(self, "Delete Cluster", f"Delete cluster '{name}'?\nBMS/PCS bindings in this cluster will be removed from the site config only.")
    if reply != QMessageBox.Yes:
        return
    before = len(self.site.clusters)
    self.site.clusters = [c for c in self.site.clusters if c.name != name]
    if len(self.site.clusters) == before:
        QMessageBox.warning(self, "Delete Cluster", f"Cluster not found: {name}")
        return
    self.default_cluster = self.site.clusters[0]
    self.save_site_config()
    self.refresh_site_view()
    self.refresh_overview()
    if hasattr(self, "refresh_cluster_strategy_controls"):
        self.refresh_cluster_strategy_controls()
    self.log(f"[INFO] Deleted cluster: {name}")


def _import_site_config_json(self) -> None:
    path, _ = QFileDialog.getOpenFileName(self, "Import site_config.json", str(Path.cwd()), "JSON Files (*.json)")
    if not path:
        return
    try:
        # Validate it is JSON and has a cluster list before replacing profile config.
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "clusters" not in data or not isinstance(data.get("clusters"), list):
            QMessageBox.warning(self, "Import Site Config", "Invalid site_config.json: missing clusters list.")
            return
        dest = self.get_profile_path("site_config.json")
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.load_site_config()
        if hasattr(self, "refresh_cluster_strategy_controls"):
            self.refresh_cluster_strategy_controls()
        self.log(f"[INFO] Imported site config: {path} -> {dest}")
        QMessageBox.information(self, "Import Site Config", f"Imported to:\n{dest}")
    except Exception as exc:
        QMessageBox.critical(self, "Import Site Config", f"Failed to import site config:\n{exc}")


def _export_site_config_json(self) -> None:
    try:
        self.save_site_config()
    except Exception:
        pass
    default_path = self.current_profile_dir / "site_config_export.json"
    path, _ = QFileDialog.getSaveFileName(self, "Export site_config.json", str(default_path), "JSON Files (*.json)")
    if not path:
        return
    try:
        import shutil
        src = self.get_profile_path("site_config.json")
        shutil.copy2(src, Path(path))
        self.log(f"[INFO] Exported site config: {path}")
        QMessageBox.information(self, "Export Site Config", f"Exported:\n{path}")
    except Exception as exc:
        QMessageBox.critical(self, "Export Site Config", f"Failed to export site config:\n{exc}")


SiteMixin._site_selected_cluster_name = _site_selected_cluster_name
SiteMixin.delete_selected_cluster = _delete_selected_cluster
SiteMixin.import_site_config_json = _import_site_config_json
SiteMixin.export_site_config_json = _export_site_config_json


# =========================
# Cluster Strategy config persistence helpers
# =========================
def _cluster_strategy_defaults(self) -> dict:
    return {
        "mode": "charge",
        "target_power_kw": 0.0,
        "ramp_step_kw": 50.0,
        "ramp_interval_s": 5.0,
        "bms_response_timeout_s": 5.0,
        "charge_stop_max_cell_mv": 3550.0,
        "discharge_stop_min_cell_mv": 2800.0,
        "positive_power_means": "discharge",
        "allocation_mode": "equal_split",
        "timeout_action": "immediate_zero",
    }


def _cluster_strategy_dict_from_ui(self) -> dict:
    data = self._cluster_strategy_defaults()
    try:
        if hasattr(self, "cluster_strategy_mode_combo"):
            data["mode"] = self.cluster_strategy_mode_combo.currentText().strip().lower() or data["mode"]
        if hasattr(self, "cluster_strategy_target_spin"):
            data["target_power_kw"] = float(self.cluster_strategy_target_spin.value())
        if hasattr(self, "cluster_strategy_ramp_step_spin"):
            data["ramp_step_kw"] = float(self.cluster_strategy_ramp_step_spin.value())
        if hasattr(self, "cluster_strategy_ramp_interval_spin"):
            data["ramp_interval_s"] = float(self.cluster_strategy_ramp_interval_spin.value())
        if hasattr(self, "cluster_strategy_timeout_spin"):
            data["bms_response_timeout_s"] = float(self.cluster_strategy_timeout_spin.value())
        if hasattr(self, "cluster_strategy_charge_cutoff_spin"):
            data["charge_stop_max_cell_mv"] = float(self.cluster_strategy_charge_cutoff_spin.value())
        if hasattr(self, "cluster_strategy_discharge_cutoff_spin"):
            data["discharge_stop_min_cell_mv"] = float(self.cluster_strategy_discharge_cutoff_spin.value())
        if hasattr(self, "cluster_strategy_positive_combo"):
            txt = self.cluster_strategy_positive_combo.currentText()
            data["positive_power_means"] = "charge" if "+ = charge" in txt else "discharge"
        if hasattr(self, "cluster_strategy_allocation_combo"):
            data["allocation_mode"] = self.cluster_strategy_allocation_combo.currentText().strip() or data["allocation_mode"]
        if hasattr(self, "cluster_strategy_timeout_action_combo"):
            data["timeout_action"] = self.cluster_strategy_timeout_action_combo.currentText().strip() or data["timeout_action"]
    except Exception:
        pass
    return data


def _cluster_strategy_apply_dict_to_ui(self, data: dict) -> None:
    cfg = self._cluster_strategy_defaults()
    if isinstance(data, dict):
        cfg.update(data)
    try:
        if hasattr(self, "cluster_strategy_mode_combo"):
            self.cluster_strategy_mode_combo.setCurrentText(str(cfg.get("mode", "charge")))
        if hasattr(self, "cluster_strategy_target_spin"):
            self.cluster_strategy_target_spin.setValue(float(cfg.get("target_power_kw", 0.0)))
        if hasattr(self, "cluster_strategy_ramp_step_spin"):
            self.cluster_strategy_ramp_step_spin.setValue(float(cfg.get("ramp_step_kw", 50.0)))
        if hasattr(self, "cluster_strategy_ramp_interval_spin"):
            self.cluster_strategy_ramp_interval_spin.setValue(float(cfg.get("ramp_interval_s", 5.0)))
        if hasattr(self, "cluster_strategy_timeout_spin"):
            self.cluster_strategy_timeout_spin.setValue(float(cfg.get("bms_response_timeout_s", 5.0)))
        if hasattr(self, "cluster_strategy_charge_cutoff_spin"):
            self.cluster_strategy_charge_cutoff_spin.setValue(float(cfg.get("charge_stop_max_cell_mv", 3550.0)))
        if hasattr(self, "cluster_strategy_discharge_cutoff_spin"):
            self.cluster_strategy_discharge_cutoff_spin.setValue(float(cfg.get("discharge_stop_min_cell_mv", 2800.0)))
        if hasattr(self, "cluster_strategy_positive_combo"):
            means = str(cfg.get("positive_power_means", "discharge"))
            self.cluster_strategy_positive_combo.setCurrentText("+ = charge" if means == "charge" else "+ = discharge")
        if hasattr(self, "cluster_strategy_allocation_combo"):
            self.cluster_strategy_allocation_combo.setCurrentText(str(cfg.get("allocation_mode", "equal_split")))
        if hasattr(self, "cluster_strategy_timeout_action_combo"):
            self.cluster_strategy_timeout_action_combo.setCurrentText(str(cfg.get("timeout_action", "immediate_zero")))
    except Exception as exc:
        try:
            self.log(f"[WARN] Failed to apply cluster strategy UI values: {exc}")
        except Exception:
            pass


def _capture_selected_cluster_strategy_from_ui(self) -> None:
    name = ""
    if hasattr(self, "cluster_strategy_combo"):
        name = self.cluster_strategy_combo.currentText().strip()
    if not name and hasattr(self, "default_cluster"):
        name = self.default_cluster.name
    cluster = None
    for c in getattr(getattr(self, "site", None), "clusters", []) or []:
        if c.name == name:
            cluster = c
            break
    if cluster is None:
        return
    cluster.strategy = self.cluster_strategy_dict_from_ui()
    # Keep legacy cluster-level fields in sync.
    cluster.allocation_mode = str(cluster.strategy.get("allocation_mode", getattr(cluster, "allocation_mode", "equal_split")))


def _apply_selected_cluster_strategy_to_ui(self, cluster_name: str | None = None) -> None:
    if not hasattr(self, "cluster_strategy_combo"):
        return
    name = (cluster_name or self.cluster_strategy_combo.currentText() or "").strip()
    if not name and hasattr(self, "default_cluster"):
        name = self.default_cluster.name
    cluster = None
    for c in getattr(getattr(self, "site", None), "clusters", []) or []:
        if c.name == name:
            cluster = c
            break
    if cluster is None:
        return
    self.cluster_strategy_apply_dict_to_ui(getattr(cluster, "strategy", {}) or {})
    try:
        self.refresh_cluster_strategy_status_text()
    except Exception:
        pass


SiteMixin.cluster_strategy_dict_from_ui = _cluster_strategy_dict_from_ui
SiteMixin.cluster_strategy_apply_dict_to_ui = _cluster_strategy_apply_dict_to_ui
SiteMixin.capture_selected_cluster_strategy_from_ui = _capture_selected_cluster_strategy_from_ui
SiteMixin.apply_selected_cluster_strategy_to_ui = _apply_selected_cluster_strategy_to_ui
SiteMixin._cluster_strategy_defaults = _cluster_strategy_defaults
