from __future__ import annotations

from datetime import datetime
from pathlib import Path
from ..paths import user_data_dir
from typing import Any

from ..action_result import ActionResult


class AuditController:
    """Central operation audit log for UI, controllers, service, and future API entrypoints."""

    def __init__(self, app: Any) -> None:
        self.app = app

    def log_result(self, result: ActionResult) -> None:
        self.log_action(
            source=result.source or "Unknown",
            action=result.action or "action",
            target=result.target,
            result="OK" if result.ok else "FAILED",
            detail=result.message or result.error,
        )

    def log_action(self, source: str, action: str, target: str = "", result: str = "", detail: str = "") -> None:
        message = self.format_message(source, action, target, result, detail)
        # Keep existing control log visible in UI.
        try:
            self.app.control_log(message)
        except Exception:
            try:
                self.app.log(message)
            except Exception:
                pass

        # Also write a compact machine-readable audit CSV.
        try:
            audit_dir = self.app.get_profile_path("logs")
            audit_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            audit_dir = user_data_dir() / "logs"
            audit_dir.mkdir(parents=True, exist_ok=True)

        path = audit_dir / f"audit_{datetime.now().strftime('%Y%m%d')}.csv"
        line = "{ts},{source},{action},{target},{result},{detail}\n".format(
            ts=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            source=self._csv(source),
            action=self._csv(action),
            target=self._csv(target),
            result=self._csv(result),
            detail=self._csv(detail),
        )
        try:
            if not path.exists():
                path.write_text("timestamp,source,action,target,result,detail\n", encoding="utf-8")
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass

    @staticmethod
    def format_message(source: str, action: str, target: str = "", result: str = "", detail: str = "") -> str:
        parts = [f"[AUDIT][{source}]", action]
        if target:
            parts.append(f"target={target}")
        if result:
            parts.append(f"result={result}")
        if detail:
            parts.append(f"detail={detail}")
        return " ".join(parts)

    @staticmethod
    def _csv(value: str) -> str:
        text = str(value).replace('"', '""')
        return f'"{text}"'
