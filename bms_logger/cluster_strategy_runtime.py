from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .cluster_power_allocator import ClusterPowerAllocator

LogFn = Callable[[str], None]
SnapshotProvider = Callable[[str], Optional[Dict[str, Any]]]
CommandDispatcher = Callable[[str, float, str], bool]


@dataclass(slots=True)
class ClusterStrategySettings:
    cluster_name: str
    mode: str = "discharge"  # charge/discharge/signed
    target_power_kw: float = 0.0
    ramp_step_kw: float = 50.0
    ramp_interval_s: float = 5.0
    monitor_interval_s: float = 1.0
    bms_response_timeout_s: float = 5.0
    charge_stop_max_cell_mv: float = 3550.0
    discharge_stop_min_cell_mv: float = 2800.0
    positive_power_means: str = "discharge"  # discharge/charge
    allocation_mode: str = "equal_split"
    clamp_margin: float = 1.0
    timeout_action: str = "immediate_zero"  # immediate_zero/ramp_zero
    command_deadband_kw: float = 0.1


@dataclass(slots=True)
class BmsLimitResult:
    name: str
    ok: bool
    allowed_kw: float = 0.0
    reason: str = ""
    timed_out: bool = False
    cutoff: bool = False


@dataclass(slots=True)
class ClusterStrategyState:
    status: str = "IDLE"
    target_signed_kw: float = 0.0
    current_signed_kw: float = 0.0
    allowed_total_kw: float = 0.0
    final_cluster_kw: float = 0.0
    last_reason: str = ""
    allocation: Dict[str, float] = field(default_factory=dict)
    last_update_ts: float = 0.0


