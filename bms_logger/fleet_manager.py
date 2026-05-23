from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from queue import Queue, Empty
from typing import Any, Callable, Dict, Optional


LogFn = Callable[[str], None]
ClientFactory = Callable[[str], Any]


@dataclass
class FleetDeviceState:
    name: str
    device_type: str
    online: bool = False
    running: bool = False
    heartbeat_value: int = 0
    last_ok_ts: float = 0.0
    last_error_ts: float = 0.0
    last_error: str = ""
    retry_interval_s: float = 2.0
    command_count: int = 0
    error_count: int = 0


@dataclass
class FleetCommand:
    method_name: str
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    label: str = ""


@dataclass
class PeriodicCommand:
    key: str
    method_name: str
    interval_s: float
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    label: str = ""
    next_due_ts: float = 0.0


class FleetDeviceWorker(threading.Thread):
    """Persistent per-device Modbus worker for fleet heartbeat and queued commands.

    It keeps one client instance per device, writes heartbeat on schedule, and executes
    commands from a small queue. Failed/offline devices enter exponential backoff so one
    bad IP cannot freeze the GUI or create a reconnect storm.
    """

    def __init__(
        self,
        *,
        name: str,
        device_type: str,
        client_factory: ClientFactory,
        heartbeat_method: str = "",
        heartbeat_modulo: int = 256,
        interval_s: float = 1.0,
        heartbeat_enabled: bool = True,
        max_retry_s: float = 30.0,
        log: Optional[LogFn] = None,
        status_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        initial_delay_s: float = 0.0,
        command_queue_size: int = 200,
    ) -> None:
        super().__init__(daemon=True)
        self.name = name
        self.device_type = device_type
        self.client_factory = client_factory
        self.heartbeat_method = heartbeat_method
        self.heartbeat_enabled = bool(heartbeat_enabled) and bool(heartbeat_method)
        self.heartbeat_modulo = max(2, int(heartbeat_modulo))
        self.interval_s = max(0.2, float(interval_s))
        self.max_retry_s = max(2.0, float(max_retry_s))
        self.log = log or (lambda _msg: None)
        self.status_callback = status_callback
        self.initial_delay_s = max(0.0, float(initial_delay_s))
        self.commands: Queue[FleetCommand] = Queue(maxsize=max(1, int(command_queue_size)))
        self.state = FleetDeviceState(name=name, device_type=device_type)
        self._stop_event = threading.Event()
        self._client: Any = None
        self._next_heartbeat_ts = 0.0
        self._next_connect_ts = 0.0
        self._periodic_commands: Dict[str, PeriodicCommand] = {}
        self._periodic_lock = threading.RLock()

    def stop(self) -> None:
        self._stop_event.set()

    def enqueue(self, command: FleetCommand) -> bool:
        if self._stop_event.is_set():
            return False
        try:
            self.commands.put_nowait(command)
            return True
        except Exception:
            return False

    def set_periodic_command(self, command: PeriodicCommand) -> None:
        command.interval_s = max(10.0, float(command.interval_s))
        if command.next_due_ts <= 0:
            # Run once shortly after enabling, then follow the configured minute-level interval.
            command.next_due_ts = time.monotonic() + min(5.0, command.interval_s)
        with self._periodic_lock:
            self._periodic_commands[command.key] = command

    def clear_periodic_command(self, key: str) -> None:
        with self._periodic_lock:
            self._periodic_commands.pop(key, None)

    def periodic_keys(self) -> list[str]:
        with self._periodic_lock:
            return list(self._periodic_commands.keys())

    def snapshot(self) -> Dict[str, Any]:
        return {
            "name": self.state.name,
            "device_type": self.state.device_type,
            "online": self.state.online,
            "running": self.state.running,
            "heartbeat_value": self.state.heartbeat_value,
            "last_ok_ts": self.state.last_ok_ts,
            "last_error_ts": self.state.last_error_ts,
            "last_error": self.state.last_error,
            "retry_interval_s": self.state.retry_interval_s,
            "command_count": self.state.command_count,
            "error_count": self.state.error_count,
            "queued_commands": self.commands.qsize(),
            "periodic_commands": self.periodic_keys(),
        }

    def _emit_status(self, status: str, message: str = "", error: bool = False) -> None:
        if not self.status_callback:
            return
        try:
            self.status_callback(self.name, {
                "status": status,
                "last_message": message or status,
                "error": error,
                "device_type": self.device_type,
                "fleet": True,
            })
        except Exception:
            pass

    def _close_client(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
        self._client = None
        self.state.online = False

    def _connect_if_needed(self) -> bool:
        if self._client is not None and self.state.online:
            return True
        now = time.monotonic()
        if now < self._next_connect_ts:
            return False
        try:
            self._client = self.client_factory(self.name)
            ok = bool(self._client.connect())
            if not ok:
                raise RuntimeError("connect returned false")
            self.state.online = True
            self.state.retry_interval_s = 2.0
            self._emit_status("FleetOnline", "Connected")
            self.log(f"[FLEET][{self.device_type}] {self.name}: connected")
            return True
        except Exception as exc:
            self._close_client()
            self._mark_error(f"connect failed: {exc}")
            self._next_connect_ts = now + self.state.retry_interval_s
            self.state.retry_interval_s = min(self.state.retry_interval_s * 2.0, self.max_retry_s)
            return False

    def _mark_error(self, message: str) -> None:
        now = time.time()
        self.state.last_error_ts = now
        self.state.last_error = message
        self.state.error_count += 1
        self._emit_status("FleetRetryWait", message, error=True)
        # Log only occasionally to avoid flooding QTextEdit when 72 devices are offline.
        if self.state.error_count <= 3 or self.state.error_count % 10 == 0:
            self.log(f"[FLEET][{self.device_type}] {self.name}: {message}; retry={self.state.retry_interval_s:.0f}s")

    def _write_heartbeat(self) -> None:
        if not self.heartbeat_enabled:
            return
        if self._client is None:
            return
        method = getattr(self._client, self.heartbeat_method, None)
        if method is None:
            raise RuntimeError(f"heartbeat method missing: {self.heartbeat_method}")
        value = int(self.state.heartbeat_value)
        ok = bool(method(value))
        if not ok:
            raise RuntimeError("heartbeat write returned false")
        self.state.last_ok_ts = time.time()
        self.state.heartbeat_value = (value + 1) % self.heartbeat_modulo

    def _execute_command(self, command: FleetCommand) -> None:
        if self._client is None:
            return
        method = getattr(self._client, command.method_name, None)
        if method is None:
            raise RuntimeError(f"command method missing: {command.method_name}")
        ok = bool(method(*command.args, **command.kwargs))
        if not ok:
            raise RuntimeError(f"command returned false: {command.method_name}")
        self.state.command_count += 1
        self.state.last_ok_ts = time.time()

    def _execute_due_periodic_commands(self, now: float) -> None:
        with self._periodic_lock:
            due = [cmd for cmd in self._periodic_commands.values() if now >= cmd.next_due_ts]
        for cmd in due:
            self._execute_command(FleetCommand(
                method_name=cmd.method_name,
                args=cmd.args,
                kwargs=cmd.kwargs,
                label=cmd.label or cmd.method_name,
            ))
            cmd.next_due_ts = now + max(10.0, float(cmd.interval_s))
            if cmd.label:
                self.log(f"[FLEET][{self.device_type}] {self.name}: periodic {cmd.label} OK")

    def run(self) -> None:
        self.state.running = True
        self._emit_status("FleetScheduled", f"Initial delay {self.initial_delay_s:.1f}s")
        if self.initial_delay_s:
            self._stop_event.wait(self.initial_delay_s)
        self._next_heartbeat_ts = time.monotonic()

        while not self._stop_event.is_set():
            now = time.monotonic()
            connected = self._connect_if_needed()
            if not connected:
                self._stop_event.wait(0.2)
                continue

            try:
                # Process a few queued commands each loop, then heartbeat. This keeps
                # emergency stop / power changes responsive without starving heartbeat.
                for _ in range(5):
                    try:
                        cmd = self.commands.get_nowait()
                    except Empty:
                        break
                    self._execute_command(cmd)
                    if cmd.label:
                        self.log(f"[FLEET][{self.device_type}] {self.name}: {cmd.label} OK")

                self._execute_due_periodic_commands(now)

                if self.heartbeat_enabled and now >= self._next_heartbeat_ts:
                    self._write_heartbeat()
                    self._next_heartbeat_ts = now + self.interval_s
                    self._emit_status("FleetRunning", f"HB={self.state.heartbeat_value}")
                elif not self.heartbeat_enabled:
                    self._emit_status("FleetCommandReady", "command worker online")

            except Exception as exc:
                self._mark_error(str(exc))
                self._close_client()
                self._next_connect_ts = time.monotonic() + self.state.retry_interval_s
                self.state.retry_interval_s = min(self.state.retry_interval_s * 2.0, self.max_retry_s)

            self._stop_event.wait(0.05)

        self.state.running = False
        self._close_client()
        self._emit_status("FleetStopped", "Stopped")


class FleetManager:
    """Manages 24 BMS + 48 PCS scale heartbeats and broadcast PCS commands."""

    def __init__(self, log: Optional[LogFn] = None, status_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None) -> None:
        self.log = log or (lambda _msg: None)
        self.status_callback = status_callback
        self.workers: Dict[str, FleetDeviceWorker] = {}
        self._lock = threading.RLock()

    def start_bms_heartbeats(self, names: list[str], factory: ClientFactory, interval_s: float = 1.0) -> int:
        started = 0
        with self._lock:
            for index, name in enumerate(names):
                key = f"BMS:{name}"
                if key in self.workers:
                    continue
                worker = FleetDeviceWorker(
                    name=name,
                    device_type="BMS",
                    client_factory=factory,
                    heartbeat_method="write_heartbeat",
                    heartbeat_modulo=256,
                    interval_s=interval_s,
                    heartbeat_enabled=True,
                    log=self.log,
                    status_callback=self.status_callback,
                    initial_delay_s=index * 0.05,
                )
                self.workers[key] = worker
                worker.start()
                started += 1
        return started

    def start_bms_command_workers(self, names: list[str], factory: ClientFactory, interval_s: float = 1.0) -> int:
        started = 0
        with self._lock:
            for index, name in enumerate(names):
                key = f"BMS:{name}"
                if key in self.workers:
                    continue
                worker = FleetDeviceWorker(
                    name=name,
                    device_type="BMS",
                    client_factory=factory,
                    heartbeat_method="",
                    heartbeat_modulo=256,
                    interval_s=interval_s,
                    heartbeat_enabled=False,
                    log=self.log,
                    status_callback=self.status_callback,
                    initial_delay_s=index * 0.05,
                )
                self.workers[key] = worker
                worker.start()
                started += 1
        return started

    def start_pcs_heartbeats(self, names: list[str], factory: ClientFactory, interval_s: float = 1.0, heartbeat_enabled: bool = False) -> int:
        """Start persistent PCS workers.

        In v3.18 site testing PCS heartbeat is disabled by default because the
        heartbeat point/function-code is still under verification. The worker is
        still useful as a per-PCS serial command queue for active/reactive power,
        start/stop, and strategy dispatch. Pass heartbeat_enabled=True only after
        the PCS heartbeat point has been validated on site.
        """
        started = 0
        with self._lock:
            for index, name in enumerate(names):
                key = f"PCS:{name}"
                if key in self.workers:
                    continue
                worker = FleetDeviceWorker(
                    name=name,
                    device_type="PCS",
                    client_factory=factory,
                    heartbeat_method="send_heartbeat",
                    heartbeat_modulo=65536,
                    interval_s=interval_s,
                    heartbeat_enabled=heartbeat_enabled,
                    log=self.log,
                    status_callback=self.status_callback,
                    initial_delay_s=index * 0.05,
                )
                self.workers[key] = worker
                worker.start()
                started += 1
        return started

    def start_pcs_command_workers(self, names: list[str], factory: ClientFactory, interval_s: float = 1.0) -> int:
        """Start PCS workers for queued commands only; no PCS heartbeat writes."""
        return self.start_pcs_heartbeats(names, factory, interval_s=interval_s, heartbeat_enabled=False)

    def stop(self, device_type: str | None = None) -> int:
        with self._lock:
            keys = [k for k, w in self.workers.items() if device_type is None or w.device_type == device_type]
            workers = [self.workers.pop(k) for k in keys]
        for worker in workers:
            worker.stop()
        for worker in workers:
            worker.join(timeout=2.0)
        return len(workers)

    def enqueue_pcs_command(self, pcs_names: list[str], method_name: str, *args: Any, label: str = "", **kwargs: Any) -> int:
        count = 0
        cmd = FleetCommand(method_name=method_name, args=args, kwargs=kwargs, label=label or method_name)
        with self._lock:
            for name in pcs_names:
                worker = self.workers.get(f"PCS:{name}")
                if worker and worker.enqueue(cmd):
                    count += 1
        return count

    def enable_bms_insulation_disable(self, names: list[str], factory: ClientFactory, interval_minutes: float) -> int:
        # Reuse/create BMS fleet workers without enabling heartbeat. This keeps 0x038B
        # on a single per-device queue and avoids adding another periodic heartbeat
        # writer that can disturb normal BMS polling.
        self.start_bms_command_workers(names, factory, interval_s=1.0)
        interval_s = max(1.0, float(interval_minutes)) * 60.0
        count = 0
        with self._lock:
            for name in names:
                worker = self.workers.get(f"BMS:{name}")
                if not worker:
                    continue
                worker.set_periodic_command(PeriodicCommand(
                    key="bms_insulation_disable_038b",
                    method_name="write_insulation_monitor_disable",
                    interval_s=interval_s,
                    label="write 0x038B=2 insulation monitor disable",
                ))
                count += 1
        return count

    def disable_bms_insulation_disable(self, names: list[str] | None = None) -> int:
        count = 0
        with self._lock:
            for key, worker in self.workers.items():
                if not key.startswith("BMS:"):
                    continue
                name = key.split(":", 1)[1]
                if names is not None and name not in names:
                    continue
                worker.clear_periodic_command("bms_insulation_disable_038b")
                count += 1
        return count

    def snapshots(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            items = list(self.workers.items())
        return {key: worker.snapshot() for key, worker in items}
