from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QMessageBox

from ..hv_controller import HvWorkflowController, HvWorkflowWorker
from ..modbus_client import BmsModbusClient
from ..pcs_client import PcsClient
from ..client_factory import create_bms_client, create_pcs_client
from ..worker import HeartbeatWorker


class CommonControlMixin:
    def _get_selected_control_device(self) -> Optional[str]:
        device_name = self.control_device_combo.currentText().strip()
        if not device_name:
            QMessageBox.warning(self, "Warning", "No control device selected.")
            return None
        return device_name

    def _build_hv_controller(self, device_name: str) -> Optional[HvWorkflowController]:
        device_cfg = next((d for d in self.devices if d["name"] == device_name), None)
        if not device_cfg:
            QMessageBox.warning(self, "Warning", f"Device config not found for {device_name}.")
            return None

        bms_client = create_bms_client(device_cfg, fake_mode=self.fake_mode)

        pcs_client = self.create_pcs_client_for_device(device_name)

        controller = HvWorkflowController(
            bms_client=bms_client,
            pcs_client=pcs_client,
            log_callback=self.control_log,
            step_timeout=self.hv_step_timeout,
            poll_interval=self.hv_poll_interval,
            pcs_zero_power_threshold=self.pcs_zero_power_threshold,
        )
        controller.ignore_pcs_checks = bool(
            hasattr(self, "ignore_pcs_checks_checkbox")
            and self.ignore_pcs_checks_checkbox.isChecked()
        )
        return controller

    def _build_bms_client_for_device(self, device_name: str) -> Optional[BmsModbusClient]:
        device_cfg = next((d for d in self.devices if d["name"] == device_name), None)
        if not device_cfg:
            QMessageBox.warning(self, "Warning", f"Device config not found for {device_name}.")
            return None

        return create_bms_client(device_cfg, fake_mode=self.fake_mode)
    def _get_selected_pcs_name(self) -> str:
        if hasattr(self, "control_pcs_combo") and self.control_pcs_combo.currentText().strip():
            return self.control_pcs_combo.currentText().strip()
        device_name = self.current_control_device or self._get_selected_control_device()
        cluster = self.get_cluster_by_device(device_name) if device_name else None
        if cluster and cluster.pcs_device:
            return cluster.pcs_device.name
        return self.current_pcs_name or ""

    def _resolve_pcs_name_for_context(self, device_name: str | None) -> str:
        if device_name and device_name in getattr(self, "pcs_configs", {}):
            return device_name

        if device_name:
            cluster = self.get_cluster_by_device(device_name)
            if cluster and cluster.pcs_device:
                return cluster.pcs_device.name

        return self._get_selected_pcs_name()

    def create_pcs_client(self):
        if hasattr(self, "pcs_controller"):
            return self.pcs_controller.create_selected_client()
        pcs_name = self._get_selected_pcs_name()
        return self.create_pcs_client_for_pcs_name(pcs_name)

    def create_pcs_client_for_pcs_name(self, pcs_name: str):
        if hasattr(self, "pcs_controller"):
            return self.pcs_controller.create_client_for_pcs_name(pcs_name)
        config = self.get_pcs_config_by_name(pcs_name)
        return create_pcs_client(config, fake_mode=self.fake_mode)

    def create_pcs_client_for_device(self, device_name: str):
        if hasattr(self, "pcs_controller"):
            return self.pcs_controller.create_client_for_device(device_name)
        pcs_name = self._resolve_pcs_name_for_context(device_name)
        return self.create_pcs_client_for_pcs_name(pcs_name)
