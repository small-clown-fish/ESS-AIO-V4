from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict


@dataclass
class TaskStatus:
    device_name: str
    status: str = "Idle"
    reads: int = 0
    errors: int = 0
    last_latency_ms: float = 0.0
    last_message: str = "-"
    last_update: str = "-"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_name": self.device_name,
            "status": self.status,
            "reads": self.reads,
            "errors": self.errors,
            "last_latency_ms": round(self.last_latency_ms, 1),
            "last_message": self.last_message,
            "last_update": self.last_update,
        }


def now_text() -> str:
    return datetime.now().strftime("%H:%M:%S")


class TaskStatusStore:
    def __init__(self) -> None:
        self._items: Dict[str, TaskStatus] = {}

    def update(self, device_name: str, **kwargs: Any) -> Dict[str, Any]:
        item = self._items.get(device_name)
        if item is None:
            item = TaskStatus(device_name=device_name)
            self._items[device_name] = item
        for key, value in kwargs.items():
            if hasattr(item, key):
                setattr(item, key, value)
        item.last_update = now_text()
        return item.to_dict()

    def remove(self, device_name: str) -> None:
        self._items.pop(device_name, None)

    def clear(self) -> None:
        self._items.clear()

    def rows(self) -> list[Dict[str, Any]]:
        return [item.to_dict() for item in self._items.values()]
