from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class ActionResult:
    """Unified result object for UI, controllers, service actions, and future API calls.

    The first three fields intentionally match the old ControllerResult(ok, message, value)
    constructor order so existing code remains compatible.
    """

    ok: bool
    message: str = ""
    value: Any = None
    action: str = ""
    target: str = ""
    source: str = ""
    severity: str = "info"
    error: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    @classmethod
    def success(
        cls,
        message: str = "OK",
        *,
        action: str = "",
        target: str = "",
        source: str = "",
        value: Any = None,
    ) -> "ActionResult":
        return cls(True, message=message, value=value, action=action, target=target, source=source, severity="info")

    @classmethod
    def failure(
        cls,
        message: str = "Failed",
        *,
        action: str = "",
        target: str = "",
        source: str = "",
        error: str = "",
        value: Any = None,
        severity: str = "error",
    ) -> "ActionResult":
        return cls(False, message=message, value=value, action=action, target=target, source=source, severity=severity, error=error or message)

    @classmethod
    def cancelled(
        cls,
        message: str = "Cancelled",
        *,
        action: str = "",
        target: str = "",
        source: str = "",
    ) -> "ActionResult":
        return cls(False, message=message, action=action, target=target, source=source, severity="warning", error=message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "message": self.message,
            "value": self.value,
            "action": self.action,
            "target": self.target,
            "source": self.source,
            "severity": self.severity,
            "error": self.error,
            "timestamp": self.timestamp,
        }
