from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox

from ..hv_controller import HvWorkflowController, HvWorkflowWorker
from ..modbus_client import BmsModbusClient
from ..pcs_client import PcsClient
from ..client_factory import create_bms_client, create_pcs_client
from ..worker import HeartbeatWorker


class BmsControlMixin:
    def _get_bms_polling_worker(self, device_name: str):
        worker = getattr(self, "device_workers", {}).get(device_name)
        if worker is not None and getattr(worker, "running", False) and hasattr(worker, "enqueue_command"):
            return worker
        return None

    def _ensure_bms_timer_store(self) -> None:
        if not hasattr(self, "bms_queue_heartbeat_timers"):
            self.bms_queue_heartbeat_timers = {}
        if not hasattr(self, "bms_queue_heartbeat_values"):
            self.bms_queue_heartbeat_values = {}
        if not hasattr(self, "bms_038b_timer"):
            self.bms_038b_timer = None

    def _enqueue_bms_worker_command(self, device_name: str, method_name: str, *args, label: str = "") -> bool:
        worker = self._get_bms_polling_worker(device_name)
        if worker is None:
            return False
        return bool(worker.enqueue_command(
            method_name,
            *args,
            label=label or method_name,
            callback=lambda name, _result: self.control_log(f"[BMS][QUEUE] {name}: {label or method_name} OK"),
            error_callback=lambda name, error: self.bridge.heartbeat_error.emit(name, error),
        ))

    def _start_bms_queue_heartbeat(self, device_name: str) -> bool:
        self._ensure_bms_timer_store()
        worker = self._get_bms_polling_worker(device_name)
        if worker is None:
            return False
        if device_name in self.bms_queue_heartbeat_timers:
            return True
        self.bms_queue_heartbeat_values.setdefault(device_name, 0)
        timer = QTimer(self)
        timer.setInterval(max(200, int(float(getattr(self, "heartbeat_interval", 1.0)) * 1000)))

        def tick(name=device_name):
            value = int(self.bms_queue_heartbeat_values.get(name, 0)) % 256
            ok = self._enqueue_bms_worker_command(name, "write_heartbeat", value, label=f"heartbeat={value}")
            if ok:
                self.bridge.heartbeat_written.emit(name, value)
                self.bms_queue_heartbeat_values[name] = (value + 1) % 256
            else:
                self.bridge.heartbeat_error.emit(name, "BMS polling worker not running; heartbeat not queued")

        timer.timeout.connect(tick)
        self.bms_queue_heartbeat_timers[device_name] = timer
        timer.start()
        tick()
        return True

    def _stop_bms_queue_heartbeat(self, device_name: str) -> bool:
        self._ensure_bms_timer_store()
        timer = self.bms_queue_heartbeat_timers.pop(device_name, None)
        if timer is None:
            return False
        timer.stop()
        timer.deleteLater()
        return True

    def handle_start_heartbeat(self) -> None:
        device_name = self._get_selected_control_device()
        if not device_name:
            return

        # Preferred path: if BMS monitoring is running, reuse the polling worker's
        # own Modbus client and queue heartbeat writes behind reads. This avoids
        # a second TCP connection to the same BMS.
        if self._start_bms_queue_heartbeat(device_name):
            self.heartbeat_state_label.setText("Queued on BMS worker")
            self.control_state_label.setText("Running")
            self.last_control_result_label.setText("Heartbeat queued on polling worker")
            self.control_log(f"[CONTROL] {device_name}: Heartbeat queued on BMS polling worker")
            return

        # Fallback for bench testing when monitoring is not running yet.
        if device_name in self.heartbeat_workers:
            self.control_log(f"[CONTROL] {device_name}: Heartbeat already running")
            self.heartbeat_state_label.setText("Running")
            return

        if self._enqueue_bms_worker_command(device_name, "write_ems_cmd", int(cmd_value), label=f"EMS cmd {cmd_value} ({cmd_name})"):
            self.control_state_label.setText("Queued")
            self.last_ems_cmd_result_label.setText("Queued on BMS worker")
            self.control_log(f"[CONTROL] {device_name}: EMS cmd {cmd_value} ({cmd_name}) queued on BMS polling worker")
            return

        client = self._build_bms_client_for_device(device_name)
        if client is None:
            return
        worker = HeartbeatWorker(
            device_name=device_name,
            client=client,
            callback=lambda name, value: self.bridge.heartbeat_written.emit(name, value),
            error_callback=lambda name, error: self.bridge.heartbeat_error.emit(name, error),
            interval=self.heartbeat_interval,
        )
        self.heartbeat_workers[device_name] = worker
        worker.start()
        self.heartbeat_state_label.setText("Starting")
        self.control_state_label.setText("Running")
        self.last_control_result_label.setText("Heartbeat started on separate connection")
        self.control_log(f"[CONTROL][WARN] {device_name}: Heartbeat started on separate connection because BMS polling worker is not running")

    def handle_stop_heartbeat(self) -> None:
        device_name = self._get_selected_control_device()
        if not device_name:
            return

        stopped_queue = self._stop_bms_queue_heartbeat(device_name)
        worker = self.heartbeat_workers.get(device_name)
        if worker:
            worker.stop()
            worker.join(timeout=3.0)
            self.heartbeat_workers.pop(device_name, None)

        if stopped_queue or worker:
            self.heartbeat_state_label.setText("Stopped")
            self.control_state_label.setText("Idle")
            self.last_control_result_label.setText("Heartbeat stopped")
            self.control_log(f"[CONTROL] {device_name}: Heartbeat stopped")
        else:
            self.heartbeat_state_label.setText("Stopped")
            self.control_state_label.setText("Idle")
            self.last_control_result_label.setText("Heartbeat not running")
            self.control_log(f"[CONTROL] {device_name}: Heartbeat not running")
        self.last_heartbeat_status = "Stopped"
        self.refresh_global_status_bar()

    def _write_ems_cmd(self, device_name: str, cmd_value: int, cmd_name: str, confirm: bool) -> None:
        if confirm:
            reply = QMessageBox.question(
                self,
                f"Confirm {cmd_name}",
                f"Write EMS cmd {cmd_value} ({cmd_name}) to {device_name}?",
            )
            if reply != QMessageBox.Yes:
                return

        client = self._build_bms_client_for_device(device_name)
        if client is None:
            return

        self.control_state_label.setText("Executing")
        self.last_control_result_label.setText(f"EMS cmd {cmd_value}")
        self.last_ems_cmd_result_label.setText("Running")
        self.control_log(f"[CONTROL] {device_name}: EMS cmd {cmd_value} ({cmd_name}) started")

        try:
            if not client.connect():
                self.control_state_label.setText("Failed")
                self.last_ems_cmd_result_label.setText("Connect failed")
                self.control_log(f"[CONTROL] {device_name}: EMS cmd {cmd_value} failed - connect failed")
                QMessageBox.critical(self, "Error", f"Connect failed: {device_name}")
                return

            ok = client.write_ems_cmd(cmd_value)
            if ok:
                self.control_state_label.setText("Done")
                self.last_ems_cmd_result_label.setText(f"Success ({cmd_name})")
                self.control_log(f"[CONTROL] {device_name}: EMS cmd {cmd_value} ({cmd_name}) success")
            else:
                self.control_state_label.setText("Failed")
                self.last_ems_cmd_result_label.setText("Write failed")
                self.control_log(f"[CONTROL] {device_name}: EMS cmd {cmd_value} ({cmd_name}) failed - write failed")
                QMessageBox.critical(self, "Error", f"EMS cmd write failed: {device_name}")

        except Exception as exc:
            self.control_state_label.setText("Failed")
            self.last_ems_cmd_result_label.setText(str(exc))
            self.control_log(f"[CONTROL] {device_name}: EMS cmd {cmd_value} exception - {exc}")
            QMessageBox.critical(self, "Error", f"EMS cmd exception:\n{exc}")

        finally:
            try:
                client.close()
            except Exception:
                pass

    def handle_ems_cmd_stay(self) -> None:
        device_name = self._get_selected_control_device()
        if device_name:
            self._write_ems_cmd(device_name, 1, "Stay", confirm=False)

    def handle_ems_cmd_power_on(self) -> None:
        device_name = self._get_selected_control_device()
        if device_name:
            self._write_ems_cmd(device_name, 2, "Power On", confirm=True)

    def handle_ems_cmd_power_off(self) -> None:
        device_name = self._get_selected_control_device()
        if device_name:
            self._write_ems_cmd(device_name, 3, "Power Off", confirm=True)

    def handle_clear_fault(self) -> None:
        device_name = self._get_selected_control_device()
        if not device_name:
            return

        reply = QMessageBox.question(
            self,
            "Confirm Clear Fault",
            f"Send clear fault command to {device_name}?",
        )
        if reply != QMessageBox.Yes:
            return

        client = self._build_bms_client_for_device(device_name)
        if client is None:
            return

        self.control_state_label.setText("Executing")
        self.last_control_result_label.setText("Running")
        self.control_log(f"[CONTROL] {device_name}: Clear Fault started")

        try:
            if not client.connect():
                self.control_state_label.setText("Failed")
                self.last_control_result_label.setText("Connect failed")
                self.control_log(f"[CONTROL] {device_name}: Clear Fault failed - connect failed")
                QMessageBox.critical(self, "Error", f"Connect failed: {device_name}")
                return

            ok = client.clear_fault()
            if ok:
                self.control_state_label.setText("Done")
                self.last_control_result_label.setText("Success")
                self.control_log(f"[CONTROL] {device_name}: Clear Fault success")
                QMessageBox.information(self, "Success", f"Clear Fault sent to {device_name}")
            else:
                self.control_state_label.setText("Failed")
                self.last_control_result_label.setText("Write failed")
                self.control_log(f"[CONTROL] {device_name}: Clear Fault failed - write failed")
                QMessageBox.critical(self, "Error", f"Clear Fault write failed: {device_name}")

        except Exception as exc:
            self.control_state_label.setText("Failed")
            self.last_control_result_label.setText(str(exc))
            self.control_log(f"[CONTROL] {device_name}: Clear Fault exception - {exc}")
            QMessageBox.critical(self, "Error", f"Clear Fault exception:\n{exc}")

        finally:
            try:
                client.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Fleet BMS heartbeat and 0x038B periodic insulation-monitor disable
    # ------------------------------------------------------------------
    def handle_start_all_bms_heartbeats(self) -> None:
        bms_names = self._fleet_bms_names() if hasattr(self, "_fleet_bms_names") else [str(d.get("name", "")).strip() for d in getattr(self, "devices", []) if str(d.get("name", "")).strip()]
        if not bms_names:
            QMessageBox.information(self, "BMS Heartbeat", "No BMS devices configured.")
            return

        queued = []
        missing = []
        for name in bms_names:
            if self._start_bms_queue_heartbeat(name):
                queued.append(name)
            else:
                missing.append(name)
        self.heartbeat_state_label.setText(f"BMS HB queued: {len(queued)}/{len(bms_names)}")
        self.control_state_label.setText("Running" if queued else "Idle")
        self.last_control_result_label.setText(f"BMS HB queued: {len(queued)}/{len(bms_names)}")
        self.refresh_fleet_heartbeat_status()
        self.control_log(f"[BMS][QUEUE] Heartbeat queued on polling workers: {len(queued)}/{len(bms_names)}")
        if missing:
            QMessageBox.warning(
                self,
                "BMS Heartbeat",
                "Some BMS monitoring workers are not running, so heartbeat was not started for them.\n"
                "Start BMS monitoring first to avoid opening a second Modbus connection.\n\n"
                f"Skipped: {', '.join(missing[:12])}{'...' if len(missing) > 12 else ''}",
            )

    def handle_stop_all_bms_heartbeats(self) -> None:
        self._ensure_bms_timer_store()
        queued_count = 0
        for name in list(self.bms_queue_heartbeat_timers.keys()):
            if self._stop_bms_queue_heartbeat(name):
                queued_count += 1
        fleet_count = self.fleet_manager.stop("BMS")
        for name, worker in list(getattr(self, "heartbeat_workers", {}).items()):
            try:
                worker.stop(); worker.join(timeout=2.0)
            except Exception:
                pass
            self.heartbeat_workers.pop(name, None)
        self.heartbeat_state_label.setText("Stopped")
        self.control_state_label.setText("Idle")
        self.last_control_result_label.setText(f"BMS HB stopped: queued={queued_count}, fleet={fleet_count}")
        self.last_heartbeat_status = "BMS HB stopped"
        self.refresh_global_status_bar()
        self.control_log(f"[BMS] Heartbeat stopped: queued={queued_count}, fleet={fleet_count}")

    def handle_start_bms_insulation_disable_cycle(self) -> None:
        bms_names = self._fleet_bms_names() if hasattr(self, "_fleet_bms_names") else [str(d.get("name", "")).strip() for d in getattr(self, "devices", []) if str(d.get("name", "")).strip()]
        if not bms_names:
            QMessageBox.information(self, "BMS 038B Cycle", "No BMS devices configured.")
            return
        interval_min = int(self.bms_insulation_interval_spin.value()) if hasattr(self, "bms_insulation_interval_spin") else 15
        self._ensure_bms_timer_store()
        if self.bms_038b_timer is not None:
            self.bms_038b_timer.stop(); self.bms_038b_timer.deleteLater()
        timer = QTimer(self)
        timer.setInterval(max(10_000, int(interval_min * 60_000)))

        def tick():
            queued = 0
            skipped = []
            for name in bms_names:
                if self._enqueue_bms_worker_command(name, "write_insulation_monitor_disable", label="write 0x038B=2"):
                    queued += 1
                else:
                    skipped.append(name)
            self.control_log(f"[BMS][QUEUE] 0x038B=2 queued: {queued}/{len(bms_names)}")
            if skipped:
                self.control_log(f"[BMS][QUEUE][WARN] 0x038B skipped because polling worker is not running: {', '.join(skipped[:8])}")

        timer.timeout.connect(tick)
        self.bms_038b_timer = timer
        timer.start()
        tick()
        if hasattr(self, "bms_insulation_state_label"):
            self.bms_insulation_state_label.setText(f"038B cycle queued / {interval_min} min")
        self.last_control_result_label.setText(f"038B cycle queued for {len(bms_names)} BMS")
        self.refresh_fleet_heartbeat_status()
        self.control_log(f"[BMS][QUEUE] Enabled periodic 0x038B=2 via BMS polling worker queue, interval={interval_min} min")

    def handle_stop_bms_insulation_disable_cycle(self) -> None:
        self._ensure_bms_timer_store()
        stopped = 0
        if self.bms_038b_timer is not None:
            self.bms_038b_timer.stop(); self.bms_038b_timer.deleteLater(); self.bms_038b_timer = None
            stopped = 1
        fleet_count = self.fleet_manager.disable_bms_insulation_disable(None)
        if hasattr(self, "bms_insulation_state_label"):
            self.bms_insulation_state_label.setText("038B cycle: stopped")
        self.last_control_result_label.setText(f"038B cycle stopped: queued={stopped}, fleet={fleet_count}")
        self.control_log(f"[BMS] Disabled periodic 0x038B=2: queued_timer={stopped}, fleet={fleet_count}")

    def refresh_fleet_heartbeat_status(self) -> None:
        if not hasattr(self, "fleet_manager"):
            return
        snapshots = self.fleet_manager.snapshots()
        if not snapshots:
            return
        bms_items = {k: v for k, v in snapshots.items() if k.startswith("BMS:")}
        pcs_items = {k: v for k, v in snapshots.items() if k.startswith("PCS:")}
        bms_online = sum(1 for v in bms_items.values() if v.get("online"))
        pcs_online = sum(1 for v in pcs_items.values() if v.get("online"))
        bms_total = len(bms_items)
        pcs_total = len(pcs_items)
        bms_038b = sum(1 for v in bms_items.values() if "bms_insulation_disable_038b" in (v.get("periodic_commands") or []))
        parts = []
        if bms_total:
            suffix = f", 038B={bms_038b}" if bms_038b else ""
            parts.append(f"BMS HB {bms_online}/{bms_total}{suffix}")
        if pcs_total:
            parts.append(f"PCS HB {pcs_online}/{pcs_total}")
        if not parts:
            return
        self.last_heartbeat_status = " | ".join(parts)
        if hasattr(self, "heartbeat_state_label"):
            self.heartbeat_state_label.setText(parts[0])
        self.refresh_global_status_bar()
