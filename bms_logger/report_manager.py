from __future__ import annotations

import csv
import html
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable

from bms_logger.event_timeline import EventTimelineBuilder
from bms_logger.communication_analyzer import CommunicationAnalyzerPro


def _safe_text(value: Any) -> str:
    return html.escape(str(value if value is not None else "-"))


def _read_csv_rows(path: Path, limit: int = 5000) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            rows = []
            for i, row in enumerate(csv.DictReader(f)):
                if i >= limit:
                    break
                rows.append(dict(row))
            return rows
    except Exception:
        return []


def _count_active_alarm_rows(profile_dir: Path) -> tuple[int, list[str]]:
    active = 0
    examples: list[str] = []
    for path in sorted(profile_dir.rglob("*alarm*.csv")):
        for row in _read_csv_rows(path, limit=2000):
            try:
                count = int(row.get("alarm_active_count", "0") or 0)
            except Exception:
                count = 0
            text = row.get("active_alarm_text", "")
            if count > 0 or text:
                active += 1
                if len(examples) < 10:
                    examples.append(
                        f"{path.name}: {row.get('timestamp','-')} | "
                        f"{row.get('device_name','-')} | {text or count}"
                    )
    return active, examples


def _file_inventory(profile_dir: Path) -> list[tuple[str, int]]:
    items: list[tuple[str, int]] = []
    if not profile_dir.exists():
        return items
    for path in profile_dir.rglob("*"):
        if path.is_file():
            try:
                items.append((str(path.relative_to(profile_dir)), path.stat().st_size))
            except Exception:
                pass
    return sorted(items)


