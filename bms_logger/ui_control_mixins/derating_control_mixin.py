from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QMessageBox

from ..hv_controller import HvWorkflowController, HvWorkflowWorker
from ..modbus_client import BmsModbusClient
from ..pcs_client import PcsClient
from ..client_factory import create_bms_client, create_pcs_client
from ..worker import HeartbeatWorker


class DeratingControlMixin:
    def handle_set_pcs_active_power(self) -> None:
        device_name = self._get_selected_control_device()
        if not device_name:
            return

        target_power = float(self.pcs_active_power_spin.value())

        reply = QMessageBox.question(
            self,
            "Confirm Set Active Power",
            f"Set PCS active power to {target_power} kW?",
        )
        if reply != QMessageBox.Yes:
            return

        pcs_client = self.create_pcs_client()

        try:
            if not pcs_client.connect():
                self.control_log("[PCS POWER] Connect failed")
                QMessageBox.critical(self, "PCS Power", "PCS connect failed")
                return

            # 注意：这里先按 UI 输入值直接写
            # 如果你的 PCS 点表要求 raw value，需要后面加 scale 反算
            ok = pcs_client.set_active_power(target_power)
            self.control_log(
                f"[PCS POWER] Set power request: {target_power} kW"
            )

            if ok:
                cluster = self.get_cluster_by_device(device_name)
                pcs_name = self._get_selected_pcs_name() if hasattr(self, "control_pcs_combo") else (cluster.pcs_device.name if cluster and cluster.pcs_device else device_name)
                self.last_user_power_kw[pcs_name] = target_power
                self.control_log(f"[PCS POWER] Set active power success: {target_power} kW")
                self.last_control_result_label.setText(f"PCS power={target_power}kW")
            else:
                self.control_log(f"[PCS POWER] Set active power failed: {target_power} kW")
                self.last_control_result_label.setText("PCS power set failed")

        except Exception as exc:
            self.control_log(f"[PCS POWER] Exception: {exc}")
            QMessageBox.critical(self, "PCS Power", str(exc))

        finally:
            try:
                pcs_client.close()
            except Exception:
                pass

    def handle_derating_action(self, device_name: str, reason: str) -> None:
        pcs_client = self.create_pcs_client_for_device(device_name)

        try:
            if not pcs_client.connect():
                self.control_log(f"[DERATING] {device_name}: PCS connect failed")
                return

            precheck_errors = pcs_client.precheck_control_ready(action="set_active_power")
            if precheck_errors:
                self.control_log(f"[DERATING] {device_name}: PCS precheck failed")
                for err in precheck_errors:
                    self.control_log(f"[DERATING] {err}")
                return

            ok = pcs_client.set_active_power(self.derating_power_kw)

            if ok:
                self.control_log(
                    f"[DERATING] {device_name}: set active power success, "
                    f"target={self.derating_power_kw}kW, reason={reason}"
                )
            else:
                self.control_log(
                    f"[DERATING] {device_name}: set active power failed, "
                    f"target={self.derating_power_kw}kW, reason={reason}"
                )

        except Exception as exc:
            self.control_log(f"[DERATING] {device_name}: exception - {exc}")

        finally:
            try:
                pcs_client.close()
            except Exception:
                pass

    def handle_derating_recover(self, device_name: str) -> None:
        pcs_name = self._resolve_pcs_name_for_context(device_name)
        target_power = self.last_user_power_kw.get(pcs_name)

        if target_power is None:
            self.control_log(f"[DERATING] {pcs_name}: no last user power, skip recover")
            return

        pcs_client = self.create_pcs_client_for_device(pcs_name)

        try:
            if not pcs_client.connect():
                self.control_log(f"[DERATING] {device_name}: PCS connect failed (recover)")
                return

            ok = pcs_client.set_active_power(target_power)

            if ok:
                self.control_log(
                    f"[DERATING] {device_name}: power restored to {target_power}kW"
                )
            else:
                self.control_log(
                    f"[DERATING] {device_name}: restore failed, target={target_power}kW"
                )

        except Exception as exc:
            self.control_log(f"[DERATING] {device_name}: recover exception - {exc}")

        finally:
            try:
                pcs_client.close()
            except Exception:
                pass
