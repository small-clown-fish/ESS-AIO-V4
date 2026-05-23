from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from .modbus_client import BmsModbusClient
from .pcs_client import PcsClient

# from bms_logger.fake_pcs_client import FakePcsClient as PcsClient
# from bms_logger.fake_bms_client import FakeBmsClient as BmsModbusClient

class HvWorkflowController:
    """
    第一版上下高压流程控制器

    HV ON:
    1. 检查 0302 == 1
    2. 检查 PCS dc breaker == open
    3. 写 0381 = 2
    4. 等待 0301 == 1
    5. 调 PCS 执行 HV ON
    6. 写 0381 = 1

    HV OFF:
    1. 检查 PCS active power == 0
    2. 写 0381 = 3
    3. 等待 0301 == 0
    4. 写 0381 = 1
    """

    def __init__(
            self,
            bms_client: BmsModbusClient,
            pcs_client: PcsClient,
            log_callback: Optional[Callable[[str], None]] = None,
            step_timeout: float = 30.0,
            poll_interval: float = 1.0,
            pcs_zero_power_threshold: float = 0.1,
            stop_flag: Optional[Callable[[], bool]] = None,
    ) -> None:
        self.bms_client = bms_client
        self.pcs_client = pcs_client
        self.log_callback = log_callback
        self.step_timeout = step_timeout
        self.poll_interval = poll_interval
        self.pcs_zero_power_threshold = pcs_zero_power_threshold
        self.stop_flag = stop_flag
        # When True, HV ON/OFF skips all PCS-side prechecks/actions and only executes BMS 0381 workflow.
        # This is useful for commissioning when the operator has manually confirmed PCS conditions.
        self.ignore_pcs_checks = False

    def log(self, message: str) -> None:
        if self.log_callback:
            self.log_callback(message)

    def should_stop(self) -> bool:
        return bool(self.stop_flag and self.stop_flag())

    def _wait_until(
        self,
        description: str,
        condition_func: Callable[[], bool],
        timeout: Optional[float] = None,
    ) -> bool:
        timeout = timeout if timeout is not None else self.step_timeout
        start = time.time()

        self.log(f"[HV] Waiting: {description}")

        while time.time() - start < timeout:
            if self.should_stop():
                self.log(f"[HV] CANCELLED: {description}")
                return False

            if condition_func():
                self.log(f"[HV] OK: {description}")
                return True

            time.sleep(self.poll_interval)

        self.log(f"[HV] TIMEOUT: {description}")
        return False

    def hv_on(self) -> bool:
        self.log("[HV] ===== HV ON workflow start =====")

        if self.should_stop():
            self.log("[HV] CANCELLED before start")
            return False

        if not self.bms_client.connect():
            self.log("[HV] FAIL: BMS connect failed")
            return False

        try:
            bms_status = self.bms_client.read_bms_status()
            self.log(f"[HV] Read 0302 (BMS status) = {bms_status}")
            if bms_status != 1:
                self.log("[HV] FAIL: 0302 != 1, HV ON condition not met")
                return False

            if self.ignore_pcs_checks:
                self.log("[HV] WARNING: PCS precheck and DC breaker open check ignored by operator")
            else:
                try:
                    if not self.pcs_client.connect():
                        self.log("[HV] FAIL: PCS connect failed")
                        return False
                except Exception as exc:
                    self.log(f"[HV] FAIL: PCS connect failed - {exc}")
                    return False
                precheck_errors = self.pcs_client.precheck_control_ready(action="hv_on")
                if precheck_errors:
                    self.log("[HV] FAIL: PCS precheck for HV ON failed")
                    for err in precheck_errors:
                        self.log(f"[HV] PCS precheck: {err}")
                    return False

                try:
                    breaker_open = self.pcs_client.is_dc_breaker_open()
                    self.log(f"[HV] PCS dc breaker open = {breaker_open}")
                except Exception as exc:
                    self.log(f"[HV] FAIL: PCS breaker check failed - {exc}")
                    return False
                finally:
                    try:
                        self.pcs_client.close()
                    except Exception:
                        pass

                if not breaker_open:
                    self.log("[HV] FAIL: PCS dc breaker is not open")
                    return False

            if self.should_stop():
                self.log("[HV] CANCELLED before write 0381=2")
                return False

            self.log("[HV] Write 0381 = 2 (Power On)")
            if not self.bms_client.write_ems_cmd_power_on():
                self.log("[HV] FAIL: write 0381=2 failed")
                return False

            ok = self._wait_until(
                "0301 == 1 (BMS power on ready)",
                lambda: self.bms_client.read_bms_power_on() == 1,
            )
            if not ok:
                self.log("[HV] FAIL: BMS power on ready timeout/cancelled")
                return False

            if self.should_stop():
                self.log("[HV] CANCELLED before PCS HV ON")
                return False

            if self.ignore_pcs_checks:
                self.log("[HV] WARNING: PCS HV ON and DC breaker close wait ignored by operator")
            else:
                try:
                    if not self.pcs_client.connect():
                        self.log("[HV] FAIL: PCS connect failed before HV ON")
                        return False
                except Exception as exc:
                    self.log(f"[HV] FAIL: PCS connect failed before HV ON - {exc}")
                    return False

                try:
                    self.log("[HV] Call PCS HV ON")
                    pcs_ok = self.pcs_client.hv_on()

                    if not pcs_ok:
                        self.log("[HV] FAIL: PCS HV ON returned False")
                        return False

                    self.log("[HV] Waiting PCS DC breaker closed")

                    ok = self._wait_until(
                        "PCS DC breaker closed",
                        lambda: self.pcs_client.is_dc_breaker_closed(),
                        timeout=self.step_timeout,
                    )

                    if not ok:
                        self.log("[HV] FAIL: PCS DC breaker close timeout/cancelled")
                        return False

                except Exception as exc:
                    self.log(f"[HV] FAIL: PCS HV ON / breaker close failed - {exc}")
                    return False

                finally:
                    try:
                        self.pcs_client.close()
                    except Exception:
                        pass

            if self.should_stop():
                self.log("[HV] CANCELLED before write 0381=1")
                return False

            self.log("[HV] Write 0381 = 1 (Stay)")
            if not self.bms_client.write_ems_cmd_stay():
                self.log("[HV] FAIL: write 0381=1 failed after HV ON")
                return False

            self.log("[HV] SUCCESS: HV ON workflow done")
            return True

        finally:
            self.bms_client.close()

    def hv_off(self) -> bool:
        self.log("[HV] ===== HV OFF workflow start =====")

        if self.should_stop():
            self.log("[HV] CANCELLED before start")
            return False

        if not self.bms_client.connect():
            self.log("[HV] FAIL: BMS connect failed")
            return False

        try:
            if self.ignore_pcs_checks:
                self.log("[HV] WARNING: PCS precheck/stop/breaker checks ignored by operator")
            else:
                try:
                    if not self.pcs_client.connect():
                        self.log("[HV] FAIL: PCS connect failed")
                        return False
                except Exception as exc:
                    self.log(f"[HV] FAIL: PCS connect failed - {exc}")
                    return False

                precheck_errors = self.pcs_client.precheck_control_ready(action="hv_off")
                if precheck_errors:
                    self.log("[HV] FAIL: PCS precheck for HV OFF failed")
                    for err in precheck_errors:
                        self.log(f"[HV] PCS precheck: {err}")
                    return False

                try:
                    active_power = self.pcs_client.get_active_power()
                    self.log(f"[HV] PCS active power before stop = {active_power}")

                    if abs(active_power) > self.pcs_zero_power_threshold:
                        self.log("[HV] PCS power is not zero, sending PCS Stop")
                        if not self.pcs_client.stop():
                            self.log("[HV] FAIL: PCS Stop command failed")
                            return False

                        self.log("[HV] Waiting PCS active power to zero")

                        ok = self._wait_until(
                            "PCS active power <= zero threshold",
                            lambda: abs(self.pcs_client.get_active_power()) <= self.pcs_zero_power_threshold,
                            timeout=self.step_timeout,
                        )

                        if not ok:
                            self.log("[HV] FAIL: PCS active power zero timeout")
                            return False

                    else:
                        self.log("[HV] PCS active power already zero")

                except Exception as exc:
                    self.log(f"[HV] FAIL: PCS active power/stop check failed - {exc}")
                    return False

                finally:
                    try:
                        self.pcs_client.close()
                    except Exception:
                        pass

            if self.should_stop():
                self.log("[HV] CANCELLED before write 0381=3")
                return False

            self.log("[HV] Write 0381 = 3 (Power Off)")
            if not self.bms_client.write_ems_cmd_power_off():
                self.log("[HV] FAIL: write 0381=3 failed")
                return False

            ok = self._wait_until(
                "0301 == 0 (BMS power on cleared)",
                lambda: self.bms_client.read_bms_power_on() == 0,
            )
            if not ok:
                self.log("[HV] FAIL: BMS power off timeout/cancelled")
                return False

            if self.ignore_pcs_checks:
                self.log("[HV] WARNING: PCS DC breaker open wait ignored by operator")
            else:
                if self.should_stop():
                    self.log("[HV] CANCELLED before PCS breaker open check")
                    return False

                try:
                    if not self.pcs_client.connect():
                        self.log("[HV] FAIL: PCS connect failed before breaker open check")
                        return False
                except Exception as exc:
                    self.log(f"[HV] FAIL: PCS connect failed before breaker open check - {exc}")
                    return False

                try:
                    self.log("[HV] Waiting PCS DC breaker open")

                    ok = self._wait_until(
                        "PCS DC breaker open",
                        lambda: self.pcs_client.is_dc_breaker_open(),
                        timeout=self.step_timeout,
                    )

                    if not ok:
                        self.log("[HV] FAIL: PCS DC breaker open timeout/cancelled")
                        return False

                except Exception as exc:
                    self.log(f"[HV] FAIL: PCS breaker open check failed - {exc}")
                    return False

                finally:
                    try:
                        self.pcs_client.close()
                    except Exception:
                        pass

            if self.should_stop():
                self.log("[HV] CANCELLED before write 0381=1")
                return False

            self.log("[HV] Write 0381 = 1 (Stay)")
            if not self.bms_client.write_ems_cmd_stay():
                self.log("[HV] FAIL: write 0381=1 failed after HV OFF")
                return False

            self.log("[HV] SUCCESS: HV OFF workflow done")
            return True

        finally:
            self.bms_client.close()


