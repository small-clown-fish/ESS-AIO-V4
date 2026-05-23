from __future__ import annotations

from pathlib import Path
from typing import Any

from .action_result import ActionResult


class AppFacade:
    """Single application entrypoint for UI, future API, CLI, and tests.

    The facade intentionally delegates to existing controllers and app methods so this
    phase does not change runtime behavior. New non-UI entrypoints should call this
    class instead of reaching directly into UI mixins, controllers, service, or drivers.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    # ------------------------------------------------------------------
    # Generic helpers
    # ------------------------------------------------------------------
    def ok(self, message: str = "OK", *, action: str = "", target: str = "", value: Any = None) -> ActionResult:
        return ActionResult.success(message, action=action, target=target, source="AppFacade", value=value)

    def fail(self, message: str, *, action: str = "", target: str = "", error: str = "") -> ActionResult:
        return ActionResult.failure(message, action=action, target=target, source="AppFacade", error=error or message)

    def _audit(self, result: ActionResult) -> ActionResult:
        audit = getattr(self.app, "audit_controller", None)
        if audit is not None:
            audit.log_result(result)
        return result

    def _safe_call(self, action: str, func, *, target: str = "", success_message: str = "OK") -> ActionResult:
        try:
            value = func()
            if isinstance(value, ActionResult):
                if not value.source:
                    value.source = "AppFacade"
                if not value.action:
                    value.action = action
                if not value.target:
                    value.target = target
                return self._audit(value)
            return self._audit(self.ok(success_message, action=action, target=target, value=value))
        except Exception as exc:
            return self._audit(self.fail(str(exc), action=action, target=target, error=str(exc)))

    # ------------------------------------------------------------------
    # Device/BMS facade
    # ------------------------------------------------------------------
    def device_names(self) -> list[str]:
        controller = getattr(self.app, "device_controller", None)
        if controller is not None:
            return controller.configured_names()
        return [str(d.get("name", "")) for d in getattr(self.app, "devices", []) if d.get("name")]

    def running_device_names(self) -> list[str]:
        controller = getattr(self.app, "device_controller", None)
        if controller is not None:
            return controller.running_names()
        return list(getattr(self.app, "device_workers", {}).keys())

    def start_all_devices(self) -> ActionResult:
        # Preserve current UI behavior; later phases can move internals into DeviceController.
        return self._safe_call("start_all_devices", self.app.start_all, success_message="Start all requested")

    def stop_all_devices(self) -> ActionResult:
        return self._safe_call("stop_all_devices", self.app.stop_all, success_message="Stop all requested")

    # ------------------------------------------------------------------
    # PCS facade
    # ------------------------------------------------------------------
    def selected_pcs_name(self) -> str:
        return self.app.pcs_controller.selected_pcs_name()

    def resolve_pcs_name_for_context(self, device_name: str | None) -> str:
        return self.app.pcs_controller.resolve_pcs_name_for_context(device_name)

    def create_pcs_client_for_context(self, device_name: str | None = None):
        if device_name:
            return self.app.pcs_controller.create_client_for_device(device_name)
        return self.app.pcs_controller.create_selected_client()

    def execute_pcs_command_for_device(
        self,
        device_name: str,
        method_name: str,
        *,
        action_name: str | None = None,
        precheck: bool = True,
    ) -> ActionResult:
        result = self.app.pcs_controller.execute_for_device(
            device_name=device_name,
            method_name=method_name,
            precheck=precheck,
            action_name=action_name,
        )
        if not result.source:
            result.source = "AppFacade"
        return result

    def set_pcs_power_for_device(self, device_name: str, target_power_kw: float, *, precheck: bool = True) -> ActionResult:
        result = self.app.pcs_controller.set_power_for_device(device_name, target_power_kw, precheck=precheck)
        if not result.source:
            result.source = "AppFacade"
        return result

    def set_pcs_power(self, pcs_name: str, target_power_kw: float, *, precheck: bool = True) -> ActionResult:
        result = self.app.pcs_controller.set_power_for_pcs(pcs_name, target_power_kw, precheck=precheck)
        if not result.source:
            result.source = "AppFacade"
        return result

    def read_pcs_status_for_device(self, device_name: str) -> ActionResult:
        result = self.app.pcs_controller.read_status_for_device(device_name)
        if not result.source:
            result.source = "AppFacade"
        return result

    # ------------------------------------------------------------------
    # Service/action facade
    # ------------------------------------------------------------------
    def set_pcs_reactive_power_for_device(self, device_name: str, target_reactive_kvar: float, *, precheck: bool = True) -> ActionResult:
        result = self.app.pcs_controller.set_reactive_power_for_device(device_name, target_reactive_kvar, precheck=precheck)
        if result.ok:
            self.app.control_log(f"[APP] PCS reactive power set for {device_name}: {target_reactive_kvar}kvar")
        return result

    def set_pcs_reactive_power(self, pcs_name: str, target_reactive_kvar: float, *, precheck: bool = True) -> ActionResult:
        result = self.app.pcs_controller.set_reactive_power_for_pcs(pcs_name, target_reactive_kvar, precheck=precheck)
        if result.ok:
            self.app.control_log(f"[APP] PCS reactive power set for {pcs_name}: {target_reactive_kvar}kvar")
        return result

    def request_derating(self, device_name: str, reason: str, target_power: float | None = None) -> ActionResult:
        return self.app.service_action_controller.derating(device_name, reason, target_power)

    def request_derating_recover(self, device_name: str) -> ActionResult:
        return self.app.service_action_controller.derating_recover(device_name)

    def request_cutoff(self, device_name: str, reason: str) -> ActionResult:
        return self.app.service_action_controller.cutoff(device_name, reason)

    def request_pcs_stop(self, device_name: str, source: str = "AppFacade") -> ActionResult:
        return self.app.service_action_controller.pcs_stop(device_name, source=source)

    def request_hv_off(self, device_name: str, source: str = "AppFacade") -> ActionResult:
        return self.app.service_action_controller.hv_off(device_name, source=source)

    # ------------------------------------------------------------------
    # Profile facade
    # ------------------------------------------------------------------
    def profile_path(self, filename: str) -> Path:
        return self.app.profile_controller.path(filename)

    def save_profile(self) -> ActionResult:
        return self._safe_call("save_profile", self.app.profile_controller.save_all, target=getattr(self.app, "current_profile_name", ""), success_message="Profile saved")

    def load_startup_profile(self) -> ActionResult:
        return self._safe_call("load_startup_profile", self.app.profile_controller.load_startup, target=getattr(self.app, "current_profile_name", ""), success_message="Startup profile loaded")

    def export_profile(self) -> ActionResult:
        if hasattr(self.app, "export_profile_package"):
            return self._safe_call("export_profile", self.app.export_profile_package, target=getattr(self.app, "current_profile_name", ""), success_message="Profile exported")
        return self.fail("Profile export is not available", action="export_profile")

    def import_profile(self) -> ActionResult:
        if hasattr(self.app, "import_profile_package"):
            return self._safe_call("import_profile", self.app.import_profile_package, success_message="Profile imported")
        return self.fail("Profile import is not available", action="import_profile")

    # ------------------------------------------------------------------
    # Strategy facade
    # ------------------------------------------------------------------
    def reload_strategy(self) -> ActionResult:
        return self._safe_call("reload_strategy", self.app.strategy_controller.reload, success_message="Strategy reloaded")

    def save_strategy(self) -> ActionResult:
        return self._safe_call("save_strategy", self.app.strategy_controller.save, success_message="Strategy saved")

    def reset_strategy(self) -> ActionResult:
        return self._safe_call("reset_strategy", self.app.strategy_controller.reset, success_message="Strategy reset")

    def apply_fake_strategy_test(self) -> ActionResult:
        if hasattr(self.app, "apply_selected_strategy_fake_test"):
            return self._safe_call("apply_fake_strategy_test", self.app.apply_selected_strategy_fake_test, success_message="Fake strategy test applied")
        return self.fail("Fake strategy test is not available", action="apply_fake_strategy_test")

    def run_fake_strategy_test(self) -> ActionResult:
        if hasattr(self.app, "run_selected_strategy_fake_test"):
            return self._safe_call("run_fake_strategy_test", self.app.run_selected_strategy_fake_test, success_message="Fake strategy test started")
        return self.fail("Fake strategy test is not available", action="run_fake_strategy_test")


    # ------------------------------------------------------------------
    # Template facade
    # ------------------------------------------------------------------
    def list_templates(self) -> list[dict[str, Any]]:
        manager = getattr(self.app, "template_manager", None)
        return manager.list_templates() if manager is not None else []

    def import_template(self, path: str) -> ActionResult:
        def _run():
            name = self.app.template_manager.import_template(path)
            return name
        return self._safe_call("import_template", _run, target=path, success_message="Template imported")

    def apply_template(self, name: str) -> ActionResult:
        def _run():
            return self.app.template_manager.apply_template(name)
        return self._safe_call("apply_template", _run, target=name, success_message="Template applied")

    def validate_template(self, name: str) -> ActionResult:
        def _run():
            return self.app.template_manager.validate_template(name)
        return self._safe_call("validate_template", _run, target=name, success_message="Template validated")

    # ------------------------------------------------------------------
    # Read-only snapshot for future API/CLI
    # ------------------------------------------------------------------
    def system_snapshot(self) -> dict[str, Any]:
        return {
            "profile": getattr(self.app, "current_profile_name", ""),
            "fake_mode": bool(getattr(self.app, "fake_mode", False)),
            "devices": self.device_names(),
            "running_devices": self.running_device_names(),
            "pcs": list(getattr(self.app, "pcs_configs", {}).keys()),
            "sampling_status": getattr(self.app, "last_sampling_status", ""),
            "heartbeat_status": getattr(self.app, "last_heartbeat_status", ""),
            "hv_status": getattr(self.app, "last_hv_status", ""),
            "last_error": getattr(self.app, "last_error_message", ""),
            "latest_snapshots": getattr(self.app, "latest_snapshots", {}),
        }