class ClusterStrategyWorker(threading.Thread):
    """Cluster-level charge/discharge dispatcher.

    It uses the latest BMS telemetry already collected by the BMS workers. One cluster
    can contain N BMS and M PCS. BMS limits are summed per cluster; the final cluster
    target is split across PCS in that same cluster.
    """

    def __init__(
        self,
        *,
        settings: ClusterStrategySettings,
        bms_names: List[str],
        pcs_names: List[str],
        pcs_configs: Dict[str, Dict[str, Any]],
        snapshot_provider: SnapshotProvider,
        dispatch_power: CommandDispatcher,
        log: Optional[LogFn] = None,
        state_callback: Optional[Callable[[str, ClusterStrategyState], None]] = None,
    ) -> None:
        super().__init__(daemon=True)
        self.settings = settings
        self.bms_names = [n for n in bms_names if str(n).strip()]
        self.pcs_names = [n for n in pcs_names if str(n).strip()]
        self.pcs_configs = pcs_configs
        self.snapshot_provider = snapshot_provider
        self.dispatch_power = dispatch_power
        self.log = log or (lambda _msg: None)
        self.state_callback = state_callback
        self.state = ClusterStrategyState()
        self._stop_event = threading.Event()
        self._last_dispatch: Dict[str, float] = {}

    def stop(self) -> None:
        self._stop_event.set()

    def _emit(self, status: str, reason: str = "") -> None:
        self.state.status = status
        self.state.last_reason = reason
        self.state.last_update_ts = time.time()
        if self.state_callback:
            try:
                self.state_callback(self.settings.cluster_name, self.state)
            except Exception:
                pass

    def _target_signed_power(self) -> float:
        target = abs(float(self.settings.target_power_kw))
        mode = (self.settings.mode or "discharge").lower()
        positive_means = (self.settings.positive_power_means or "discharge").lower()
        if mode == "signed":
            return float(self.settings.target_power_kw)
        if mode == "charge":
            return -target if positive_means == "discharge" else target
        return target if positive_means == "discharge" else -target

    def _operation_from_signed_power(self, signed_kw: float) -> str:
        mode = (self.settings.mode or "discharge").lower()
        if mode in {"charge", "discharge"}:
            return mode
        positive_means = (self.settings.positive_power_means or "discharge").lower()
        if signed_kw >= 0:
            return "discharge" if positive_means == "discharge" else "charge"
        return "charge" if positive_means == "discharge" else "discharge"

    @staticmethod
    def _positive_number(value: Any) -> Optional[float]:
        """Positive physical value used for voltage/cell thresholds.

        Voltage and cell values must be truly positive. Do not use this helper for
        charge/discharge limits because many BMS point tables publish charge
        limits as negative numbers.
        """
        try:
            number = float(value)
        except Exception:
            return None
        if number <= 0:
            return None
        if number in {255.0, 65535.0, 6553.5, 655350.0}:
            return None
        return number

    @staticmethod
    def _limit_magnitude(value: Any) -> Optional[float]:
        """Return an absolute limit magnitude for BMS current/power limits.

        Site convention can be signed: charge limits may be negative while
        discharge limits are positive. For limiting PCS power we only need the
        available magnitude, so -1200kW and +1200kW both mean 1200kW allowed.
        """
        try:
            number = float(value)
        except Exception:
            return None
        abs_number = abs(number)
        if abs_number <= 0:
            return None
        if abs_number in {255.0, 65535.0, 6553.5, 655350.0}:
            return None
        return abs_number

    @staticmethod
    def _snapshot_age_s(snapshot: Dict[str, Any]) -> Optional[float]:
        ts = snapshot.get("_received_ts") or snapshot.get("received_ts") or snapshot.get("last_ok_ts")
        try:
            return max(0.0, time.time() - float(ts))
        except Exception:
            return None

    def _bms_allowed_power(self, bms_name: str, operation: str) -> BmsLimitResult:
        snapshot = self.snapshot_provider(bms_name) or {}
        if not snapshot:
            return BmsLimitResult(name=bms_name, ok=False, reason="no BMS snapshot", timed_out=True)

        age = self._snapshot_age_s(snapshot)
        if age is None or age > float(self.settings.bms_response_timeout_s):
            return BmsLimitResult(
                name=bms_name,
                ok=False,
                reason=f"BMS response timeout ({age if age is not None else 'unknown'}s)",
                timed_out=True,
            )

        max_cell = self._positive_number(snapshot.get("max_cell_voltage"))
        min_cell = self._positive_number(snapshot.get("min_cell_voltage"))
        if operation == "charge" and max_cell is not None and max_cell >= float(self.settings.charge_stop_max_cell_mv):
            return BmsLimitResult(name=bms_name, ok=False, reason=f"charge cutoff max_cell={max_cell}mV", cutoff=True)
        if operation == "discharge" and min_cell is not None and min_cell <= float(self.settings.discharge_stop_min_cell_mv):
            return BmsLimitResult(name=bms_name, ok=False, reason=f"discharge cutoff min_cell={min_cell}mV", cutoff=True)

        voltage_v = self._positive_number(snapshot.get("system_voltage"))
        if operation == "charge":
            power_key = "max_charge_power_allowed"
            current_key = "max_charge_current_allowed"
        else:
            power_key = "max_discharge_power_allowed"
            current_key = "max_discharge_current_allowed"

        candidates: List[tuple[str, float]] = []
        power_kw = self._limit_magnitude(snapshot.get(power_key))
        if power_kw is not None:
            candidates.append((power_key, power_kw))
        current_a = self._limit_magnitude(snapshot.get(current_key))
        if current_a is not None and voltage_v is not None:
            candidates.append((f"{current_key}*system_voltage/1000", current_a * voltage_v / 1000.0))
        if not candidates:
            return BmsLimitResult(name=bms_name, ok=False, reason=f"no valid BMS limit ({power_key}/{current_key})")
        source, allowed_kw = min(candidates, key=lambda item: item[1])
        allowed_kw *= max(0.0, float(self.settings.clamp_margin or 1.0))
        return BmsLimitResult(name=bms_name, ok=True, allowed_kw=allowed_kw, reason=source)

    def _next_ramped_power(self, desired_signed_kw: float) -> float:
        current = float(self.state.current_signed_kw)
        step = max(0.1, float(self.settings.ramp_step_kw))
        if abs(desired_signed_kw - current) <= step:
            return desired_signed_kw
        return current + step if desired_signed_kw > current else current - step

    def _dispatch_allocation(self, allocation: Dict[str, float], label: str) -> None:
        for pcs_name, power_kw in allocation.items():
            last = self._last_dispatch.get(pcs_name)
            if last is not None and abs(last - power_kw) < float(self.settings.command_deadband_kw):
                continue
            ok = self.dispatch_power(pcs_name, float(power_kw), label)
            if ok:
                self._last_dispatch[pcs_name] = float(power_kw)

    def dispatch_zero(self, reason: str) -> None:
        allocation = {name: 0.0 for name in self.pcs_names}
        self.state.current_signed_kw = 0.0
        self.state.final_cluster_kw = 0.0
        self.state.allocation = allocation
        self._dispatch_allocation(allocation, f"cluster_strategy_zero:{reason}")
        self._emit("ZERO", reason)

    def _step_once(self) -> None:
        if not self.pcs_names:
            self._emit("FAULT", "no PCS in cluster")
            return
        if not self.bms_names:
            self.dispatch_zero("no BMS in cluster")
            return

        target_signed = self._target_signed_power()
        self.state.target_signed_kw = target_signed
        operation = self._operation_from_signed_power(target_signed)

        bms_results = [self._bms_allowed_power(name, operation) for name in self.bms_names]
        hard_faults = [r for r in bms_results if r.timed_out or r.cutoff]
        if hard_faults:
            reason = "; ".join(f"{r.name}:{r.reason}" for r in hard_faults[:3])
            if any(r.cutoff for r in hard_faults) or self.settings.timeout_action == "immediate_zero":
                self.dispatch_zero(reason)
                self._emit("CUTOFF" if any(r.cutoff for r in hard_faults) else "BMS_TIMEOUT", reason)
                return

        ok_results = [r for r in bms_results if r.ok]
        allowed_total = sum(r.allowed_kw for r in ok_results)
        self.state.allowed_total_kw = allowed_total
        if allowed_total <= 0:
            reasons = "; ".join(f"{r.name}:{r.reason}" for r in bms_results[:5])
            self.dispatch_zero(f"cluster allowed power is 0; {reasons}")
            return

        requested_after_ramp = self._next_ramped_power(target_signed)
        final_abs = min(abs(requested_after_ramp), allowed_total)
        final_signed = final_abs if requested_after_ramp >= 0 else -final_abs
        self.state.current_signed_kw = final_signed
        self.state.final_cluster_kw = final_signed

        allocation = ClusterPowerAllocator.allocate(
            final_signed,
            self.pcs_configs,
            self.pcs_names,
            self.settings.allocation_mode,
        )
        self.state.allocation = allocation
        reasons = ", ".join(f"{r.name}:{r.allowed_kw:.1f}kW({r.reason})" for r in ok_results)
        clamped = abs(final_signed) < abs(requested_after_ramp) - 1e-6
        status = "LIMITED_BY_BMS" if clamped else ("RAMPING" if abs(final_signed - target_signed) > 0.1 else "RUNNING")
        self._dispatch_allocation(allocation, f"cluster_strategy_{self.settings.cluster_name}")
        self._emit(status, f"operation={operation}; allowed_total={allowed_total:.1f}kW; {reasons}")

    def run(self) -> None:
        self._emit("STARTING", f"cluster={self.settings.cluster_name}")
        self.log(
            f"[CLUSTER_STRATEGY] start {self.settings.cluster_name}: "
            f"mode={self.settings.mode}, target={self.settings.target_power_kw}kW, "
            f"BMS={self.bms_names}, PCS={self.pcs_names}"
        )
        next_ramp_ts = 0.0
        while not self._stop_event.is_set():
            now = time.monotonic()
            try:
                # Check BMS/cutoff every monitor cycle. Power changes are rate-limited by ramp_interval.
                if now >= next_ramp_ts:
                    self._step_once()
                    next_ramp_ts = now + max(0.2, float(self.settings.ramp_interval_s))
                else:
                    # BMS timeout/cutoff should not wait for a long ramp interval.
                    target_signed = self._target_signed_power()
                    operation = self._operation_from_signed_power(target_signed)
                    for name in self.bms_names:
                        result = self._bms_allowed_power(name, operation)
                        if result.timed_out or result.cutoff:
                            reason = f"{name}:{result.reason}"
                            self.dispatch_zero(reason)
                            next_ramp_ts = now + max(0.2, float(self.settings.ramp_interval_s))
                            break
            except Exception as exc:
                self.dispatch_zero(f"strategy exception: {exc}")
                self.log(f"[CLUSTER_STRATEGY][ERROR] {self.settings.cluster_name}: {exc}")
            self._stop_event.wait(max(0.2, float(self.settings.monitor_interval_s)))

        self.dispatch_zero("strategy stopped")
        self._emit("STOPPED", "operator stopped")
        self.log(f"[CLUSTER_STRATEGY] stopped {self.settings.cluster_name}")
