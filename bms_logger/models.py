from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Any, List, Dict

@dataclass
class Device:
    name: str
    device_type: str  # "BMS" / "PCS"
    config: Dict


@dataclass
class Cluster:
    name: str
    bms_devices: List[Device] = field(default_factory=list)
    pcs_devices: List[Device] = field(default_factory=list)
    allocation_mode: str = "equal_split"
    fault_strategy: str = "stop_all"

    @property
    def pcs_device(self) -> Device | None:
        # Backward-compatible single PCS view.
        return self.pcs_devices[0] if self.pcs_devices else None

    @pcs_device.setter
    def pcs_device(self, value: Device | None) -> None:
        # Backward-compatible assignment used by older UI code.
        self.pcs_devices = [value] if value is not None else []


@dataclass
class Site:
    name: str
    clusters: List[Cluster] = field(default_factory=list)

@dataclass(slots=True)
class RegisterDef:
    name: str
    address: int
    scale: float = 1.0
    value_offset: float = 0.0
    data_type: str = "uint16"

    def decode(self, raw: int) -> float:
        return raw * self.scale + self.value_offset


@dataclass(slots=True)
class DeviceConfig:
    name: str
    host: str
    port: int = 502
    unit_id: int = 1
    poll_interval: float = 1.0
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeviceConfig":
        return cls(
            name=str(data.get("name", "BMS")),
            host=str(data.get("host", "127.0.0.1")),
            port=int(data.get("port", 502)),
            unit_id=int(data.get("unit_id", 1)),
            poll_interval=float(data.get("poll_interval", 1.0)),
            enabled=bool(data.get("enabled", True)),
        )


@dataclass(slots=True)
class SampleRecord:
    timestamp: datetime
    device_name: str
    host: str
    port: int
    unit_id: int
    soc_pct: float | None
    voltage_v: float | None
    current_a: float | None
    status: str
    error: str = ""

    def to_row(self) -> list[Any]:
        return [
            self.timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            self.device_name,
            self.host,
            self.port,
            self.unit_id,
            self.soc_pct,
            self.voltage_v,
            self.current_a,
            self.status,
            self.error,
        ]
