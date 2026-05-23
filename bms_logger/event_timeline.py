from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from .paths import user_data_dir
from typing import Any, Iterable, List


@dataclass
class TimelineEvent:
    timestamp: float
    time_text: str
    source: str
    category: str
    severity: str
    title: str
    detail: str
    suggestion: str = ""


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _format_time(ts: float) -> str:
    # Packet/CAN timestamps are often relative seconds. Keep them readable.
    if ts > 1_000_000_000:
        try:
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        except Exception:
            pass
    return f"{ts:.6f}s"


def _severity_rank(severity: str) -> int:
    table = {"CRITICAL": 0, "ERROR": 1, "WARN": 2, "INFO": 3, "OK": 4}
    return table.get(str(severity).upper(), 9)


class EventTimelineBuilder:
    """Builds a field troubleshooting timeline from live state and imported analysis data."""

    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx

    def build(self) -> List[TimelineEvent]:
        events: List[TimelineEvent] = []
        events.extend(self._from_cutoff_states())
        events.extend(self._from_derating_states())
        events.extend(self._from_packet_records())
        events.extend(self._from_can_anomalies())
        events.extend(self._from_signal_compare())
        events.extend(self._from_audit_logs())
        events.extend(self._from_latest_errors())
        events.sort(key=lambda e: (e.timestamp, _severity_rank(e.severity), e.category))
        return events

    def summarize(self, events: Iterable[TimelineEvent]) -> dict[str, Any]:
        rows = list(events)
        by_category: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        for e in rows:
            by_category[e.category] = by_category.get(e.category, 0) + 1
            by_severity[e.severity] = by_severity.get(e.severity, 0) + 1
        critical = [e for e in rows if e.severity in {"CRITICAL", "ERROR"}]
        warnings = [e for e in rows if e.severity == "WARN"]
        return {
            "total": len(rows),
            "critical_or_error": len(critical),
            "warning": len(warnings),
            "by_category": by_category,
            "by_severity": by_severity,
            "first_event": rows[0].time_text if rows else "-",
            "last_event": rows[-1].time_text if rows else "-",
            "root_cause_hints": self.root_cause_hints(rows),
        }

    def root_cause_hints(self, events: Iterable[TimelineEvent]) -> List[str]:
        rows = list(events)
        hints: List[str] = []
        cats = [e.category for e in rows]
        if "CAN Anomaly" in cats and "Modbus Timeout" in cats:
            first_can = next((e for e in rows if e.category == "CAN Anomaly"), None)
            first_timeout = next((e for e in rows if e.category == "Modbus Timeout"), None)
            if first_can and first_timeout and first_can.timestamp <= first_timeout.timestamp:
                hints.append("CAN anomaly appears before Modbus timeout; check upstream CAN/BMS data path before EMS polling.")
            else:
                hints.append("Modbus timeout and CAN anomaly both exist; compare timestamps to isolate network vs device-side issue.")
        if "PCS Protection" in cats and "Cutoff" in cats:
            hints.append("PCS protection and cutoff both occurred; verify whether PCS fault caused BMS protection or vice versa.")
        if "Modbus Exception" in cats:
            hints.append("Modbus exception responses exist; verify register address, function code, access permission and device state.")
        if "Signal Compare" in cats:
            hints.append("Cross-protocol signal deviation exists; compare CAN and Modbus scaling, timestamp alignment and source priority.")
        if "Control" in cats and ("Modbus Timeout" in cats or "Modbus Exception" in cats):
            hints.append("Control actions overlap with communication errors; check command confirmation timing and retry settings.")
        if not hints and rows:
            hints.append("No obvious root-cause chain detected; inspect high-severity events and packet/CAN details around the first abnormal timestamp.")
        return hints[:8]

    def _from_cutoff_states(self) -> List[TimelineEvent]:
        events: List[TimelineEvent] = []
        for name, states in getattr(self.ctx, "cutoff_alarm_states", {}).items():
            active = []
            if states.get("charge_cutoff"):
                active.append("charge")
            if states.get("discharge_cutoff"):
                active.append("discharge")
            if active:
                events.append(TimelineEvent(
                    timestamp=0.0,
                    time_text="current",
                    source=name,
                    category="Cutoff",
                    severity="CRITICAL",
                    title=f"Cutoff active: {', '.join(active)}",
                    detail=f"Active cutoff state in {name}: {states}",
                    suggestion="Check max/min cell voltage, cutoff thresholds, PCS output and HV workflow state.",
                ))
        return events

    def _from_derating_states(self) -> List[TimelineEvent]:
        events: List[TimelineEvent] = []
        for name, state in getattr(self.ctx, "derating_state", {}).items():
            if state.get("active"):
                events.append(TimelineEvent(
                    timestamp=0.0,
                    time_text="current",
                    source=name,
                    category="Derating",
                    severity="WARN",
                    title="Derating active",
                    detail=f"Derating state: {state}",
                    suggestion="Check cell voltage margin and PCS target power recovery settings.",
                ))
        return events

    def _from_packet_records(self) -> List[TimelineEvent]:
        events: List[TimelineEvent] = []
        for rec in list(getattr(self.ctx, "packet_records", []))[:20000]:
            status = getattr(rec, "status", "")
            if status not in {"Timeout", "Exception"}:
                continue
            ts = _safe_float(getattr(rec, "timestamp", 0.0))
            fc = getattr(rec, "function_code", "-")
            address = getattr(rec, "address", "-") or "-"
            unit = getattr(rec, "unit_id", "-")
            if status == "Timeout":
                events.append(TimelineEvent(
                    timestamp=ts,
                    time_text=_format_time(ts),
                    source=f"Unit {unit}",
                    category="Modbus Timeout",
                    severity="ERROR",
                    title=f"Modbus timeout FC{fc} addr={address}",
                    detail=f"Packet #{getattr(rec, 'index', '-')}: {getattr(rec, 'summary', '')}",
                    suggestion="Check device response time, network loss, polling interval or timeout setting.",
                ))
            elif status == "Exception":
                events.append(TimelineEvent(
                    timestamp=ts,
                    time_text=_format_time(ts),
                    source=f"Unit {unit}",
                    category="Modbus Exception",
                    severity="WARN",
                    title=f"Modbus exception FC{fc} addr={address}",
                    detail=f"Exception code={getattr(rec, 'exception_code', '-')}; {getattr(rec, 'summary', '')}",
                    suggestion="Verify register address, function code, access permission and device state.",
                ))
        return events

    def _from_can_anomalies(self) -> List[TimelineEvent]:
        events: List[TimelineEvent] = []
        for item in list(getattr(self.ctx, "can_anomalies", []))[:2000]:
            ts = _safe_float(item.get("time", 0.0))
            events.append(TimelineEvent(
                timestamp=ts,
                time_text=str(item.get("time", "-")),
                source=str(item.get("can_id", "-")),
                category="CAN Anomaly",
                severity="WARN",
                title=str(item.get("type", "CAN anomaly")),
                detail=f"index={item.get('index','-')}; value={item.get('value','-')}; {item.get('detail','')}",
                suggestion="Check CAN bus load, lost frames, DBC scaling and device-side state transitions.",
            ))
        return events

    def _from_signal_compare(self) -> List[TimelineEvent]:
        events: List[TimelineEvent] = []
        stats = getattr(self.ctx, "last_signal_compare_stats", None)
        if not isinstance(stats, dict):
            return events
        try:
            max_diff = float(stats.get("max_diff", 0) or 0)
            avg_diff = float(stats.get("avg_diff", 0) or 0)
        except Exception:
            max_diff = avg_diff = 0.0
        if max_diff or avg_diff:
            events.append(TimelineEvent(
                timestamp=0.0,
                time_text="analysis",
                source="Signal Compare",
                category="Signal Compare",
                severity="WARN" if max_diff else "INFO",
                title="CAN / Modbus signal deviation",
                detail=f"max_diff={max_diff}, avg_diff={avg_diff}, samples={stats.get('sample_count','-')}, delay={stats.get('delay_ms','-')}ms",
                suggestion="Check scale/offset consistency, timestamp alignment and source update rate.",
            ))
        return events

    def _from_audit_logs(self) -> List[TimelineEvent]:
        events: List[TimelineEvent] = []
        try:
            logs_dir = self.ctx.get_profile_path("logs")
        except Exception:
            logs_dir = user_data_dir() / "logs"
        for path in sorted(Path(logs_dir).glob("audit_*.csv"))[-5:]:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        action = row.get("action") or row.get("Action") or "Control"
                        success = (row.get("success") or row.get("Success") or "").lower()
                        target = row.get("target") or row.get("Target") or "-"
                        message = row.get("message") or row.get("Message") or ""
                        ts_text = row.get("timestamp") or row.get("Timestamp") or path.stem
                        sev = "INFO" if success in {"true", "1", "ok", "success"} else "WARN"
                        events.append(TimelineEvent(
                            timestamp=0.0,
                            time_text=ts_text,
                            source=target,
                            category="Control",
                            severity=sev,
                            title=action,
                            detail=message,
                            suggestion="Review control result and nearby communication events if action failed.",
                        ))
            except Exception:
                pass
        return events[-1000:]

    def _from_latest_errors(self) -> List[TimelineEvent]:
        msg = getattr(self.ctx, "last_error_message", "-")
        if not msg or msg == "-":
            return []
        return [TimelineEvent(
            timestamp=0.0,
            time_text="current",
            source="System",
            category="System Error",
            severity="ERROR",
            title="Latest error",
            detail=str(msg),
            suggestion="Inspect operation log and device task status around this error.",
        )]
