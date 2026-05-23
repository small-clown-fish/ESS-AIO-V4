from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from ..action_result import ActionResult


class ExecutionMixin:
    def _execute_pcs_command_for_device(
            self,
            device_name: str,
            action_name: str,
            pcs_method_name: str,
            confirm: bool = True,
    ) -> ActionResult:
        if confirm:
            reply = QMessageBox.question(
                self,
                f"Confirm {action_name}",
                f"Execute PCS action '{action_name}'?",
            )
            if reply != QMessageBox.Yes:
                return ActionResult.cancelled(
                    f"PCS {action_name} cancelled",
                    action=action_name,
                    target=device_name,
                    source="UI",
                )

        self.control_state_label.setText("Executing")
        self.last_control_result_label.setText(f"PCS {action_name}")
        self.control_log(f"[CONTROL] {device_name}: PCS {action_name} started")

        if hasattr(self, "app_facade"):
            result = self.app_facade.execute_pcs_command_for_device(
                device_name=device_name,
                method_name=pcs_method_name,
                action_name=action_name,
                precheck=True,
            )
            if result.ok:
                self.control_state_label.setText("Done")
                self.last_control_result_label.setText(f"PCS {action_name} success")
                self.control_log(f"[CONTROL] {device_name}: {result.message}")
            else:
                self.control_state_label.setText("Failed")
                self.last_control_result_label.setText(result.message)
                self.control_log(f"[CONTROL] {device_name}: PCS {action_name} failed - {result.message}")
            return result

        pcs_client = self.create_pcs_client_for_device(device_name)

        try:
            if not pcs_client.connect():
                result = ActionResult.failure(
                    "PCS connect failed",
                    action=action_name,
                    target=device_name,
                    source="UI",
                )
                self.control_state_label.setText("Failed")
                self.last_control_result_label.setText(result.message)
                self.control_log(f"[CONTROL] {device_name}: PCS {action_name} failed - connect failed")
                return result

            precheck_errors = pcs_client.precheck_control_ready(action=pcs_method_name)
            if precheck_errors:
                msg = "\n".join(precheck_errors)
                result = ActionResult.failure(msg, action=action_name, target=device_name, source="UI")
                self.control_log(f"[PCS PRECHECK] {device_name}: failed\n{msg}")
                QMessageBox.warning(self, "PCS Precheck Failed", msg)
                return result

            method = getattr(pcs_client, pcs_method_name, None)
            if method is None:
                result = ActionResult.failure(
                    "PCS method missing",
                    action=action_name,
                    target=device_name,
                    source="UI",
                )
                self.control_state_label.setText("Failed")
                self.last_control_result_label.setText(result.message)
                self.control_log(f"[CONTROL] {device_name}: PCS {action_name} failed - method missing")
                return result

            ok = bool(method())
            if ok:
                result = ActionResult.success(
                    f"PCS {action_name} success",
                    action=action_name,
                    target=device_name,
                    source="UI",
                )
                self.control_state_label.setText("Done")
                self.last_control_result_label.setText(result.message)
                self.control_log(f"[CONTROL] {device_name}: PCS {action_name} success")
                return result

            result = ActionResult.failure(
                f"PCS {action_name} failed",
                action=action_name,
                target=device_name,
                source="UI",
            )
            self.control_state_label.setText("Failed")
            self.last_control_result_label.setText(result.message)
            self.control_log(f"[CONTROL] {device_name}: PCS {action_name} failed")
            return result

        except Exception as exc:
            result = ActionResult.failure(
                f"PCS {action_name} exception - {exc}",
                action=action_name,
                target=device_name,
                source="UI",
                error=str(exc),
            )
            self.control_state_label.setText("Failed")
            self.last_control_result_label.setText(str(exc))
            self.control_log(f"[CONTROL] {device_name}: PCS {action_name} exception - {exc}")
            return result

        finally:
            try:
                pcs_client.close()
            except Exception:
                pass

    def execute_pcs_stop(self, device_name: str, source: str = "Service") -> ActionResult:
        self.control_log(f"[{source}] {device_name}: PCS STOP")
        result = self._execute_pcs_command_for_device(
            device_name=device_name,
            action_name="PCS Stop",
            pcs_method_name="stop_with_confirm",
            confirm=False,
        )
        if not result.source:
            result.source = source
        return result

    def _resolve_bms_name_for_hv_context(self, device_name: str) -> str | None:
        if device_name in getattr(self, "pcs_configs", {}):
            for cluster in self.site.clusters:
                if cluster.pcs_device and cluster.pcs_device.name == device_name:
                    return cluster.bms_devices[0].name if cluster.bms_devices else None
            return None

        return device_name

    def execute_hv_off(self, device_name: str, source: str = "Service") -> ActionResult:
        bms_name = self._resolve_bms_name_for_hv_context(device_name)
        if not bms_name:
            msg = f"[{source}] {device_name}: no BMS bound for HV OFF"
            self.control_log(msg)
            return ActionResult.failure(msg, action="hv_off", target=device_name, source=source)

        self.start_hv_off_for_device(bms_name, source=source)
        return ActionResult.success(
            "HV OFF workflow started",
            action="hv_off",
            target=device_name,
            source=source,
            value={"bms_name": bms_name},
        )

    def execute_derating(self, device_name: str, reason: str) -> ActionResult:
        self.handle_derating_action(device_name, reason)
        return ActionResult.success(reason, action="derating", target=device_name, source="Service")

    def execute_derating_with_power(self, device_name: str, reason: str, target_power: float) -> ActionResult:
        old_power = self.derating_power_kw
        self.derating_power_kw = float(target_power)
        try:
            self.handle_derating_action(device_name, reason)
            return ActionResult.success(
                reason,
                action="derating",
                target=device_name,
                source="Service",
                value={"target_power": target_power},
            )
        finally:
            self.derating_power_kw = old_power

    def execute_derating_recover(self, device_name: str) -> ActionResult:
        self.handle_derating_recover(device_name)
        return ActionResult.success("derating recovered", action="derating_recover", target=device_name, source="Service")

    def execute_cutoff(self, device_name: str, reason: str) -> ActionResult:
        mode = self.strategy_engine.get_str("cutoff_mode", self.cutoff_mode) if hasattr(self, "strategy_engine") else self.cutoff_mode

        if mode == "Stop PCS":
            return self.execute_pcs_stop(device_name, source="Cutoff")

        if mode == "HV Off":
            return self.execute_hv_off(device_name, source="Cutoff")

        self.control_log(f"[CUTOFF] {device_name}: Alarm only ({reason})")
        return ActionResult.success(
            f"Cutoff alarm only ({reason})",
            action="cutoff",
            target=device_name,
            source="Service",
            value={"mode": mode},
        )