class HvWorkflowWorker(threading.Thread):
    """
    后台线程执行 HV workflow，避免阻塞 UI
    """

    def __init__(
        self,
        mode: str,
        controller: HvWorkflowController,
        device_name: str,
        log_callback: Optional[Callable[[str, str], None]] = None,
        finished_callback: Optional[Callable[[str, str, bool], None]] = None,
    ) -> None:
        super().__init__(daemon=True)
        self.mode = mode  # "on" or "off"
        self.controller = controller
        self.device_name = device_name
        self.log_callback = log_callback
        self.finished_callback = finished_callback
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True

    def should_stop(self) -> bool:
        return self._stop_requested

    def _log(self, message: str) -> None:
        if self.log_callback:
            self.log_callback(self.device_name, message)

    def run(self) -> None:
        self.controller.stop_flag = self.should_stop
        self.controller.log_callback = lambda msg: self._log(msg)

        success = False
        try:
            if self.mode == "on":
                success = self.controller.hv_on()
            elif self.mode == "off":
                success = self.controller.hv_off()
            else:
                self._log(f"[HV] FAIL: unknown workflow mode {self.mode}")
                success = False
        except Exception as exc:
            self._log(f"[HV] EXCEPTION: {exc}")
            success = False

        if self.finished_callback:
            self.finished_callback(self.device_name, self.mode, success)