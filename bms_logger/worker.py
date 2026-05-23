from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from queue import Queue, Empty
from typing import Any, Callable, Dict, Optional

from .data_model import normalize_telemetry_snapshot


@dataclass
class DeviceCommand:
    method_name: str
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    label: str = ""
    callback: Optional[Callable[[str, Any], None]] = None
    error_callback: Optional[Callable[[str, str], None]] = None


class DeviceWorker(threading.Thread):
    """
    单设备独立采集线程。

    v3.0 phase 5 additions:
    - initial_delay 支持错峰启动，避免所有设备同时连接/读取。
    - status_callback 输出任务状态，用于 Scheduler/Tasks 面板。
    """

    def __init__(
        self,
        device_name: str,
        client: Any,
        interval: float,
        callback: Callable[[str, Dict[str, Any]], None],
        error_callback: Optional[Callable[[str, str], None]] = None,
        status_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        initial_delay: float = 0.0,
    ) -> None:
        super().__init__(daemon=True)
        self.device_name = device_name
        self.client = client
        self.interval = interval
        self.callback = callback
        self.error_callback = error_callback
        self.status_callback = status_callback
        self.initial_delay = max(0.0, float(initial_delay))
        self.running = False
        self.commands: Queue[DeviceCommand] = Queue(maxsize=200)

    def _status(
        self,
        status: str,
        message: str = "-",
        latency_ms: float = 0.0,
        read_ok: bool = False,
        error: bool = False,
    ) -> None:
        if not self.status_callback:
            return
        try:
            self.status_callback(
                self.device_name,
                {
                    "status": status,
                    "last_message": message,
                    "last_latency_ms": latency_ms,
                    "read_ok": read_ok,
                    "error": error,
                },
            )
        except Exception:
            pass

    def stop(self) -> None:
        self.running = False

    def enqueue_command(
        self,
        method_name: str,
        *args: Any,
        label: str = "",
        callback: Optional[Callable[[str, Any], None]] = None,
        error_callback: Optional[Callable[[str, str], None]] = None,
        **kwargs: Any,
    ) -> bool:
        """Queue a BMS write/control command on the polling worker's own client.

        This serializes BMS polling, heartbeat, 0x038B, and simple manual BMS
        writes through one Modbus TCP connection per BMS. It avoids transaction-id
        mismatch / Broken pipe errors caused by several threads touching the same
        device at the same time.
        """
        if not self.running:
            return False
        try:
            self.commands.put_nowait(DeviceCommand(
                method_name=method_name,
                args=tuple(args),
                kwargs=dict(kwargs),
                label=label or method_name,
                callback=callback,
                error_callback=error_callback,
            ))
            return True
        except Exception:
            return False

    def _process_commands(self, limit: int = 5) -> None:
        for _ in range(max(1, int(limit))):
            try:
                command = self.commands.get_nowait()
            except Empty:
                return
            try:
                method = getattr(self.client, command.method_name, None)
                if method is None:
                    raise RuntimeError(f"command method missing: {command.method_name}")
                result = method(*command.args, **command.kwargs)
                if result is False:
                    raise RuntimeError(f"command returned false: {command.method_name}")
                if command.callback:
                    command.callback(self.device_name, result)
                self._status("Running", f"Command OK: {command.label}")
            except Exception as exc:
                message = f"Command failed: {command.label or command.method_name}: {exc}"
                self._status("Error", message, error=True)
                if command.error_callback:
                    command.error_callback(self.device_name, message)
                elif self.error_callback:
                    self.error_callback(self.device_name, message)

    def _sleep_interruptible(self, seconds: float) -> None:
        end = time.time() + max(0.0, seconds)
        while self.running and time.time() < end:
            time.sleep(min(0.2, max(0.0, end - time.time())))

    def _connect_with_backoff(self) -> bool:
        retry = 2.0
        while self.running:
            try:
                if self.client.connect():
                    self._status("Running", "Connected")
                    return True
                message = f"Connect failed; retry in {retry:.0f}s"
            except Exception as exc:
                message = f"Connect exception: {exc}; retry in {retry:.0f}s"

            self._status("RetryWait", message, error=True)
            if self.error_callback:
                try:
                    self.error_callback(self.device_name, message)
                except Exception:
                    pass
            try:
                self.client.close()
            except Exception:
                pass
            self._sleep_interruptible(retry)
            retry = min(retry * 2.0, 30.0)
        return False

    def run(self) -> None:
        self.running = True

        if self.initial_delay > 0:
            self._status("Scheduled", f"Initial delay {self.initial_delay:.1f}s")
            self._sleep_interruptible(self.initial_delay)

        if not self.running or not self._connect_with_backoff():
            return

        consecutive_failures = 0
        while self.running:
            start = time.time()

            try:
                self._process_commands(limit=5)

                raw_snapshot = self.client.read_telemetry_snapshot()
                if raw_snapshot is None:
                    consecutive_failures += 1
                    self._status("Timeout", f"Read telemetry failed ({consecutive_failures})", error=True)
                    if self.error_callback:
                        self.error_callback(self.device_name, "Read telemetry failed")
                    if consecutive_failures >= 3:
                        try:
                            self.client.close()
                        except Exception:
                            pass
                        if not self._connect_with_backoff():
                            break
                        consecutive_failures = 0
                else:
                    consecutive_failures = 0
                    point_catalog = {}
                    try:
                        getter = getattr(self.client, "get_point_catalog", None)
                        if callable(getter):
                            point_catalog = getter()
                    except Exception:
                        point_catalog = {}

                    driver_key = getattr(self.client, "driver_key", self.client.__class__.__name__)
                    snapshot = normalize_telemetry_snapshot(
                        raw_snapshot,
                        device_name=self.device_name,
                        driver_key=str(driver_key),
                        device_type="BMS",
                        point_catalog=point_catalog,
                    )
                    if snapshot is None:
                        self._status("Error", "Normalize telemetry failed", error=True)
                        if self.error_callback:
                            self.error_callback(self.device_name, "Normalize telemetry failed")
                    else:
                        latency_ms = (time.time() - start) * 1000.0
                        self._status("Running", "Read OK", latency_ms=latency_ms, read_ok=True)
                        self.callback(self.device_name, snapshot)

            except Exception as exc:
                consecutive_failures += 1
                self._status("Error", f"Read exception: {exc}", error=True)
                if self.error_callback:
                    self.error_callback(self.device_name, f"Read exception: {exc}")
                if consecutive_failures >= 3:
                    try:
                        self.client.close()
                    except Exception:
                        pass
                    if not self._connect_with_backoff():
                        break
                    consecutive_failures = 0

            elapsed = time.time() - start
            sleep_time = max(0.0, self.interval - elapsed)
            self._sleep_interruptible(sleep_time)

        self._status("Stopped", "Worker stopped")
        try:
            self.client.close()
        except Exception:
            pass


