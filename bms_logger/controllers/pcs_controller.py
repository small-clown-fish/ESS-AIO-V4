from __future__ import annotations

from typing import Any, Callable, Optional

from ..action_result import ActionResult
from ..client_factory import create_pcs_client

# Backward-compatible name used by existing UI code.
ControllerResult = ActionResult


class PcsController:
    """Application-level PCS control facade.

    UI pages/controllers should use this class instead of constructing PCS clients directly.
    It keeps Fake/Real selection, multi-PCS config lookup, and cluster-bound PCS resolution in one place.
    All externally useful actions return ActionResult and are audit-logged when AuditController exists.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    def selected_pcs_name(self) -> str:
        app = self.app
        if hasattr(app, "control_pcs_combo") and app.control_pcs_combo.currentText().strip():
            return app.control_pcs_combo.currentText().strip()

        device_name = getattr(app, "current_control_device", None)
        if device_name:
            cluster = app.get_cluster_by_device(device_name)
            if cluster and cluster.pcs_device:
                return cluster.pcs_device.name

        return getattr(app, "current_pcs_name", "") or ""

    def resolve_pcs_name_for_context(self, device_name: str | None) -> str:
        app = self.app
        if device_name and device_name in getattr(app, "pcs_configs", {}):
            return device_name

        if device_name:
            cluster = app.get_cluster_by_device(device_name)
            if cluster and cluster.pcs_device:
                return cluster.pcs_device.name

        return self.selected_pcs_name()

    def get_config(self, pcs_name: str) -> dict[str, Any]:
        if not pcs_name:
            return {}
        return self.app.get_pcs_config_by_name(pcs_name)

    def create_client_for_pcs_name(self, pcs_name: str):
        return create_pcs_client(self.get_config(pcs_name), fake_mode=getattr(self.app, "fake_mode", False))

    def create_client_for_device(self, device_name: str):
        return self.create_client_for_pcs_name(self.resolve_pcs_name_for_context(device_name))

    def create_selected_client(self):
        return self.create_client_for_pcs_name(self.selected_pcs_name())

    def execute_for_device(
        self,
        device_name: str,
        method_name: str,
        *,
        precheck: bool = True,
        action_name: str | None = None,
        log: Optional[Callable[[str], None]] = None,
    ) -> ActionResult:
        pcs_name = self.resolve_pcs_name_for_context(device_name)
        client = self.create_client_for_pcs_name(pcs_name)
        action = action_name or method_name
        target = pcs_name

        try:
            if not client.connect():
                return self._result(False, f"PCS connect failed: {pcs_name}", action=action, target=target)

            if precheck and hasattr(client, "precheck_control_ready"):
                errors = client.precheck_control_ready(action=method_name)
                if errors:
                    return self._result(False, "\n".join(str(e) for e in errors), action=action, target=target)

            method = getattr(client, method_name, None)
            if method is None:
                return self._result(False, f"PCS method not found: {method_name}", action=action, target=target)

            ok = bool(method())
            if ok:
                return self._result(True, f"{action} success", action=action, target=target, value={"pcs_name": pcs_name})
            return self._result(False, f"{action} failed", action=action, target=target, value={"pcs_name": pcs_name})

        except Exception as exc:
            return self._result(False, f"{action} exception: {exc}", action=action, target=target, error=str(exc), value={"pcs_name": pcs_name})

        finally:
            try:
                client.close()
            except Exception:
                pass

    def set_power_for_device(self, device_name: str, target_power_kw: float, *, precheck: bool = True) -> ActionResult:
        pcs_name = self.resolve_pcs_name_for_context(device_name)
        return self.set_power_for_pcs(pcs_name, target_power_kw, precheck=precheck)

    def set_power_for_pcs(self, pcs_name: str, target_power_kw: float, *, precheck: bool = True) -> ActionResult:
        client = self.create_client_for_pcs_name(pcs_name)
        action = "set_active_power"
        target = pcs_name
        try:
            if not client.connect():
                return self._result(False, f"PCS connect failed: {pcs_name}", action=action, target=target)

            if precheck and hasattr(client, "precheck_control_ready"):
                errors = client.precheck_control_ready(action="set_active_power")
                if errors:
                    return self._result(False, "\n".join(str(e) for e in errors), action=action, target=target)

            ok = bool(client.set_active_power(target_power_kw))
            if ok:
                return self._result(True, f"Set power success: {target_power_kw}kW", action=action, target=target, value={"pcs_name": pcs_name, "target_power_kw": target_power_kw})
            return self._result(False, f"Set power failed: {target_power_kw}kW", action=action, target=target, value={"pcs_name": pcs_name, "target_power_kw": target_power_kw})

        except Exception as exc:
            return self._result(False, f"Set power exception: {exc}", action=action, target=target, error=str(exc), value={"pcs_name": pcs_name})

        finally:
            try:
                client.close()
            except Exception:
                pass


    def set_reactive_power_for_device(self, device_name: str, target_reactive_kvar: float, *, precheck: bool = True) -> ActionResult:
        pcs_name = self.resolve_pcs_name_for_context(device_name)
        return self.set_reactive_power_for_pcs(pcs_name, target_reactive_kvar, precheck=precheck)

    def set_reactive_power_for_pcs(self, pcs_name: str, target_reactive_kvar: float, *, precheck: bool = True) -> ActionResult:
        client = self.create_client_for_pcs_name(pcs_name)
        action = "set_reactive_power"
        target = pcs_name
        try:
            if not client.connect():
                return self._result(False, f"PCS connect failed: {pcs_name}", action=action, target=target)

            if precheck and hasattr(client, "precheck_control_ready"):
                errors = client.precheck_control_ready(action="set_reactive_power")
                if errors:
                    return self._result(False, "\n".join(str(e) for e in errors), action=action, target=target)

            # PcsClient.set_reactive_power() performs the required sequence:
            #   7909 = 1 reactive remote enable, then 7812 = kvar setpoint.
            ok = bool(client.set_reactive_power(target_reactive_kvar))
            if ok:
                return self._result(True, f"Set reactive power success: enable 7909=1, set 7812={target_reactive_kvar}kvar", action=action, target=target, value={"pcs_name": pcs_name, "target_reactive_kvar": target_reactive_kvar})
            return self._result(False, f"Set reactive power failed: {target_reactive_kvar}kvar", action=action, target=target, value={"pcs_name": pcs_name, "target_reactive_kvar": target_reactive_kvar})

        except Exception as exc:
            return self._result(False, f"Set reactive power exception: {exc}", action=action, target=target, error=str(exc), value={"pcs_name": pcs_name})

        finally:
            try:
                client.close()
            except Exception:
                pass

    def read_status_for_device(self, device_name: str) -> ActionResult:
        pcs_name = self.resolve_pcs_name_for_context(device_name)
        client = self.create_client_for_pcs_name(pcs_name)
        action = "read_status"
        target = pcs_name
        try:
            if not client.connect():
                return self._result(False, f"PCS connect failed: {pcs_name}", action=action, target=target)

            values: dict[str, str] = {}
            readers = [
                ("online", lambda: "Online" if client.is_online() else "Offline"),
                ("run_status", lambda: str(client.get_run_status())),
                ("fault_status", lambda: str(client.get_fault_status())),
                ("alarm_status", lambda: str(client.get_alarm_status())),
                ("dc_breaker", lambda: self._format_breaker_state(client)),
                ("active_power", lambda: str(client.get_active_power())),
                ("mode", lambda: str(client.get_mode())),
                ("remote_local", lambda: str(client.get_remote_local_status())),
            ]
            for key, func in readers:
                try:
                    values[key] = func()
                except Exception as exc:
                    values[key] = f"Error: {exc}"

            return self._result(True, f"PCS status refreshed: {pcs_name}", action=action, target=target, value=values)

        except Exception as exc:
            return self._result(False, f"PCS status exception: {exc}", action=action, target=target, error=str(exc))

        finally:
            try:
                client.close()
            except Exception:
                pass

    def _result(
        self,
        ok: bool,
        message: str,
        *,
        action: str = "",
        target: str = "",
        value: Any = None,
        error: str = "",
    ) -> ActionResult:
        if ok:
            result = ActionResult.success(message, action=action, target=target, source="PcsController", value=value)
        else:
            result = ActionResult.failure(message, action=action, target=target, source="PcsController", value=value, error=error)
        self._audit_result(result)
        return result

    def _audit_result(self, result: ActionResult) -> None:
        audit = getattr(self.app, "audit_controller", None)
        if audit is not None:
            audit.log_result(result)

    @staticmethod
    def _format_breaker_state(client: Any) -> str:
        try:
            if client.is_dc_breaker_open():
                return "Open"
            if client.is_dc_breaker_closed():
                return "Closed"
            return "Unknown"
        except Exception as exc:
            return f"Error: {exc}"
