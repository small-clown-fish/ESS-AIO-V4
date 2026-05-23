from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QMessageBox

from ..hv_controller import HvWorkflowController, HvWorkflowWorker
from ..modbus_client import BmsModbusClient
from ..pcs_client import PcsClient
from ..client_factory import create_bms_client, create_pcs_client
from ..worker import HeartbeatWorker


class HvControlMixin:
    def handle_hv_on(self) -> None:
        device_name = self._get_selected_control_device()
        if not device_name:
            return

        if device_name in self.hv_workers:
            QMessageBox.information(self, "Info", f"HV workflow already running for {device_name}")
            return

        reply = QMessageBox.question(
            self,
            "Confirm HV On",
            f"Execute HV On workflow for {device_name}?",
        )
        if reply != QMessageBox.Yes:
            return

        controller = self._build_hv_controller(device_name)
        if controller is None:
            return

        worker = HvWorkflowWorker(
            mode="on",
            controller=controller,
            device_name=device_name,
            log_callback=self.on_hv_workflow_log,
            finished_callback=self.on_hv_workflow_finished,
        )
        self.hv_workers[device_name] = worker

        self.control_state_label.setText("Executing")
        self.last_control_result_label.setText("HV ON running")
        self.control_log(f"[CONTROL] {device_name}: HV ON workflow started")
        worker.start()

    def handle_hv_off(self) -> None:
        device_name = self._get_selected_control_device()
        if not device_name:
            return

        if device_name in self.hv_workers:
            QMessageBox.information(self, "Info", f"HV workflow already running for {device_name}")
            return

        reply = QMessageBox.question(
            self,
            "Confirm HV Off",
            f"Execute HV Off workflow for {device_name}?",
        )
        if reply != QMessageBox.Yes:
            return

        controller = self._build_hv_controller(device_name)
        if controller is None:
            return

        worker = HvWorkflowWorker(
            mode="off",
            controller=controller,
            device_name=device_name,
            log_callback=self.on_hv_workflow_log,
            finished_callback=self.on_hv_workflow_finished,
        )
        self.hv_workers[device_name] = worker

        self.control_state_label.setText("Executing")
        self.last_control_result_label.setText("HV OFF running")
        self.control_log(f"[CONTROL] {device_name}: HV OFF workflow started")
        worker.start()

    def handle_cancel_hv_workflow(self) -> None:
        device_name = self._get_selected_control_device()
        if not device_name:
            return

        worker = self.hv_workers.get(device_name)
        if not worker:
            self.control_log(f"[CONTROL] {device_name}: No HV workflow running")
            return

        worker.stop()
        self.control_state_label.setText("Cancelling")
        self.last_control_result_label.setText("HV workflow cancelling")
        self.control_log(f"[CONTROL] {device_name}: HV workflow cancel requested")
        self.last_hv_status = "Cancelling"
        self.refresh_global_status_bar()
    def start_hv_off_for_device(self, device_name: str, source: str = "Manual") -> None:
        if device_name in self.hv_workers:
            self.control_log(f"[{source}] {device_name}: HV workflow already running")
            return

        controller = self._build_hv_controller(device_name)
        if controller is None:
            return

        worker = HvWorkflowWorker(
            mode="off",
            controller=controller,
            device_name=device_name,
            log_callback=self.on_hv_workflow_log,
            finished_callback=self.on_hv_workflow_finished,
        )

        self.hv_workers[device_name] = worker
        self.last_hv_status = "Running"
        self.refresh_global_status_bar()
        self.control_log(f"[{source}] {device_name}: HV OFF workflow started")
        worker.start()
