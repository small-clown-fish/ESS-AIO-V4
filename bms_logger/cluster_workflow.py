from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from .cluster_power_allocator import ClusterPowerAllocator


LogCallback = Callable[[str], None]


@dataclass(slots=True)
class ClusterDispatchSettings:
    target_power_kw: float
    allocation_mode: str = "equal_split"
    clamp_margin: float = 1.0
    use_bms_limit_clamp: bool = True


class ClusterDispatchController:
    """Lightweight cluster-level dispatcher.

    This class intentionally reuses existing BMS/PCS clients and profile-driven
    PCS points. It does not replace the conservative single-PCS workflow; it adds
    the EMS step that converts one cluster target into N PCS setpoints.
    """

    def __init__(
        self,
        bms_client: Any,
        pcs_clients: Dict[str, Any],
        pcs_configs: Dict[str, Dict[str, Any]],
        settings: ClusterDispatchSettings,
        log_callback: Optional[LogCallback] = None,
    ) -> None:
        self.bms = bms_client
        self.pcs_clients = pcs_clients
        self.pcs_configs = pcs_configs
        self.settings = settings
        self.log_callback = log_callback or (lambda msg: None)

    def log(self, msg: str) -> None:
        self.log_callback(msg)

    @staticmethod
    def _positive_number(value: Any) -> Optional[float]:
        try:
            number = float(value)
        except Exception:
            return None
        if number <= 0:
            return None
        if number in {255.0, 65535.0, 6553.5, 655350.0}:
            return None
        return abs(number)

    def _read_allowed_cluster_power_kw(self, operation: str) -> tuple[Optional[float], str]:
        snapshot = dict(self.bms.read_telemetry_snapshot() or {})
        voltage_v = self._positive_number(snapshot.get("system_voltage"))
        if operation == "charge":
            power_key = "max_charge_power_allowed"
            current_key = "max_charge_current_allowed"
        else:
            power_key = "max_discharge_power_allowed"
            current_key = "max_discharge_current_allowed"
        candidates: list[tuple[str, float]] = []
        p = self._positive_number(snapshot.get(power_key))
        if p is not None:
            candidates.append((power_key, p))
        i = self._positive_number(snapshot.get(current_key))
        if i is not None and voltage_v is not None:
            candidates.append((f"{current_key}*system_voltage/1000", i * voltage_v / 1000.0))
        if not candidates:
            return None, f"no valid BMS limit ({power_key}/{current_key})"
        return min(candidates, key=lambda item: item[1])

    def dispatch_once(self, operation: str = "discharge") -> Dict[str, float]:
        requested = float(self.settings.target_power_kw)
        allowed_kw = None
        source = "clamp disabled"
        if self.settings.use_bms_limit_clamp:
            allowed_kw, source = self._read_allowed_cluster_power_kw(operation)
        final_total, clamped, reason = ClusterPowerAllocator.clamp_total_power(
            requested,
            allowed_kw,
            self.settings.clamp_margin,
        ) if self.settings.use_bms_limit_clamp else (requested, False, "BMS clamp disabled")
        names = list(self.pcs_clients.keys())
        allocation = ClusterPowerAllocator.allocate(
            final_total,
            self.pcs_configs,
            names,
            self.settings.allocation_mode,
        )
        self.log(
            f"[CLUSTER] requested={requested:.3f}kW, allowed={allowed_kw}, source={source}, "
            f"final_total={final_total:.3f}kW, clamped={clamped}, allocation={allocation}"
        )
        for name, power_kw in allocation.items():
            client = self.pcs_clients.get(name)
            if client is None:
                continue
            self.log(f"[CLUSTER] Set {name} active power = {power_kw:.3f}kW")
            client.set_active_power(int(round(power_kw)))
        return allocation

    def stop_all(self) -> None:
        for name, client in self.pcs_clients.items():
            try:
                self.log(f"[CLUSTER] Stop {name}: set power=0")
                client.set_active_power(0)
            except Exception as exc:
                self.log(f"[CLUSTER] Failed to set {name} power=0: {exc}")
            try:
                self.log(f"[CLUSTER] Stop {name}: PCS stop")
                client.stop()
            except Exception as exc:
                self.log(f"[CLUSTER] Failed to stop {name}: {exc}")
