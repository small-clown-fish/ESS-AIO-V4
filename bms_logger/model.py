from dataclasses import dataclass, field
from typing import List, Dict


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
        return self.pcs_devices[0] if self.pcs_devices else None

    @pcs_device.setter
    def pcs_device(self, value: Device | None) -> None:
        self.pcs_devices = [value] if value is not None else []


@dataclass
class Site:
    name: str
    clusters: List[Cluster] = field(default_factory=list)