class HeartbeatWorker(threading.Thread):
    """
    每台设备一个心跳线程：
    - 每秒写一次
    - 数值从 0 到 255
    - 到 255 后回到 0
    """

    def __init__(
        self,
        device_name: str,
        client: Any,
        callback: Optional[Callable[[str, int], None]] = None,
        error_callback: Optional[Callable[[str, str], None]] = None,
        interval: float = 1.0,
    ) -> None:
        super().__init__(daemon=True)
        self.device_name = device_name
        self.client = client
        self.callback = callback
        self.error_callback = error_callback
        self.interval = interval
        self.running = False
        self.value = 0

    def stop(self) -> None:
        self.running = False

    def enqueue_command(
        self,
        method_name: str,
        *args: Any,
        label: str = "",
        callback: Optional[Callable[[str, Any], None]] = None,
        error_callback: Optional[Callable[[str, str], None]] = None,
        **kwargs: Any,
    ) -> bool:
        """Queue a BMS write/control command on the polling worker's own client.

        This serializes BMS polling, heartbeat, 0x038B, and simple manual BMS
        writes through one Modbus TCP connection per BMS. It avoids transaction-id
        mismatch / Broken pipe errors caused by several threads touching the same
        device at the same time.
        """
        if not self.running:
            return False
        try:
            self.commands.put_nowait(DeviceCommand(
                method_name=method_name,
                args=tuple(args),
                kwargs=dict(kwargs),
                label=label or method_name,
                callback=callback,
                error_callback=error_callback,
            ))
            return True
        except Exception:
            return False

    def _process_commands(self, limit: int = 5) -> None:
        for _ in range(max(1, int(limit))):
            try:
                command = self.commands.get_nowait()
            except Empty:
                return
            try:
                method = getattr(self.client, command.method_name, None)
                if method is None:
                    raise RuntimeError(f"command method missing: {command.method_name}")
                result = method(*command.args, **command.kwargs)
                if result is False:
                    raise RuntimeError(f"command returned false: {command.method_name}")
                if command.callback:
                    command.callback(self.device_name, result)
                self._status("Running", f"Command OK: {command.label}")
            except Exception as exc:
                message = f"Command failed: {command.label or command.method_name}: {exc}"
                self._status("Error", message, error=True)
                if command.error_callback:
                    command.error_callback(self.device_name, message)
                elif self.error_callback:
                    self.error_callback(self.device_name, message)

    def run(self) -> None:
        self.running = True

        try:
            if not self.client.connect():
                if self.error_callback:
                    try:
                        self.error_callback(self.device_name, "Heartbeat connect failed")
                    except Exception:
                        pass
                return
        except Exception as exc:
            if self.error_callback:
                try:
                    self.error_callback(self.device_name, f"Heartbeat connect exception: {exc}")
                except Exception:
                    pass
            return

        while self.running:
            start = time.time()

            try:
                self._process_commands(limit=5)

                ok = self.client.write_heartbeat(self.value)
                if ok:
                    if self.callback:
                        try:
                            self.callback(self.device_name, self.value)
                        except Exception:
                            pass
                    self.value = (self.value + 1) % 256
                else:
                    if self.error_callback:
                        try:
                            self.error_callback(self.device_name, "Heartbeat write failed")
                        except Exception:
                            pass
            except Exception as exc:
                if self.error_callback:
                    try:
                        self.error_callback(self.device_name, f"Heartbeat exception: {exc}")
                    except Exception:
                        pass
                # Do not keep writing to a broken/stale socket. Close and reconnect
                # with a short backoff so BrokenPipe/transaction errors do not loop
                # forever on the same client instance.
                try:
                    self.client.close()
                except Exception:
                    pass
                time.sleep(min(2.0, max(0.2, self.interval)))
                if not self.running:
                    break
                try:
                    if not self.client.connect() and self.error_callback:
                        self.error_callback(self.device_name, "Heartbeat reconnect failed")
                except Exception as reconnect_exc:
                    if self.error_callback:
                        try:
                            self.error_callback(self.device_name, f"Heartbeat reconnect exception: {reconnect_exc}")
                        except Exception:
                            pass

            elapsed = time.time() - start
            sleep_time = max(0.0, self.interval - elapsed)
            time.sleep(sleep_time)

        try:
            self.client.close()
        except Exception:
            pass


