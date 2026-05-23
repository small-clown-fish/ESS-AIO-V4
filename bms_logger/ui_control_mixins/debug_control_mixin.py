from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QMessageBox

from ..hv_controller import HvWorkflowController, HvWorkflowWorker
from ..modbus_client import BmsModbusClient
from ..pcs_client import PcsClient
from ..client_factory import create_bms_client, create_pcs_client
from ..worker import HeartbeatWorker


class DebugControlMixin:
    def handle_test_pcs_config(self) -> None:
        pcs_client = self.create_pcs_client()
        errors = pcs_client.validate_config()

        if errors:
            msg = "\n".join(errors)
            self.control_log("[PCS CONFIG] Validation failed:\n" + msg)
            QMessageBox.warning(self, "PCS Config", msg)
            return

        try:
            if not pcs_client.connect():
                self.control_log("[PCS CONFIG] Connect failed")
                QMessageBox.critical(self, "PCS Config", "PCS connect failed")
                return

            self.control_log("[PCS CONFIG] Connect success")
            QMessageBox.information(self, "PCS Config", "PCS config OK and connect success")

        except Exception as exc:
            self.control_log(f"[PCS CONFIG] Exception: {exc}")
            QMessageBox.critical(self, "PCS Config", str(exc))

        finally:
            try:
                pcs_client.close()
            except Exception:
                pass

    def handle_read_pcs_debug_status(self) -> None:
        device_name = self._get_selected_control_device()
        if not device_name:
            return

        pcs_client = self.create_pcs_client()

        try:
            if not pcs_client.connect():
                self.control_log("[PCS DEBUG] Connect failed")
                return

            status = pcs_client.read_debug_status()

            self.control_log("[PCS DEBUG] ===== PCS raw status =====")
            for name, info in status.items():
                self.control_log(f"[PCS DEBUG] {name}: {info}")

        except Exception as exc:
            self.control_log(f"[PCS DEBUG] Exception: {exc}")

        finally:
            try:
                pcs_client.close()
            except Exception:
                pass

    def _execute_pcs_command_with_debug(
            self,
            action_name: str,
            pcs_method_name: str,
            confirm: bool = True,
    ) -> None:
        device_name = self._get_selected_control_device()
        if not device_name:
            return

        if confirm:
            reply = QMessageBox.question(
                self,
                f"Confirm {action_name}",
                f"Execute PCS action '{action_name}' and read debug status?",
            )
            if reply != QMessageBox.Yes:
                return

        pcs_client = self.create_pcs_client()

        try:
            if not pcs_client.connect():
                self.control_log(f"[PCS DEBUG CMD] {action_name}: connect failed")
                return

            precheck_errors = pcs_client.precheck_control_ready(action=pcs_method_name)
            if precheck_errors:
                self.control_log("[PCS DEBUG CMD] Precheck failed:")
                for err in precheck_errors:
                    self.control_log(f"[PCS DEBUG CMD] {err}")
                return
            result = pcs_client.execute_command_with_debug(pcs_method_name)

            self.control_log(f"[PCS DEBUG CMD] command={result.get('command')}")
            self.control_log(f"[PCS DEBUG CMD] success={result.get('success')}")
            if result.get("error"):
                self.control_log(f"[PCS DEBUG CMD] error={result.get('error')}")

            debug_status = result.get("debug_status", {})
            self.control_log("[PCS DEBUG CMD] ===== status after command =====")
            for name, info in debug_status.items():
                self.control_log(f"[PCS DEBUG CMD] {name}: {info}")

        except Exception as exc:
            self.control_log(f"[PCS DEBUG CMD] Exception: {exc}")

        finally:
            try:
                pcs_client.close()
            except Exception:
                pass

    def handle_pcs_stop_debug(self) -> None:
        self._execute_pcs_command_with_debug("PCS Stop Debug", "stop", confirm=True)

    def handle_pcs_start_debug(self) -> None:
        self._execute_pcs_command_with_debug("PCS Start Debug", "start", confirm=True)

    def handle_pcs_hv_on_debug(self) -> None:
        self._execute_pcs_command_with_debug("PCS HV On Debug", "hv_on", confirm=True)

    def handle_pcs_hv_off_debug(self) -> None:
        self._execute_pcs_command_with_debug("PCS HV Off Debug", "hv_off", confirm=True)

    def handle_read_bms_debug_status(self) -> None:
        device_name = self._get_selected_control_device()
        if not device_name:
            return

        client = self._build_bms_client_for_device(device_name)
        if client is None:
            return

        try:
            if not client.connect():
                self.control_log(f"[BMS DEBUG] {device_name}: connect failed")
                return

            status = client.read_debug_status()

            self.control_log(f"[BMS DEBUG] ===== {device_name} raw status =====")
            for name, value in status.items():
                self.control_log(f"[BMS DEBUG] {name}: {value}")

        except Exception as exc:
            self.control_log(f"[BMS DEBUG] {device_name}: exception - {exc}")

        finally:
            try:
                client.close()
            except Exception:
                pass


    def handle_read_bms_version(self) -> None:
        device_name = self._get_selected_control_device()
        if not device_name:
            return

        client = self._build_bms_client_for_device(device_name)
        if client is None:
            return

        try:
            if not client.connect():
                self.control_log(f"[BMS VERSION] {device_name}: connect failed")
                return

            versions = client.read_software_version()
            self.control_log(f"[BMS VERSION] ===== {device_name} =====")
            for name, value in versions.items():
                self.control_log(f"[BMS VERSION] {name}: {value}")
            self.last_control_result_label.setText("BMS version read")

        except Exception as exc:
            self.control_log(f"[BMS VERSION] {device_name}: exception - {exc}")

        finally:
            try:
                client.close()
            except Exception:
                pass
