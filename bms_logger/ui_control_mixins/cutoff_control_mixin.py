from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QMessageBox

from ..hv_controller import HvWorkflowController, HvWorkflowWorker
from ..modbus_client import BmsModbusClient
from ..pcs_client import PcsClient
from ..client_factory import create_bms_client, create_pcs_client
from ..worker import HeartbeatWorker


class CutoffControlMixin:
    def handle_cutoff_action(self, device_name: str, reason: str) -> None:
        mode = self.cutoff_mode

        self.control_log(f"[CUTOFF] {device_name}: reason={reason}, mode={mode}")
        self.log(f"[CUTOFF] {device_name}: reason={reason}, mode={mode}")

        if mode == "Disabled":
            return

        if mode == "Alarm Only":
            return

        if mode == "Stop PCS":
            self.control_log(f"[CUTOFF] {device_name}: executing PCS Stop")
            self._execute_pcs_command_for_device(
                device_name=device_name,
                action_name="Stop by Cutoff",
                pcs_method_name="stop_with_confirm",
                confirm=False,
            )
            return

        if mode == "HV Off":
            self.control_log(f"[CUTOFF] {device_name}: executing HV OFF workflow")

            if device_name in self.hv_workers:
                self.control_log(f"[CUTOFF] {device_name}: HV workflow already running, skip")
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
            worker.start()
            return

        self.control_log(f"[CUTOFF] Unknown cutoff mode: {mode}")