class ReportManager:
    """Builds field-friendly HTML reports and debug packages for ESS-AIO profiles."""

    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx

    def reports_dir(self) -> Path:
        path = self.ctx.get_profile_path("reports") if hasattr(self.ctx, "get_profile_path") else Path.cwd() / "reports"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def build_report_context(self) -> Dict[str, Any]:
        ctx = self.ctx
        profile_dir = getattr(ctx, "current_profile_dir", Path.cwd())
        devices = list(getattr(ctx, "devices", []))
        pcs_configs = dict(getattr(ctx, "pcs_configs", {}))
        site = getattr(ctx, "site", None)
        clusters = getattr(site, "clusters", []) if site is not None else []
        latest = dict(getattr(ctx, "latest_snapshots", {}))

        online = stale = offline = 0
        for _, row in getattr(ctx, "device_rows", {}).items():
            try:
                item = ctx.device_table.item(row, 12)
                state = item.text() if item else "Unknown"
            except Exception:
                state = "Unknown"
            if state == "Online":
                online += 1
            elif state == "Stale":
                stale += 1
            elif state in ["Offline", "Error"]:
                offline += 1

        active_alarm_rows, alarm_examples = _count_active_alarm_rows(profile_dir)
        packet_records = list(getattr(ctx, "packet_records", []))
        try:
            communication_analysis = dict(getattr(ctx, "communication_analysis", None) or CommunicationAnalyzerPro().analyze_modbus(packet_records))
        except Exception:
            communication_analysis = {"issues": [], "conclusions": [], "latency": {}}
        can_records = list(getattr(ctx, "can_records", []))
        can_anomalies = list(getattr(ctx, "can_anomalies", []))
        try:
            timeline_events = EventTimelineBuilder(ctx).build()
            timeline_summary = EventTimelineBuilder(ctx).summarize(timeline_events)
        except Exception:
            timeline_events = []
            timeline_summary = {"total": 0, "critical_or_error": 0, "warning": 0, "root_cause_hints": []}

        return {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "profile_name": getattr(ctx, "current_profile_name", "default"),
            "profile_dir": str(profile_dir),
            "session": getattr(ctx, "debug_session", None) or {},
            "devices": devices,
            "pcs_configs": pcs_configs,
            "clusters": clusters,
            "latest_snapshots": latest,
            "status": {
                "sampling": getattr(ctx, "last_sampling_status", "-"),
                "heartbeat": getattr(ctx, "last_heartbeat_status", "-"),
                "hv": getattr(ctx, "last_hv_status", "-"),
                "last_error": getattr(ctx, "last_error_message", "-"),
                "online": online,
                "stale": stale,
                "offline": offline,
            },
            "alarms": {"active_rows": active_alarm_rows, "examples": alarm_examples},
            "packet": {
                "total": len(packet_records),
                "exceptions": sum(1 for r in packet_records if getattr(r, "status", "") == "Exception"),
                "timeouts": sum(1 for r in packet_records if getattr(r, "status", "") == "Timeout"),
                "communication_analysis": communication_analysis,
            },
            "can": {"total": len(can_records), "anomalies": len(can_anomalies)},
            "timeline": {"events": timeline_events[:200], "summary": timeline_summary},
            "files": _file_inventory(profile_dir),
        }

    def render_html(self, data: Dict[str, Any]) -> str:
        def rows(items: Iterable[Iterable[Any]]) -> str:
            return "\n".join("<tr>" + "".join(f"<td>{_safe_text(cell)}</td>" for cell in row) + "</tr>" for row in items)

        devices = data["devices"]
        pcs_configs = data["pcs_configs"]
        clusters = data["clusters"]
        latest = data["latest_snapshots"]
        status = data["status"]
        alarms = data["alarms"]
        packet = data["packet"]
        communication_analysis = packet.get("communication_analysis", {}) or {}
        communication_latency = communication_analysis.get("latency", {}) or {}
        communication_conclusions = communication_analysis.get("conclusions", []) or []
        communication_issues = communication_analysis.get("issues", []) or []
        can = data["can"]
        timeline = data.get("timeline", {}) or {}
        timeline_summary = timeline.get("summary", {}) or {}
        timeline_events = timeline.get("events", []) or []
        session = data.get("session") or {}

        cluster_rows = []
        for cluster in clusters:
            bms_names = ", ".join(getattr(dev, "name", "-") for dev in getattr(cluster, "bms_devices", [])) or "-"
            pcs = getattr(getattr(cluster, "pcs_device", None), "name", "-")
            cluster_rows.append([getattr(cluster, "name", "-"), bms_names, pcs])

        snapshot_rows = [[
            name,
            snap.get("soc", "-"),
            snap.get("system_voltage", "-"),
            snap.get("system_current", "-"),
            snap.get("system_power", "-"),
            snap.get("max_cell_voltage", "-"),
            snap.get("min_cell_voltage", "-"),
        ] for name, snap in latest.items()]

        file_rows = [[rel, size] for rel, size in data.get("files", [])[:200]]
        alarm_rows = [[line] for line in alarms.get("examples", [])] or [["No active alarm examples found"]]
        timeline_rows = [[
            getattr(e, "time_text", "-"),
            getattr(e, "severity", "-"),
            getattr(e, "category", "-"),
            getattr(e, "source", "-"),
            getattr(e, "title", "-"),
            getattr(e, "suggestion", "-"),
        ] for e in timeline_events[:50]] or [["-", "-", "-", "-", "No timeline events", "-"]]
        timeline_hints = [[hint] for hint in timeline_summary.get("root_cause_hints", [])] or [["No root-cause hints available."]]
        communication_conclusion_rows = [[line] for line in communication_conclusions] or [["No communication diagnosis conclusion available."]]
        communication_issue_rows = []
        for issue in communication_issues[:20]:
            if hasattr(issue, "as_row"):
                communication_issue_rows.append(issue.as_row())
            else:
                communication_issue_rows.append(list(issue))
        if not communication_issue_rows:
            communication_issue_rows = [["OK", "No obvious communication issue", "0", "-", "-", "Info"]]

        return f"""
<!doctype html>
<html><head><meta charset="utf-8" /><title>ESS-AIO Debug Report</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei UI', Arial, sans-serif; background:#f4f7fb; color:#0f172a; margin:24px; }}
h1 {{ color:#0f4c81; margin-bottom:4px; }}
h2 {{ color:#075985; border-bottom:1px solid #cbd5e1; padding-bottom:6px; margin-top:24px; }}
.card {{ background:#ffffff; border:1px solid #dbe3ef; border-radius:10px; padding:14px 16px; margin:12px 0; box-shadow:0 1px 2px rgba(15,23,42,0.06); }}
.grid {{ display:grid; grid-template-columns: repeat(4, 1fr); gap:12px; }}
.metric {{ background:#eef6ff; border:1px solid #cfe8ff; border-radius:8px; padding:10px; }}
.metric b {{ display:block; font-size:20px; color:#0052d9; }}
table {{ width:100%; border-collapse:collapse; background:#fff; }}
th, td {{ border:1px solid #dbe3ef; padding:7px 8px; text-align:left; font-size:13px; }}
th {{ background:#eaf3ff; color:#075985; }}
.small {{ color:#64748b; font-size:12px; }}
</style></head><body>
<h1>ESS-AIO Debug Report</h1>
<div class="small">Generated at {_safe_text(data['generated_at'])} | Profile: {_safe_text(data['profile_name'])}</div>
<div class="card grid"><div class="metric">BMS Devices <b>{len(devices)}</b></div><div class="metric">PCS Devices <b>{len(pcs_configs)}</b></div><div class="metric">Online BMS <b>{status['online']}</b></div><div class="metric">Active Alarm Rows <b>{alarms['active_rows']}</b></div></div>
<h2>Session</h2><div class="card"><table><tr><th>Name</th><th>Started</th><th>Ended</th><th>Notes</th></tr><tr><td>{_safe_text(session.get('name','-'))}</td><td>{_safe_text(session.get('started_at','-'))}</td><td>{_safe_text(session.get('ended_at','-'))}</td><td>{_safe_text(session.get('notes','-'))}</td></tr></table></div>
<h2>System Status</h2><div class="card"><table><tr><th>Sampling</th><th>Heartbeat</th><th>HV</th><th>Last Error</th><th>Stale</th><th>Offline/Error</th></tr><tr><td>{_safe_text(status['sampling'])}</td><td>{_safe_text(status['heartbeat'])}</td><td>{_safe_text(status['hv'])}</td><td>{_safe_text(status['last_error'])}</td><td>{status['stale']}</td><td>{status['offline']}</td></tr></table></div>
<h2>Devices</h2><div class="card"><table><tr><th>Name</th><th>Host</th><th>Port</th><th>Unit ID</th><th>Interval</th></tr>{rows([[d.get('name','-'), d.get('host','-'), d.get('port','-'), d.get('unit_id','-'), d.get('interval','-')] for d in devices])}</table></div>
<h2>PCS</h2><div class="card"><table><tr><th>Name</th><th>Host</th><th>Port</th><th>Unit ID</th><th>Enabled</th><th>Driver</th></tr>{rows([[name, cfg.get('host','-'), cfg.get('port','-'), cfg.get('unit_id','-'), cfg.get('enabled','-'), cfg.get('driver','-')] for name, cfg in pcs_configs.items()])}</table></div>
<h2>Clusters</h2><div class="card"><table><tr><th>Cluster</th><th>BMS Devices</th><th>PCS</th></tr>{rows(cluster_rows)}</table></div>
<h2>Latest Snapshot</h2><div class="card"><table><tr><th>Device</th><th>SOC</th><th>Voltage</th><th>Current</th><th>Power</th><th>Max Cell V</th><th>Min Cell V</th></tr>{rows(snapshot_rows)}</table></div>
<h2>Alarm Summary</h2><div class="card"><p>Active alarm rows found in profile CSVs: <b>{alarms['active_rows']}</b></p><table><tr><th>Examples</th></tr>{rows(alarm_rows)}</table></div>
<h2>Communication Analyzer Pro</h2><div class="card"><table><tr><th>Modbus Packets</th><th>Exceptions</th><th>Timeouts</th><th>Error Rate</th><th>Latency p50</th><th>Latency p90</th><th>Latency Max</th></tr><tr><td>{packet['total']}</td><td>{packet['exceptions']}</td><td>{packet['timeouts']}</td><td>{communication_analysis.get('error_rate', 0.0):.2f}%</td><td>{_safe_text(f"{communication_latency.get('p50', 0):.2f} ms" if communication_latency.get('p50') is not None else "-")}</td><td>{_safe_text(f"{communication_latency.get('p90', 0):.2f} ms" if communication_latency.get('p90') is not None else "-")}</td><td>{_safe_text(f"{communication_latency.get('max', 0):.2f} ms" if communication_latency.get('max') is not None else "-")}</td></tr></table><h3>Diagnosis Conclusions</h3><table><tr><th>Conclusion</th></tr>{rows(communication_conclusion_rows)}</table><h3>Top Issues</h3><table><tr><th>Type</th><th>Key</th><th>Count</th><th>Worst/Avg</th><th>Suggestion</th><th>Severity</th></tr>{rows(communication_issue_rows)}</table></div>
<h2>CAN Summary</h2><div class="card"><table><tr><th>CAN Frames</th><th>CAN Anomalies</th></tr><tr><td>{can['total']}</td><td>{can['anomalies']}</td></tr></table></div>
<h2>Event Timeline</h2><div class="card"><p>Total events: <b>{timeline_summary.get('total', 0)}</b> | Critical/Error: <b>{timeline_summary.get('critical_or_error', 0)}</b> | Warning: <b>{timeline_summary.get('warning', 0)}</b></p><table><tr><th>Time</th><th>Severity</th><th>Category</th><th>Source</th><th>Title</th><th>Suggestion</th></tr>{rows(timeline_rows)}</table></div>
<h2>Root Cause Hints</h2><div class="card"><table><tr><th>Hint</th></tr>{rows(timeline_hints)}</table></div>
<h2>Profile File Inventory</h2><div class="card"><table><tr><th>File</th><th>Size bytes</th></tr>{rows(file_rows)}</table></div>
</body></html>
"""

    def write_report(self) -> Path:
        html_text = self.render_html(self.build_report_context())
        path = self.reports_dir() / f"debug_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        with open(path, "w", encoding="utf-8") as f:
            f.write(html_text)
        return path

    def export_debug_package(self, include_report: bool = True) -> Path:
        profile_dir = getattr(self.ctx, "current_profile_dir", Path.cwd())
        zip_path = self.reports_dir() / f"ESS-AIO_debug_package_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        report_path = self.write_report() if include_report else None
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            if profile_dir.exists():
                for path in profile_dir.rglob("*"):
                    if path.is_file():
                        try:
                            if path.resolve() == zip_path.resolve():
                                continue
                            zf.write(path, path.relative_to(profile_dir))
                        except Exception:
                            pass
            if report_path and report_path.exists():
                zf.write(report_path, Path("reports") / report_path.name)
        return zip_path
