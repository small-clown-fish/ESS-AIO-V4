from __future__ import annotations

from typing import Any

from ..action_result import ActionResult


class ServiceActionController:
    """Execution boundary used by Service.

    Service decides *what* should happen. This controller owns *how* the app executes it.
    Every action returns ActionResult and is audit-logged so UI/API can reason about failures
    without parsing log text.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    def derating(self, device_name: str, reason: str, target_power: float | None = None) -> ActionResult:
        try:
            if target_power is None:
                result = self.app.execute_derating(device_name, reason)
            else:
                result = self.app.execute_derating_with_power(device_name, reason, target_power)
            return self._ensure_result(result, action="derating", target=device_name, detail=reason)
        except Exception as exc:
            return self._failure("derating", device_name, str(exc), detail=reason)

    def derating_recover(self, device_name: str) -> ActionResult:
        try:
            result = self.app.execute_derating_recover(device_name)
            return self._ensure_result(result, action="derating_recover", target=device_name)
        except Exception as exc:
            return self._failure("derating_recover", device_name, str(exc))

    def cutoff(self, device_name: str, reason: str) -> ActionResult:
        try:
            result = self.app.execute_cutoff(device_name, reason)
            return self._ensure_result(result, action="cutoff", target=device_name, detail=reason)
        except Exception as exc:
            return self._failure("cutoff", device_name, str(exc), detail=reason)

    def pcs_stop(self, device_name: str, source: str = "Service") -> ActionResult:
        try:
            result = self.app.execute_pcs_stop(device_name, source=source)
            return self._ensure_result(result, action="pcs_stop", target=device_name, source=source)
        except Exception as exc:
            return self._failure("pcs_stop", device_name, str(exc), source=source)

    def hv_off(self, device_name: str, source: str = "Service") -> ActionResult:
        try:
            result = self.app.execute_hv_off(device_name, source=source)
            return self._ensure_result(result, action="hv_off", target=device_name, source=source)
        except Exception as exc:
            return self._failure("hv_off", device_name, str(exc), source=source)

    def _ensure_result(
        self,
        result: Any,
        *,
        action: str,
        target: str,
        source: str = "Service",
        detail: str = "",
    ) -> ActionResult:
        if isinstance(result, ActionResult):
            if not result.action:
                result.action = action
            if not result.target:
                result.target = target
            if not result.source:
                result.source = source
            self._audit(result)
            return result

        # Existing UI execution methods may still return None after starting async work.
        wrapped = ActionResult.success(
            detail or f"{action} requested",
            action=action,
            target=target,
            source=source,
        )
        self._audit(wrapped)
        return wrapped

    def _failure(
        self,
        action: str,
        target: str,
        message: str,
        *,
        source: str = "Service",
        detail: str = "",
    ) -> ActionResult:
        result = ActionResult.failure(
            message,
            action=action,
            target=target,
            source=source,
            error=message,
            value={"detail": detail} if detail else None,
        )
        self._audit(result)
        return result

    def _audit(self, result: ActionResult) -> None:
        audit = getattr(self.app, "audit_controller", None)
        if audit is not None:
            audit.log_result(result)
