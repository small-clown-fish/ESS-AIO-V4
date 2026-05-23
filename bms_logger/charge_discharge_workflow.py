from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .modbus_client import BmsModbusClient
from .pcs_client import PcsClient


LogCallback = Callable[[str], None]
ProgressCallback = Callable[[str], None]


@dataclass
class ChargeDischargeSettings:
    mode: str  # "charge", "discharge", "signed"
    target_power_kw: float
    ramp_step_kw: float = 20.0
    ramp_interval_s: float = 2.0
    monitor_interval_s: float = 1.0
    step_timeout_s: float = 30.0
    auto_bms_hv: bool = True
    auto_pcs_start: bool = True
    auto_pcs_stop_on_finish: bool = True
    auto_bms_hv_off_on_stop: bool = False
    positive_power_means: str = "discharge"  # "discharge" or "charge"
    require_pcs_remote: bool = True
    require_dc_breaker_closed: bool = False
    bms_heartbeat_interval_s: float = 1.0
    pcs_heartbeat_interval_s: float = 1.0
    use_bms_limit_clamp: bool = True
    power_limit_mode: str = "target_with_clamp"  # "target_with_clamp" or "follow_bms_max"
    clamp_margin: float = 1.0


class ChargeDischargeWorkflowController:
    """BMS + PCS charge/discharge workflow.

    This controller intentionally implements a conservative EMS-like sequence:
    precheck -> BMS HV on -> PCS start -> ramp active power -> monitor -> stop.

    It is designed for field commissioning. Any failed check triggers a safe stop:
    set PCS active power to 0, then PCS stop. BMS HV off is optional because some
    sites prefer keeping HV on after a normal stop.
    """

    BMS_FAULT_STATUS_VALUES = {5}
    BMS_HV_READY_VALUE = 1
    BMS_HV_OFF_VALUE = 0
    PCS_STOPPED_VALUES = {0}
    PCS_FAULT_VALUES = {2}
    PCS_RUNNING_OR_READY_VALUES = {1, 3, 4, 5, 6}

    def __init__(
        self,
        bms_client: BmsModbusClient,
        pcs_client: PcsClient,
        settings: ChargeDischargeSettings,
        log_callback: Optional[LogCallback] = None,
        progress_callback: Optional[ProgressCallback] = None,
        stop_flag: Optional[Callable[[], bool]] = None,
    ) -> None:
        self.bms = bms_client
        self.pcs = pcs_client
        self.settings = settings
        self.log_callback = log_callback or (lambda msg: None)
        self.progress_callback = progress_callback or (lambda state: None)
        self.stop_flag = stop_flag or (lambda: False)
        self._bms_heartbeat_value = 0
        self._pcs_heartbeat_value = 0
        self._last_bms_heartbeat = 0.0
        self._last_pcs_heartbeat = 0.0
        self._last_commanded_power_kw: float = 0.0

    def log(self, message: str) -> None:
        self.log_callback(message)

    def progress(self, state: str) -> None:
        self.progress_callback(state)
        self.log(f"[CD] {state}")

    def _should_stop(self) -> bool:
        return bool(self.stop_flag())

    def _sleep_checked(self, seconds: float) -> bool:
        end = time.time() + max(0.0, seconds)
        while time.time() < end:
            if self._should_stop():
                return False
            time.sleep(min(0.1, max(0.0, end - time.time())))
        return True

    def _wait_until(self, title: str, predicate: Callable[[], bool], timeout: Optional[float] = None) -> bool:
        timeout = self.settings.step_timeout_s if timeout is None else timeout
        start = time.time()
        self.log(f"[CD] Waiting: {title}, timeout={timeout}s")
        while time.time() - start <= timeout:
            if self._should_stop():
                self.log(f"[CD] Cancelled while waiting: {title}")
                return False
            self._send_heartbeats_if_due()
            try:
                if predicate():
                    self.log(f"[CD] OK: {title}")
                    return True
            except Exception as exc:
                self.log(f"[CD] Wait check error for {title}: {exc}")
            time.sleep(self.settings.monitor_interval_s)
        self.log(f"[CD] TIMEOUT: {title}")
        return False

    def _send_heartbeats_if_due(self) -> None:
        now = time.time()
        if now - self._last_bms_heartbeat >= self.settings.bms_heartbeat_interval_s:
            try:
                self.bms.write_heartbeat(self._bms_heartbeat_value)
                self._bms_heartbeat_value = (self._bms_heartbeat_value + 1) % 256
            except Exception as exc:
                self.log(f"[CD] BMS heartbeat failed: {exc}")
            self._last_bms_heartbeat = now

        if now - self._last_pcs_heartbeat >= self.settings.pcs_heartbeat_interval_s:
            try:
                self.pcs.send_heartbeat(self._pcs_heartbeat_value)
                self._pcs_heartbeat_value = (self._pcs_heartbeat_value + 1) % 65536
            except Exception as exc:
                self.log(f"[CD] PCS heartbeat failed: {exc}")
            self._last_pcs_heartbeat = now

    def _target_signed_power(self) -> float:
        target = abs(float(self.settings.target_power_kw))
        if self.settings.mode == "signed":
            return float(self.settings.target_power_kw)
        if self.settings.mode == "discharge":
            return target if self.settings.positive_power_means == "discharge" else -target
        if self.settings.mode == "charge":
            return -target if self.settings.positive_power_means == "discharge" else target
        raise RuntimeError(f"Unsupported workflow mode: {self.settings.mode}")


    def _operation_from_signed_power(self, signed_power_kw: float) -> str:
        """Return logical battery operation: charge/discharge.

        PCS active-power sign differs by vendor/site. positive_power_means tells the
        workflow how to translate a signed PCS setpoint into battery operation.
        """
        if self.settings.mode in {"charge", "discharge"}:
            return self.settings.mode
        if signed_power_kw >= 0:
            return "discharge" if self.settings.positive_power_means == "discharge" else "charge"
        return "charge" if self.settings.positive_power_means == "discharge" else "discharge"

    @staticmethod
    def _positive_number(value: Any) -> Optional[float]:
        try:
            number = float(value)
        except Exception:
            return None
        if number <= 0:
            return None
        # Filter common invalid placeholders from BMS/Modbus protocols.
        if number in {255.0, 65535.0, 6553.5, 655350.0}:
            return None
        return abs(number)

    def _read_bms_allowed_power_kw(self, operation: str) -> tuple[Optional[float], str]:
        """Read BMS current/power limits and return allowed kW.

        Priority:
        1. Dedicated BMS allowed power register when valid.
        2. Current limit * system voltage / 1000.
        3. Min of valid candidates if both exist.
        """
        snapshot = self._read_bms_snapshot_safe()
        voltage_v = self._positive_number(snapshot.get("system_voltage"))
        if operation == "charge":
            power_key = "max_charge_power_allowed"
            current_key = "max_charge_current_allowed"
        else:
            power_key = "max_discharge_power_allowed"
            current_key = "max_discharge_current_allowed"

        candidates: list[tuple[str, float]] = []
        power_kw = self._positive_number(snapshot.get(power_key))
        if power_kw is not None:
            candidates.append((power_key, power_kw))

        current_a = self._positive_number(snapshot.get(current_key))
        if current_a is not None and voltage_v is not None:
            candidates.append((f"{current_key}*system_voltage/1000", current_a * voltage_v / 1000.0))

        if not candidates:
            return None, f"no valid BMS limit ({power_key}/{current_key})"

        source, allowed_kw = min(candidates, key=lambda item: item[1])
        margin = max(0.0, float(self.settings.clamp_margin or 1.0))
        return allowed_kw * margin, source

    def _apply_bms_power_clamp(self, requested_signed_kw: float) -> float:
        if not self.settings.use_bms_limit_clamp:
            return requested_signed_kw

        operation = self._operation_from_signed_power(requested_signed_kw)
        allowed_kw, source = self._read_bms_allowed_power_kw(operation)
        if allowed_kw is None:
            self.log(
                f"[CD][CLAMP] skipped: requested={requested_signed_kw:.3f}kW, "
                f"operation={operation}, reason={source}"
            )
            return requested_signed_kw

        if self.settings.power_limit_mode == "follow_bms_max":
            final_abs = allowed_kw
        else:
            final_abs = min(abs(requested_signed_kw), abs(allowed_kw))

        final_signed = final_abs if requested_signed_kw >= 0 else -final_abs
        active = abs(final_signed) < abs(requested_signed_kw) - 1e-9
        mode = self.settings.power_limit_mode
        self.log(
            f"[CD][CLAMP] mode={mode}, operation={operation}, source={source}, "
            f"requested={requested_signed_kw:.3f}kW, allowed={allowed_kw:.3f}kW, "
            f"final={final_signed:.3f}kW, active={active}"
        )
        return final_signed

    def _set_pcs_active_power_with_record(self, power_kw: float) -> bool:
        ok = self.pcs.set_active_power(int(round(power_kw)))
        if ok:
            self._last_commanded_power_kw = float(power_kw)
        return ok

    def _read_bms_snapshot_safe(self) -> dict[str, Any]:
        snapshot = self.bms.read_telemetry_snapshot()
        if not snapshot:
            raise RuntimeError("BMS snapshot read failed")
        return dict(snapshot)

    def precheck(self) -> None:
        self.progress("PRECHECK")
        bms_snapshot = self._read_bms_snapshot_safe()
        bms_status = bms_snapshot.get("bms_status")
        soc = bms_snapshot.get("soc")
        sys_voltage = bms_snapshot.get("system_voltage")
        max_cell = bms_snapshot.get("max_cell_voltage")
        min_cell = bms_snapshot.get("min_cell_voltage")
        max_temp = bms_snapshot.get("max_cell_temperature")
        min_temp = bms_snapshot.get("min_cell_temperature")

        self.log(
            "[CD] BMS precheck: "
            f"status={bms_status}, soc={soc}, U={sys_voltage}, "
            f"cell_max={max_cell}, cell_min={min_cell}, T_max={max_temp}, T_min={min_temp}"
        )
        if bms_status in self.BMS_FAULT_STATUS_VALUES:
            raise RuntimeError(f"BMS is in fault status: {bms_status}")
        if soc is not None and not (0 <= float(soc) <= 100):
            raise RuntimeError(f"BMS SOC out of range: {soc}")

        try:
            if self.settings.require_pcs_remote and not self.pcs.is_online():
                raise RuntimeError("PCS remote/online status is not active")
        except Exception as exc:
            if self.settings.require_pcs_remote:
                raise
            self.log(f"[CD] PCS remote check skipped/failed: {exc}")

        try:
            run_status = self.pcs.get_run_status()
            fault_status = self.pcs.get_fault_status()
            alarm_status = self.pcs.get_alarm_status()
            self.log(
                "[CD] PCS precheck: "
                f"run_status={run_status}, fault_status={fault_status}, alarm_status={alarm_status}"
            )
            if int(run_status) in self.PCS_FAULT_VALUES:
                raise RuntimeError(f"PCS run_status indicates fault: {run_status}")
            if int(fault_status) != 0:
                raise RuntimeError(f"PCS fault_status is active: {fault_status}")
        except Exception:
            raise

    def bms_hv_on(self) -> None:
        self.progress("BMS_HV_ON")
        if not self.settings.auto_bms_hv:
            self.log("[CD] Auto BMS HV ON disabled, only checking 0301")
            hv_ready = self.bms.read_bms_power_on()
            if hv_ready != self.BMS_HV_READY_VALUE:
                raise RuntimeError(f"BMS HV is not ready, 0301={hv_ready}")
            return

        self._send_heartbeats_if_due()
        self.log("[CD] Write BMS 0381=2 Power On cmd")
        if not self.bms.write_ems_cmd_power_on():
            raise RuntimeError("Write BMS 0381=2 failed")

        ok = self._wait_until(
            "BMS 0301 == 1 HV ready",
            lambda: self.bms.read_bms_power_on() == self.BMS_HV_READY_VALUE,
        )
        if not ok:
            raise RuntimeError("BMS HV ready timeout")

        self.log("[CD] Write BMS 0381=1 Stay")
        if not self.bms.write_ems_cmd_stay():
            raise RuntimeError("Write BMS 0381=1 failed after HV ON")

    def pcs_start(self) -> None:
        self.progress("PCS_START")
        if not self.settings.auto_pcs_start:
            self.log("[CD] Auto PCS start disabled")
            return
        self._send_heartbeats_if_due()
        self.log("[CD] PCS start command")
        if not self.pcs.start():
            raise RuntimeError("PCS start command failed")
        ok = self._wait_until(
            "PCS run_status ready/running",
            lambda: int(self.pcs.get_run_status()) in self.PCS_RUNNING_OR_READY_VALUES,
        )
        if not ok:
            raise RuntimeError("PCS start ready timeout")
        if self.settings.require_dc_breaker_closed:
            ok = self._wait_until("PCS DC breaker closed", lambda: self.pcs.is_dc_breaker_closed())
            if not ok:
                raise RuntimeError("PCS DC breaker close timeout")

    def ramp_power(self) -> None:
        self.progress("RAMP_POWER")
        requested_target = self._target_signed_power()
        step = abs(float(self.settings.ramp_step_kw)) or abs(requested_target)
        current = 0.0
        if requested_target == 0:
            self.log("[CD] Target power is 0, writing 0 only")
            if not self._set_pcs_active_power_with_record(0):
                raise RuntimeError("PCS set active power 0 failed")
            return

        effective_target = self._apply_bms_power_clamp(requested_target)
        self.log(
            f"[CD] Ramp active power requested={requested_target:.3f} kW, "
            f"effective={effective_target:.3f} kW, step={step} kW"
        )
        while abs(current - effective_target) > 1e-9:
            if self._should_stop():
                raise RuntimeError("Workflow cancelled during ramp")
            effective_target = self._apply_bms_power_clamp(requested_target)
            direction = 1.0 if effective_target > current else -1.0
            next_value = current + direction * step
            if (direction > 0 and next_value > effective_target) or (direction < 0 and next_value < effective_target):
                next_value = effective_target
            self._send_heartbeats_if_due()
            self._monitor_safety_once()
            self.log(f"[CD] Set PCS active power = {next_value:.3f} kW")
            if not self._set_pcs_active_power_with_record(next_value):
                raise RuntimeError(f"PCS set active power failed: {next_value}")
            current = next_value
            if abs(current - effective_target) > 1e-9 and not self._sleep_checked(self.settings.ramp_interval_s):
                raise RuntimeError("Workflow cancelled during ramp interval")

    def monitor_running(self, duration_s: float = 3.0) -> None:
        self.progress("RUNNING_MONITOR")
        start = time.time()
        while time.time() - start < duration_s:
            if self._should_stop():
                raise RuntimeError("Workflow cancelled during running monitor")
            self._send_heartbeats_if_due()
            self._monitor_safety_once()
            time.sleep(self.settings.monitor_interval_s)

    def _monitor_safety_once(self) -> None:
        bms_status = self.bms.read_bms_status()
        if bms_status in self.BMS_FAULT_STATUS_VALUES:
            raise RuntimeError(f"BMS fault during workflow: bms_status={bms_status}")
        pcs_run = int(self.pcs.get_run_status())
        pcs_fault = int(self.pcs.get_fault_status())
        if pcs_run in self.PCS_FAULT_VALUES or pcs_fault != 0:
            raise RuntimeError(f"PCS fault during workflow: run_status={pcs_run}, fault_status={pcs_fault}")
        if self.settings.use_bms_limit_clamp and abs(self._last_commanded_power_kw) > 0.1:
            adjusted = self._apply_bms_power_clamp(self._last_commanded_power_kw)
            if abs(adjusted) < abs(self._last_commanded_power_kw) - 0.5:
                self.log(
                    f"[CD][CLAMP] dynamic reduction: "
                    f"last={self._last_commanded_power_kw:.3f}kW -> adjusted={adjusted:.3f}kW"
                )
                if not self._set_pcs_active_power_with_record(adjusted):
                    raise RuntimeError(f"PCS dynamic clamp set active power failed: {adjusted}")

    def ramp_down_to_zero(self) -> None:
        self.progress("RAMP_DOWN")
        try:
            actual = float(self.pcs.get_active_power())
        except Exception:
            actual = 0.0
        step = abs(float(self.settings.ramp_step_kw)) or 20.0
        if abs(actual) <= 0.1:
            self._set_pcs_active_power_with_record(0)
            return
        direction = -1.0 if actual > 0 else 1.0
        current = actual
        while abs(current) > 0.1:
            if self._should_stop():
                break
            next_value = current + direction * step
            if (current > 0 and next_value < 0) or (current < 0 and next_value > 0):
                next_value = 0.0
            self._send_heartbeats_if_due()
            self.log(f"[CD] Ramp down PCS active power = {next_value:.3f} kW")
            self._set_pcs_active_power_with_record(next_value)
            current = next_value
            if current != 0.0:
                self._sleep_checked(self.settings.ramp_interval_s)
        self._set_pcs_active_power_with_record(0)

    def stop_sequence(self, hv_off: Optional[bool] = None) -> None:
        hv_off = self.settings.auto_bms_hv_off_on_stop if hv_off is None else hv_off
        self.progress("STOP_SEQUENCE")
        try:
            self.ramp_down_to_zero()
        except Exception as exc:
            self.log(f"[CD] Ramp-down warning: {exc}; forcing 0 kW")
            try:
                self._set_pcs_active_power_with_record(0)
            except Exception:
                pass
        if self.settings.auto_pcs_stop_on_finish:
            try:
                self.log("[CD] PCS stop command")
                self.pcs.stop()
            except Exception as exc:
                self.log(f"[CD] PCS stop warning: {exc}")
        if hv_off:
            try:
                self.log("[CD] Write BMS 0381=3 Power Off cmd")
                self.bms.write_ems_cmd_power_off()
                self._wait_until(
                    "BMS 0301 == 0 HV off",
                    lambda: self.bms.read_bms_power_on() == self.BMS_HV_OFF_VALUE,
                )
                self.log("[CD] Write BMS 0381=1 Stay after HV OFF")
                self.bms.write_ems_cmd_stay()
            except Exception as exc:
                self.log(f"[CD] BMS HV OFF warning: {exc}")

    def emergency_stop(self, reason: str) -> None:
        self.progress("FAULT_STOP")
        self.log(f"[CD] EMERGENCY STOP: {reason}")
        try:
            self._set_pcs_active_power_with_record(0)
        except Exception as exc:
            self.log(f"[CD] Emergency set 0 failed: {exc}")
        try:
            self.pcs.stop()
        except Exception as exc:
            self.log(f"[CD] Emergency PCS stop failed: {exc}")

    def run_start(self) -> bool:
        try:
            self.progress("CONNECT")
            if not self.bms.connect():
                raise RuntimeError("BMS connect failed")
            if not self.pcs.connect():
                raise RuntimeError("PCS connect failed")
            self.precheck()
            self.bms_hv_on()
            self.pcs_start()
            self.ramp_power()
            self.monitor_running(duration_s=3.0)
            self.progress("RUNNING")
            return True
        except Exception as exc:
            self.emergency_stop(str(exc))
            raise
        finally:
            try:
                self.bms.close()
            except Exception:
                pass
            try:
                self.pcs.close()
            except Exception:
                pass

    def run_stop(self) -> bool:
        try:
            self.progress("CONNECT_STOP")
            if not self.bms.connect():
                raise RuntimeError("BMS connect failed")
            if not self.pcs.connect():
                raise RuntimeError("PCS connect failed")
            self.stop_sequence(hv_off=self.settings.auto_bms_hv_off_on_stop)
            self.progress("STOP_DONE")
            return True
        finally:
            try:
                self.bms.close()
            except Exception:
                pass
            try:
                self.pcs.close()
            except Exception:
                pass