class PcsPollingWorker(threading.Thread):
    """Poll one PCS device periodically and return a normalized lightweight snapshot.

    This mirrors DeviceWorker for BMS, but is profile-driven and reads a selected
    list of PCS points. It is intentionally tolerant: a single bad point is
    returned as an error in point_errors instead of killing the whole cycle.
    """

    def __init__(
        self,
        pcs_name: str,
        client: Any,
        interval: float,
        point_names: list[str],
        callback: Callable[[str, Dict[str, Any]], None],
        error_callback: Optional[Callable[[str, str], None]] = None,
        status_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        initial_delay: float = 0.0,
    ) -> None:
        super().__init__(daemon=True)
        self.pcs_name = pcs_name
        self.client = client
        self.interval = max(0.2, float(interval))
        self.point_names = list(point_names)
        self.callback = callback
        self.error_callback = error_callback
        self.status_callback = status_callback
        self.initial_delay = max(0.0, float(initial_delay))
        self.running = False
        self.commands: Queue[DeviceCommand] = Queue(maxsize=200)

    def stop(self) -> None:
        self.running = False

    def enqueue_command(
        self,
        method_name: str,
        *args: Any,
        label: str = "",
        callback: Optional[Callable[[str, Any], None]] = None,
        error_callback: Optional[Callable[[str, str], None]] = None,
        **kwargs: Any,
    ) -> bool:
        """Queue a BMS write/control command on the polling worker's own client.

        This serializes BMS polling, heartbeat, 0x038B, and simple manual BMS
        writes through one Modbus TCP connection per BMS. It avoids transaction-id
        mismatch / Broken pipe errors caused by several threads touching the same
        device at the same time.
        """
        if not self.running:
            return False
        try:
            self.commands.put_nowait(DeviceCommand(
                method_name=method_name,
                args=tuple(args),
                kwargs=dict(kwargs),
                label=label or method_name,
                callback=callback,
                error_callback=error_callback,
            ))
            return True
        except Exception:
            return False

    def _process_commands(self, limit: int = 5) -> None:
        for _ in range(max(1, int(limit))):
            try:
                command = self.commands.get_nowait()
            except Empty:
                return
            try:
                method = getattr(self.client, command.method_name, None)
                if method is None:
                    raise RuntimeError(f"command method missing: {command.method_name}")
                result = method(*command.args, **command.kwargs)
                if result is False:
                    raise RuntimeError(f"command returned false: {command.method_name}")
                if command.callback:
                    command.callback(self.device_name, result)
                self._status("Running", f"Command OK: {command.label}")
            except Exception as exc:
                message = f"Command failed: {command.label or command.method_name}: {exc}"
                self._status("Error", message, error=True)
                if command.error_callback:
                    command.error_callback(self.device_name, message)
                elif self.error_callback:
                    self.error_callback(self.device_name, message)

    def _status(self, status: str, message: str = "-", latency_ms: float = 0.0, read_ok: bool = False, error: bool = False) -> None:
        if not self.status_callback:
            return
        try:
            self.status_callback(
                self.pcs_name,
                {
                    "status": status,
                    "last_message": message,
                    "last_latency_ms": latency_ms,
                    "read_ok": read_ok,
                    "error": error,
                    "device_type": "PCS",
                },
            )
        except Exception:
            pass

    def run(self) -> None:
        self.running = True
        if self.initial_delay > 0:
            self._status("Scheduled", f"Initial delay {self.initial_delay:.1f}s")
            time.sleep(self.initial_delay)

        try:
            if not self.client.connect():
                self._status("Error", "PCS connect failed", error=True)
                if self.error_callback:
                    self.error_callback(self.pcs_name, "PCS connect failed")
                return
        except Exception as exc:
            self._status("Error", f"PCS connect exception: {exc}", error=True)
            if self.error_callback:
                self.error_callback(self.pcs_name, f"PCS connect exception: {exc}")
            return

        self._status("Running", "PCS connected")

        while self.running:
            start = time.time()
            snapshot: Dict[str, Any] = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "device_type": "PCS",
                "driver_key": getattr(self.client, "config", {}).get("driver", "generic_modbus_pcs") if hasattr(self.client, "config") else "generic_modbus_pcs",
                "points": {},
                "raw": {},
                "point_errors": {},
            }
            try:
                for point_name in self.point_names:
                    try:
                        raw = self.client.read_raw(point_name)
                        try:
                            value = self.client.read_value(point_name)
                        except Exception:
                            value = raw
                        snapshot["raw"][point_name] = raw
                        snapshot["points"][point_name] = value
                        # Promote common points for CSV/quick display convenience.
                        snapshot[point_name] = value
                    except Exception as exc:
                        snapshot["point_errors"][point_name] = str(exc)

                latency_ms = (time.time() - start) * 1000.0
                self._status("Running", "PCS read OK", latency_ms=latency_ms, read_ok=True)
                self.callback(self.pcs_name, snapshot)
            except Exception as exc:
                self._status("Error", f"PCS read exception: {exc}", error=True)
                if self.error_callback:
                    self.error_callback(self.pcs_name, f"PCS read exception: {exc}")

            elapsed = time.time() - start
            time.sleep(max(0.0, self.interval - elapsed))

        self._status("Stopped", "PCS worker stopped")
        try:
            self.client.close()
        except Exception:
            pass
