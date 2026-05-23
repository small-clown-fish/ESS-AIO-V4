from __future__ import annotations

from typing import Any, Dict


class BmsPcsService:
    def __init__(self) -> None:
        self.enabled = True

    def _manual_connected_pcs_name(self, cluster: Any, ctx: Any) -> str:
        """Return a PCS name only when the operator explicitly connected it.

        The BMS sampling service runs on every BMS snapshot. It must not create
        PCS clients or call connect() just because a PCS is configured/bound in
        the project. A PCS is considered available to background services only
        after the user presses Connect selected/all PCS, which creates an entry
        in ctx.pcs_workers.
        """
        configured = []
        if getattr(cluster, "pcs_device", None):
            configured.append(cluster.pcs_device.name)
        for pcs in getattr(cluster, "pcs_devices", []) or []:
            if pcs.name not in configured:
                configured.append(pcs.name)

        active_workers = getattr(ctx, "pcs_workers", {}) or {}
        for pcs_name in configured:
            if pcs_name not in active_workers:
                continue
            pcs_cfg = ctx.get_pcs_config_by_name(pcs_name) if hasattr(ctx, "get_pcs_config_by_name") else {}
            if pcs_cfg and pcs_cfg.get("enabled", False) and pcs_cfg.get("host"):
                return pcs_name
        return ""

    def on_snapshot(self, device_name: str, snapshot: Dict[str, Any], ctx: Any) -> None:
        cluster = ctx.get_cluster_by_device(device_name)
        if cluster is None:
            ctx.control_log(f"[SERVICE] {device_name}: no cluster found")
            return
        if not self.enabled:
            return

        self.check_power_derating(device_name, snapshot, ctx)
        self.check_cutoff(device_name, snapshot, ctx)
        self.check_power_tracking(device_name, ctx)
        self.check_pcs_fault_protection(device_name, ctx)

    def check_power_derating(self, device_name: str, snapshot: Dict[str, Any], ctx: Any) -> None:
        if not ctx.power_derating_enabled:
            return

        cluster = ctx.get_cluster_by_device(device_name)
        if cluster is None:
            return

        max_v, min_v = self._get_cluster_voltage_stats(cluster, ctx)
        if max_v is None or min_v is None:
            return

        cluster_key = cluster.name
        pcs_name = self._manual_connected_pcs_name(cluster, ctx)

        charge_derating_threshold = ctx.strategy_engine.get_float('charge_cutoff_max_cell_voltage', ctx.charge_cutoff_max_cell_voltage) - ctx.strategy_engine.get_float('derating_margin_mv', ctx.derating_margin_mv)
        discharge_derating_threshold = ctx.strategy_engine.get_float('discharge_cutoff_min_cell_voltage', ctx.discharge_cutoff_min_cell_voltage) + ctx.strategy_engine.get_float('derating_margin_mv', ctx.derating_margin_mv)

        charge_derating = max_v >= charge_derating_threshold
        discharge_derating = min_v <= discharge_derating_threshold
        should_derate = charge_derating or discharge_derating

        state = ctx.derating_state.get(cluster_key, {"active": False})

        if should_derate:
            if state.get("active", False):
                return

            reason = "charge_derating" if charge_derating else "discharge_derating"

            ctx.control_log(
                f"[SERVICE][DERATING] {cluster.name}: triggered reason={reason}, "
                f"max_cell_voltage={max_v}mV, min_cell_voltage={min_v}mV, "
                f"target_power={ctx.strategy_engine.get_float('derating_power_kw', ctx.derating_power_kw)}kW, pcs={pcs_name}"
            )

            if pcs_name:
                ctx.service_action_controller.derating(pcs_name, reason, ctx.strategy_engine.get_float('derating_power_kw', ctx.derating_power_kw))
            else:
                ctx.control_log(f"[SERVICE][DERATING] {cluster.name}: BMS-only mode, PCS derating command skipped")

            ctx.derating_state[cluster_key] = {
                "active": True,
                "reason": reason,
            }

        else:
            if state.get("active", False):
                ctx.control_log(
                    f"[SERVICE][DERATING] {cluster.name}: recovered, restoring power, pcs={pcs_name}"
                )

                if pcs_name:
                    ctx.service_action_controller.derating_recover(pcs_name)

                ctx.derating_state[cluster_key] = {
                    "active": False,
                    "reason": "",
                }

    def check_cutoff(self, device_name: str, snapshot: Dict[str, Any], ctx: Any) -> None:
        cluster = ctx.get_cluster_by_device(device_name)
        if cluster is None:
            return

        max_v, min_v = self._get_cluster_voltage_stats(cluster, ctx)
        if max_v is None or min_v is None:
            return

        cluster_key = cluster.name
        pcs_name = self._manual_connected_pcs_name(cluster, ctx)

        charge_alarm = max_v >= ctx.strategy_engine.get_float('charge_cutoff_max_cell_voltage', ctx.charge_cutoff_max_cell_voltage)
        discharge_alarm = min_v <= ctx.strategy_engine.get_float('discharge_cutoff_min_cell_voltage', ctx.discharge_cutoff_min_cell_voltage)

        old_state = ctx.cutoff_alarm_states.get(cluster_key, {})

        # ===== 触发 =====
        if charge_alarm and not old_state.get("charge_cutoff", False):
            msg = (
                f"[SERVICE][CUTOFF] {cluster.name}: Charge cutoff triggered. "
                f"max_cell_voltage={max_v}mV, "
                f"threshold={ctx.strategy_engine.get_float('charge_cutoff_max_cell_voltage', ctx.charge_cutoff_max_cell_voltage)}mV, "
                f"pcs={pcs_name}"
            )
            ctx.control_log(msg)
            ctx.log(msg)

            if pcs_name:
                ctx.service_action_controller.cutoff(pcs_name, "charge")
            else:
                ctx.control_log(f"[SERVICE][CUTOFF] {cluster.name}: BMS-only mode, PCS charge cutoff command skipped")

        if discharge_alarm and not old_state.get("discharge_cutoff", False):
            msg = (
                f"[SERVICE][CUTOFF] {cluster.name}: Discharge cutoff triggered. "
                f"min_cell_voltage={min_v}mV, "
                f"threshold={ctx.strategy_engine.get_float('discharge_cutoff_min_cell_voltage', ctx.discharge_cutoff_min_cell_voltage)}mV, "
                f"pcs={pcs_name}"
            )
            ctx.control_log(msg)
            ctx.log(msg)

            if pcs_name:
                ctx.service_action_controller.cutoff(pcs_name, "discharge")
            else:
                ctx.control_log(f"[SERVICE][CUTOFF] {cluster.name}: BMS-only mode, PCS discharge cutoff command skipped")

        # ===== 恢复 =====
        if not charge_alarm and old_state.get("charge_cutoff", False):
            msg = f"[SERVICE][CUTOFF] {cluster.name}: Charge cutoff recovered."
            ctx.control_log(msg)
            ctx.log(msg)

        if not discharge_alarm and old_state.get("discharge_cutoff", False):
            msg = f"[SERVICE][CUTOFF] {cluster.name}: Discharge cutoff recovered."
            ctx.control_log(msg)
            ctx.log(msg)

        ctx.cutoff_alarm_states[cluster_key] = {
            "charge_cutoff": charge_alarm,
            "discharge_cutoff": discharge_alarm,
        }

    def check_power_tracking(self, device_name: str, ctx: Any) -> None:
        import time

        if not ctx.power_tracking_enabled:
            return

        cluster = ctx.get_cluster_by_device(device_name)
        if cluster is None:
            return

        pcs_name = self._manual_connected_pcs_name(cluster, ctx)
        if not pcs_name:
            return

        target_power = ctx.last_user_power_kw.get(pcs_name)
        if target_power is None:
            return

        pcs_client = ctx.create_pcs_client_for_device(device_name)

        try:
            if not pcs_client.connect():
                return

            actual_power = pcs_client.get_active_power()
            diff = abs(actual_power - target_power)

            state = ctx.power_tracking_retry_state.get(
                pcs_name,
                {
                    "retry_count": 0,
                    "last_retry_time": 0,
                },
            )

            if diff > ctx.strategy_engine.get_float('power_tracking_tolerance_kw', ctx.power_tracking_tolerance_kw):
                count = ctx.power_tracking_counters.get(pcs_name, 0) + 1
                ctx.power_tracking_counters[pcs_name] = count

                if count >= ctx.power_tracking_confirm_count:
                    ctx.control_log(
                        f"[SERVICE][PCS POWER TRACK] {cluster.name}: deviation alarm, "
                        f"pcs={pcs_name}, target={target_power}kW, "
                        f"actual={actual_power}kW, diff={diff}kW"
                    )

                    if ctx.power_tracking_auto_retry:
                        now = time.time()

                        if state["retry_count"] >= ctx.power_tracking_max_retry:
                            ctx.control_log(
                                f"[SERVICE][PCS POWER TRACK] {cluster.name}: max retry reached, pcs={pcs_name}"
                            )
                            return

                        if now - state["last_retry_time"] < ctx.power_tracking_retry_interval:
                            return

                        ctx.control_log(
                            f"[SERVICE][PCS POWER TRACK] {cluster.name}: retry set power "
                            f"{target_power}kW, pcs={pcs_name}"
                        )

                        ok = pcs_client.set_active_power(target_power)

                        if ok:
                            state["retry_count"] += 1
                            state["last_retry_time"] = now
                            ctx.power_tracking_retry_state[pcs_name] = state
                        else:
                            ctx.control_log(
                                f"[SERVICE][PCS POWER TRACK] {cluster.name}: retry failed, pcs={pcs_name}"
                            )

            else:
                if ctx.power_tracking_counters.get(pcs_name, 0) > 0:
                    ctx.control_log(
                        f"[SERVICE][PCS POWER TRACK] {cluster.name}: recovered, "
                        f"pcs={pcs_name}, target={target_power}kW, actual={actual_power}kW"
                    )

                ctx.power_tracking_counters[pcs_name] = 0
                ctx.power_tracking_retry_state[pcs_name] = {
                    "retry_count": 0,
                    "last_retry_time": 0,
                }

        except Exception as exc:
            ctx.control_log(
                f"[SERVICE][PCS POWER TRACK] {cluster.name}: exception, pcs={pcs_name} - {exc}"
            )

        finally:
            try:
                pcs_client.close()
            except Exception:
                pass

    def check_pcs_fault_protection(self, device_name: str, ctx: Any) -> None:
        if not ctx.pcs_fault_protection_enabled:
            return

        cluster = ctx.get_cluster_by_device(device_name)
        if cluster is None:
            return

        pcs_name = self._manual_connected_pcs_name(cluster, ctx)
        if not pcs_name:
            return

        mode = ctx.strategy_engine.get_str('pcs_fault_protection_mode', ctx.pcs_fault_protection_mode)
        fault_reason = ""

        pcs_client = ctx.create_pcs_client_for_device(device_name)

        try:
            if not pcs_client.connect():
                fault_reason = "PCS connect failed"
            else:
                try:
                    fault_status = pcs_client.get_fault_status()
                    if int(fault_status) != 0:
                        fault_reason = f"PCS fault_status={fault_status}"
                except Exception:
                    pass

                try:
                    breaker_open = pcs_client.is_dc_breaker_open()
                    breaker_closed = pcs_client.is_dc_breaker_closed()

                    if not breaker_open and not breaker_closed:
                        fault_reason = "PCS dc breaker unknown"

                except Exception as exc:
                    fault_reason = f"PCS breaker check failed: {exc}"

        except Exception as exc:
            fault_reason = f"PCS protection exception: {exc}"

        finally:
            try:
                pcs_client.close()
            except Exception:
                pass

        if not fault_reason:
            if ctx.pcs_fault_counters.get(pcs_name, 0) > 0:
                ctx.control_log(
                    f"[SERVICE][PCS PROTECT] {cluster.name}: recovered, pcs={pcs_name}"
                )

            ctx.pcs_fault_counters[pcs_name] = 0
            return

        count = ctx.pcs_fault_counters.get(pcs_name, 0) + 1
        ctx.pcs_fault_counters[pcs_name] = count

        if count < ctx.pcs_fault_confirm_count:
            return

        ctx.control_log(
            f"[SERVICE][PCS PROTECT] {cluster.name}: triggered, "
            f"pcs={pcs_name}, reason={fault_reason}, mode={mode}"
        )

        if mode == "Alarm Only":
            return

        if mode == "Stop PCS":
            ctx.service_action_controller.pcs_stop(pcs_name, source="PCS Protect")
            return

        if mode == "HV Off":
            ctx.service_action_controller.hv_off(pcs_name, source="PCS Protect")

    def _get_cluster_voltage_stats(self, cluster, ctx):
        max_list = []
        min_list = []

        for dev in cluster.bms_devices:
            snapshot = ctx.latest_snapshots.get(dev.name)
            if not snapshot:
                continue

            try:
                max_v = float(snapshot.get("max_cell_voltage"))
                min_v = float(snapshot.get("min_cell_voltage"))
            except Exception:
                continue

            max_list.append(max_v)
            min_list.append(min_v)

        if not max_list or not min_list:
            return None, None

        return max(max_list), min(min_list)