class ChargeDischargeWorkflowWorker(threading.Thread):
    def __init__(
        self,
        action: str,
        controller: ChargeDischargeWorkflowController,
        device_name: str,
        log_callback: Optional[Callable[[str, str], None]] = None,
        progress_callback: Optional[Callable[[str, str], None]] = None,
        finished_callback: Optional[Callable[[str, str, bool, str], None]] = None,
    ) -> None:
        super().__init__(daemon=True)
        self.action = action  # "start" or "stop"
        self.controller = controller
        self.device_name = device_name
        self.log_callback = log_callback
        self.progress_callback = progress_callback
        self.finished_callback = finished_callback
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True

    def should_stop(self) -> bool:
        return self._stop_requested

    def _log(self, message: str) -> None:
        if self.log_callback:
            self.log_callback(self.device_name, message)

    def _progress(self, state: str) -> None:
        if self.progress_callback:
            self.progress_callback(self.device_name, state)

    def run(self) -> None:
        self.controller.stop_flag = self.should_stop
        self.controller.log_callback = self._log
        self.controller.progress_callback = self._progress
        ok = False
        message = ""
        try:
            if self.action == "start":
                ok = self.controller.run_start()
                message = "Charge/discharge workflow started and power target reached."
            elif self.action == "stop":
                ok = self.controller.run_stop()
                message = "Charge/discharge workflow stopped."
            else:
                raise RuntimeError(f"Unknown workflow action: {self.action}")
        except Exception as exc:
            ok = False
            message = str(exc)
            self._log(f"[CD] FAILED: {message}")
        if self.finished_callback:
            self.finished_callback(self.device_name, self.action, ok, message)
