from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from ..charge_discharge_workflow import (
    ChargeDischargeSettings,
    ChargeDischargeWorkflowController,
    ChargeDischargeWorkflowWorker,
)


class ChargeDischargeControlMixin:
    def _build_cd_settings(self) -> ChargeDischargeSettings:
        mode = self.cd_mode_combo.currentText().strip().lower() if hasattr(self, "cd_mode_combo") else "discharge"
        positive_text = self.cd_positive_meaning_combo.currentText() if hasattr(self, "cd_positive_meaning_combo") else "+ = discharge"
        return ChargeDischargeSettings(
            mode=mode,
            target_power_kw=float(self.cd_power_spin.value()),
            ramp_step_kw=float(self.cd_ramp_step_spin.value()),
            ramp_interval_s=float(self.cd_ramp_interval_spin.value()),
            monitor_interval_s=float(getattr(self, "hv_poll_interval", 1.0)),
            step_timeout_s=float(getattr(self, "hv_step_timeout", 30.0)),
            auto_bms_hv=bool(self.cd_auto_bms_hv_check.isChecked()),
            auto_pcs_start=bool(self.cd_auto_pcs_start_check.isChecked()),
            auto_pcs_stop_on_finish=bool(self.cd_auto_pcs_stop_check.isChecked()),
            auto_bms_hv_off_on_stop=bool(self.cd_auto_bms_hv_off_check.isChecked()),
            positive_power_means="charge" if "charge" in positive_text and "discharge" not in positive_text.split("=")[-1] else "discharge",
            require_pcs_remote=bool(self.cd_require_remote_check.isChecked()),
            require_dc_breaker_closed=bool(self.cd_require_dc_closed_check.isChecked()),
            bms_heartbeat_interval_s=float(getattr(self, "heartbeat_interval", 1.0)),
            pcs_heartbeat_interval_s=1.0,
            use_bms_limit_clamp=bool(getattr(self, "cd_use_bms_clamp_check", None).isChecked()) if hasattr(self, "cd_use_bms_clamp_check") else True,
            power_limit_mode=(
                "follow_bms_max"
                if hasattr(self, "cd_power_limit_mode_combo") and self.cd_power_limit_mode_combo.currentText().startswith("Follow")
                else "target_with_clamp"
            ),
            clamp_margin=float(self.cd_clamp_margin_spin.value()) if hasattr(self, "cd_clamp_margin_spin") else 1.0,
        )

    def _build_cd_controller(self, device_name: str, settings: ChargeDischargeSettings) -> ChargeDischargeWorkflowController | None:
        bms_client = self._build_bms_client_for_device(device_name)
        if bms_client is None:
            return None
        pcs_client = self.create_pcs_client_for_device(device_name)
        return ChargeDischargeWorkflowController(
            bms_client=bms_client,
            pcs_client=pcs_client,
            settings=settings,
            log_callback=lambda msg: self.control_log(f"[CD] {device_name}: {msg}"),
            progress_callback=lambda state: self._on_cd_progress(device_name, state),
        )

    def _on_cd_progress(self, device_name: str, state: str) -> None:
        if hasattr(self, "cd_status_label"):
            self.cd_status_label.setText(f"{device_name}: {state}")
        if hasattr(self, "control_state_label"):
            self.control_state_label.setText(f"CD {state}")

    def _on_cd_log(self, device_name: str, message: str) -> None:
        self.control_log(f"[CD] {device_name}: {message}")

    def _on_cd_finished(self, device_name: str, action: str, ok: bool, message: str) -> None:
        key = f"{device_name}:{action}"
        try:
            self.charge_discharge_workers.pop(key, None)
        except Exception:
            pass
        text = f"{device_name}: {action} {'success' if ok else 'failed'} - {message}"
        if hasattr(self, "cd_status_label"):
            self.cd_status_label.setText(text)
        if hasattr(self, "last_control_result_label"):
            self.last_control_result_label.setText(text)
        self.control_log(f"[CD] {text}")

    def _start_cd_worker(self, action: str) -> None:
        device_name = self._get_selected_control_device()
        if not device_name:
            return
        key = f"{device_name}:{action}"
        if getattr(self, "charge_discharge_workers", {}).get(key):
            QMessageBox.warning(self, "Workflow running", f"Workflow already running: {key}")
            return
        settings = self._build_cd_settings()
        if action == "start" and abs(settings.target_power_kw) < 0.1:
            reply = QMessageBox.question(
                self,
                "Target power is zero",
                "Target power is 0 kW. Continue workflow?",
            )
            if reply != QMessageBox.Yes:
                return
        confirm_text = (
            f"Run {action} workflow for BMS device '{device_name}' and selected PCS?\n\n"
            f"Mode: {settings.mode}\n"
            f"Target: {settings.target_power_kw} kW\n"
            f"Ramp: {settings.ramp_step_kw} kW every {settings.ramp_interval_s}s\n"
            f"PCS sign: + means {settings.positive_power_means}\n"
            f"BMS clamp: {settings.use_bms_limit_clamp}, mode={settings.power_limit_mode}, margin={settings.clamp_margin}\n\n"
            "Make sure this is connected to a safe test setup."
        )
        reply = QMessageBox.question(self, "Confirm charge/discharge workflow", confirm_text)
        if reply != QMessageBox.Yes:
            return
        controller = self._build_cd_controller(device_name, settings)
        if controller is None:
            return
        worker = ChargeDischargeWorkflowWorker(
            action=action,
            controller=controller,
            device_name=device_name,
            log_callback=self._on_cd_log,
            progress_callback=self._on_cd_progress,
            finished_callback=self._on_cd_finished,
        )
        self.charge_discharge_workers[key] = worker
        if hasattr(self, "cd_status_label"):
            self.cd_status_label.setText(f"{device_name}: starting {action} workflow")
        self.control_log(f"[CD] {device_name}: starting {action} workflow")
        worker.start()

    def handle_cd_start_workflow(self) -> None:
        self._start_cd_worker("start")

    def handle_cd_stop_workflow(self) -> None:
        self._start_cd_worker("stop")

    def handle_cd_cancel_workflow(self) -> None:
        workers = list(getattr(self, "charge_discharge_workers", {}).items())
        if not workers:
            if hasattr(self, "cd_status_label"):
                self.cd_status_label.setText("No charge/discharge workflow running")
            return
        for key, worker in workers:
            try:
                worker.stop()
                self.control_log(f"[CD] Cancel requested: {key}")
            except Exception as exc:
                self.control_log(f"[CD] Cancel failed for {key}: {exc}")
        if hasattr(self, "cd_status_label"):
            self.cd_status_label.setText("Cancel requested")

    def _get_selected_cluster_for_dispatch(self):
        cluster_name = ""
        if hasattr(self, "cluster_dispatch_combo"):
            cluster_name = self.cluster_dispatch_combo.currentText().strip()
        if not cluster_name and hasattr(self, "default_cluster"):
            return self.default_cluster
        for cluster in getattr(self, "site", None).clusters if hasattr(self, "site") else []:
            if cluster.name == cluster_name:
                return cluster
        return getattr(self, "default_cluster", None)

    def _build_cluster_dispatch_controller(self):
        from ..cluster_workflow import ClusterDispatchController, ClusterDispatchSettings
        cluster = self._get_selected_cluster_for_dispatch()
        if cluster is None:
            QMessageBox.warning(self, "Warning", "No cluster selected.")
            return None
        if not getattr(cluster, "bms_devices", []):
            QMessageBox.warning(self, "Warning", f"Cluster '{cluster.name}' has no BMS device.")
            return None
        pcs_devices = list(getattr(cluster, "pcs_devices", []))
        if not pcs_devices and getattr(cluster, "pcs_device", None):
            pcs_devices = [cluster.pcs_device]
        if not pcs_devices:
            QMessageBox.warning(self, "Warning", f"Cluster '{cluster.name}' has no PCS devices.")
            return None

        bms_name = cluster.bms_devices[0].name
        bms_client = self._build_bms_client_for_device(bms_name)
        if bms_client is None:
            return None
        pcs_clients = {}
        for pcs in pcs_devices:
            try:
                pcs_clients[pcs.name] = self.create_pcs_client_for_pcs_name(pcs.name)
            except Exception as exc:
                self.control_log(f"[CLUSTER] Failed to create PCS client {pcs.name}: {exc}")
        if not pcs_clients:
            QMessageBox.warning(self, "Warning", f"No usable PCS clients in cluster '{cluster.name}'.")
            return None
        settings = ClusterDispatchSettings(
            target_power_kw=float(self.cluster_dispatch_power_spin.value()) if hasattr(self, "cluster_dispatch_power_spin") else 0.0,
            allocation_mode=self.cluster_dispatch_mode_combo.currentText() if hasattr(self, "cluster_dispatch_mode_combo") else getattr(cluster, "allocation_mode", "equal_split"),
            clamp_margin=float(self.cluster_dispatch_margin_spin.value()) if hasattr(self, "cluster_dispatch_margin_spin") else 1.0,
            use_bms_limit_clamp=bool(self.cluster_dispatch_use_clamp_check.isChecked()) if hasattr(self, "cluster_dispatch_use_clamp_check") else True,
        )
        return ClusterDispatchController(
            bms_client=bms_client,
            pcs_clients=pcs_clients,
            pcs_configs=getattr(self, "pcs_configs", {}),
            settings=settings,
            log_callback=lambda msg: self.control_log(f"[CLUSTER] {cluster.name}: {msg}"),
        )

    def handle_cluster_dispatch_once(self) -> None:
        controller = self._build_cluster_dispatch_controller()
        if controller is None:
            return
        target = float(self.cluster_dispatch_power_spin.value()) if hasattr(self, "cluster_dispatch_power_spin") else 0.0
        operation = "discharge" if target >= 0 else "charge"
        reply = QMessageBox.question(
            self,
            "Confirm cluster dispatch",
            f"Apply cluster total power {target:.1f} kW to selected cluster?\n\n"
            "This will split the total target across all PCS bound to the cluster.",
        )
        if reply != QMessageBox.Yes:
            return
        try:
            allocation = controller.dispatch_once(operation=operation)
            if hasattr(self, "cluster_dispatch_status_label"):
                self.cluster_dispatch_status_label.setText(f"Applied allocation: {allocation}")
        except Exception as exc:
            QMessageBox.critical(self, "Cluster dispatch failed", str(exc))
            if hasattr(self, "cluster_dispatch_status_label"):
                self.cluster_dispatch_status_label.setText(f"Failed: {exc}")

    def handle_cluster_stop_all(self) -> None:
        controller = self._build_cluster_dispatch_controller()
        if controller is None:
            return
        reply = QMessageBox.question(
            self,
            "Confirm stop all PCS",
            "Set all PCS in selected cluster to 0 kW and send PCS stop?",
        )
        if reply != QMessageBox.Yes:
            return
        try:
            controller.stop_all()
            if hasattr(self, "cluster_dispatch_status_label"):
                self.cluster_dispatch_status_label.setText("Stop all PCS command sent")
        except Exception as exc:
            QMessageBox.critical(self, "Cluster stop failed", str(exc))
            if hasattr(self, "cluster_dispatch_status_label"):
                self.cluster_dispatch_status_label.setText(f"Failed: {exc}")
