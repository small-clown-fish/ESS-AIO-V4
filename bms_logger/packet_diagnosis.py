from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

try:
    from .communication_analyzer import CommunicationAnalyzerPro
except Exception:  # pragma: no cover
    CommunicationAnalyzerPro = None  # type: ignore

try:
    from .point_table import PointTable, resolve_point_table_path
except Exception:  # pragma: no cover
    PointTable = None  # type: ignore
    resolve_point_table_path = None  # type: ignore


@dataclass
class DiagnosisIssue:
    severity: str
    layer: str
    time: str
    obj: str
    rule_id: str
    description: str
    evidence: str
    suggestion: str
    refs: Dict[str, Any] = field(default_factory=dict)

    def as_row(self) -> list[str]:
        return [self.severity, self.layer, self.time, self.obj, self.rule_id, self.description, self.evidence, self.suggestion]


class PacketDiagnosisEngine:
    """Cross-layer packet health checker for field troubleshooting.

    It deliberately uses conservative heuristic rules. The goal is not to prove a
    fault, but to mark suspicious places engineers should inspect first.
    """

    def __init__(self, point_table_path: str | Path | None = None) -> None:
        self.point_table_path = Path(point_table_path) if point_table_path else None
        self.point_table = self._load_point_table(self.point_table_path)
        self.protocol_dir = Path(__file__).resolve().parent / "protocols"
        self.mapping_by_key = self._load_mapping_index()
        self.semantic_by_key = self._load_semantic_index()

    def analyze(
        self,
        *,
        modbus_records: Iterable[Any] | None = None,
        can_records: Iterable[Any] | None = None,
        can_stats: Iterable[Any] | None = None,
        can_anomalies: Iterable[dict[str, Any]] | None = None,
        joint_rows: Iterable[dict[str, Any]] | None = None,
        can_signal_buffers: Dict[str, Sequence[tuple[float, float]]] | None = None,
        check_modbus: bool = True,
        check_can: bool = True,
        check_mapping: bool = True,
        check_business: bool = True,
    ) -> Dict[str, Any]:
        issues: list[DiagnosisIssue] = []
        modbus_records = list(modbus_records or [])
        can_records = list(can_records or [])
        can_stats = list(can_stats or [])
        can_anomalies = list(can_anomalies or [])
        joint_rows = list(joint_rows or [])
        can_signal_buffers = can_signal_buffers or {}

        if check_modbus:
            issues.extend(self._check_modbus(modbus_records))
        if check_can:
            issues.extend(self._check_can(can_records, can_stats, can_anomalies))
        if check_mapping:
            issues.extend(self._check_mapping(modbus_records, can_records, joint_rows))
        if check_business:
            issues.extend(self._check_business_signals(can_signal_buffers))
            issues.extend(self._check_fault_templates(modbus_records, can_records, can_signal_buffers, joint_rows))
        self._attach_raw_refs(issues, modbus_records, can_records, joint_rows)

        severity_rank = {"Critical": 0, "Warning": 1, "Info": 2, "OK": 3}
        issues.sort(key=lambda i: (severity_rank.get(i.severity, 9), i.layer, i.time, i.obj))
        summary = self._summary(issues, modbus_records, can_records, can_stats, joint_rows)
        summary["checks_enabled"] = {
            "modbus": check_modbus,
            "can": check_can,
            "mapping": check_mapping,
            "business": check_business,
        }
        return {"issues": issues, "summary": summary}

    def export_csv(self, analysis: Dict[str, Any], path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["severity", "layer", "time", "object", "rule_id", "description", "evidence", "suggestion"])
            for issue in analysis.get("issues", []):
                writer.writerow(issue.as_row() if hasattr(issue, "as_row") else issue)

    def export_markdown(self, analysis: Dict[str, Any], path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# Packet Diagnosis Report", ""]
        summary = analysis.get("summary", {}) or {}
        lines.extend(["## Summary", ""])
        for line in summary.get("conclusions", []):
            lines.append(f"- {line}")
        lines.extend(["", "## Issues", ""])
        if not analysis.get("issues"):
            lines.append("No issues found by the current rule set.")
        else:
            lines.append("| Severity | Layer | Time | Object | Rule | Description | Evidence | Suggested action |")
            lines.append("|---|---|---:|---|---|---|---|---|")
            for issue in analysis.get("issues", []):
                row = issue.as_row() if hasattr(issue, "as_row") else list(issue)
                lines.append("| " + " | ".join(self._md(str(x)) for x in row) + " |")
        path.write_text("\n".join(lines), encoding="utf-8")

    def _load_point_table(self, explicit_path: Path | None) -> Any:
        if PointTable is None:
            return None
        candidates: list[Path] = []
        if explicit_path:
            candidates.append(explicit_path)
        elif resolve_point_table_path is not None:
            try:
                candidates.append(resolve_point_table_path("catl_v22_bms"))
            except Exception:
                pass
        for path in candidates:
            try:
                if path and Path(path).exists():
                    return PointTable(path)
            except Exception:
                continue
        return None


    def _load_mapping_index(self) -> dict[str, dict[str, Any]]:
        """Load CAN Message::Signal -> Modbus/point-table metadata.

        This is intentionally optional. Diagnosis should still work without it,
        but when available it becomes the highest-priority truth source for
        range/span checks.
        """
        path = Path(__file__).resolve().parent / "protocols" / "catl_v22_can_modbus_mapping.json"
        out: dict[str, dict[str, Any]] = {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            rows = data.get("mappings", []) if isinstance(data, dict) else []
            for row in rows:
                msg = str(row.get("can_message") or "").strip()
                sig = str(row.get("can_signal") or "").strip()
                if msg and sig:
                    out[f"{msg}::{sig}"] = row
                    out.setdefault(sig, row)
        except Exception:
            pass
        return out

    def _load_semantic_index(self) -> dict[str, dict[str, Any]]:
        path = Path(__file__).resolve().parent / "protocols" / "catl_mbd4_18_runtime_semantic_lookup_v2.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            merged: dict[str, dict[str, Any]] = {}
            for k, v in (data.get("by_message_signal", {}) or {}).items():
                if isinstance(v, dict):
                    merged[k] = v
            for k, v in (data.get("by_signal", {}) or {}).items():
                if isinstance(v, dict):
                    merged.setdefault(k, v)
            return merged
        except Exception:
            return {}

    def _meta_for_signal(self, key: str) -> dict[str, Any]:
        sig = key.split("::")[-1]
        meta: dict[str, Any] = {}
        sem = self.semantic_by_key.get(key) or self.semantic_by_key.get(sig) or {}
        if isinstance(sem, dict):
            meta.update(sem)
        mp = self.mapping_by_key.get(key) or self.mapping_by_key.get(sig) or {}
        if isinstance(mp, dict):
            meta.update({f"mapping_{k}": v for k, v in mp.items()})
            # Promote common mapping fields for easier use.
            for k in ["modbus_actual_span", "modbus_address", "modbus_description", "modbus_key", "modbus_access", "modbus_section"]:
                if k in mp:
                    meta[k] = mp[k]
        return meta

    def _parse_span(self, text: Any) -> Optional[tuple[float, float]]:
        """Parse point-table spans such as '0~1500V', '-50~205℃', '0-255'."""
        if text is None:
            return None
        s = str(text).strip()
        if not s or s.upper() in {"NA", "N/A", "NONE", "NULL"}:
            return None
        # Normalize visually similar separators.
        s = s.replace("～", "~").replace("–", "-").replace("—", "-")
        # Prefer explicit ranges. Avoid interpreting leading minus as separator.
        m = re.search(r"(-?\d+(?:\.\d+)?)\s*(?:~|至|to|\.\.)\s*(-?\d+(?:\.\d+)?)", s, flags=re.I)
        if not m:
            m = re.search(r"(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)", s)
        if m:
            a, b = float(m.group(1)), float(m.group(2))
            if a > b:
                a, b = b, a
            return a, b
        return None

    def _signal_category(self, key: str, meta: dict[str, Any]) -> str:
        sig = key.split("::")[-1]
        text = " ".join(str(meta.get(k, "")) for k in [
            "chinese_name", "english_name", "ems_name", "ems_meaning", "modbus_description", "unit", "dbc_unit"
        ]) + " " + sig
        low = text.lower()
        # Position/index must win over temperature because names like
        # 'max temperature cell position' contain both concepts.
        if any(x in text for x in ["位置", "编号", "序号", "节号", "簇号"]) or any(x in low for x in ["pst", "pos", "position", "index", "number", "no.", "cell no"]):
            return "position"
        if any(x in text for x in ["状态", "模式", "命令", "使能", "告警", "故障"]) or any(x in low for x in ["status", "state", "mode", "cmd", "command", "enable", "fault", "alarm"]):
            return "status"
        if any(x in text for x in ["温度"]) or any(x in low for x in ["temperature", "temp"]):
            return "temperature"
        if any(x in text for x in ["电压"]) or any(x in low for x in ["voltage", "volt", "vol", "u_hvs", "u_tot"]):
            return "voltage"
        if any(x in text for x in ["电流"]) or any(x in low for x in ["current", "curr", "_i", "amp"]):
            return "current"
        if "soc" in low or "soh" in low or "soe" in low:
            return "soc"
        return "generic"

    def _first_outside_span(self, pts: Sequence[tuple[float, float]], span: tuple[float, float]) -> Optional[tuple[float, float]]:
        lo, hi = span
        for t, v in pts:
            if v < lo or v > hi:
                return t, v
        return None

    def _issue(self, severity: str, layer: str, time: str, obj: str, rule_id: str,
               description: str, evidence: str, suggestion: str, **refs: Any) -> DiagnosisIssue:
        return DiagnosisIssue(severity, layer, time, obj, rule_id, description, evidence, suggestion, refs={k: v for k, v in refs.items() if v not in (None, "", [], {})})

    def _attach_raw_refs(self, issues: list[DiagnosisIssue], modbus_records: list[Any], can_records: list[Any], joint_rows: list[dict[str, Any]]) -> None:
        """Best-effort reverse links from an issue to original table rows.

        The UI uses these refs to highlight the source packets/frames when an
        issue is selected. This deliberately stays fuzzy because some rules are
        aggregate-level rather than single-frame issues.
        """
        modbus_by_addr: dict[int, list[int]] = {}
        for r in modbus_records:
            addr = self._parse_addr(getattr(r, "address", ""))
            if addr is not None:
                modbus_by_addr.setdefault(addr, []).append(int(getattr(r, "index", -1)))
        can_by_id: dict[str, list[int]] = {}
        can_by_signal: dict[str, list[int]] = {}
        can_by_message_signal: dict[str, list[int]] = {}
        for r in can_records:
            idx = int(getattr(r, "index", -1))
            cid = str(getattr(r, "can_id", "")).upper()
            msg = str(getattr(r, "message_name", ""))
            dec = str(getattr(r, "decoded", ""))
            if cid:
                can_by_id.setdefault(cid, []).append(idx)
            for m in re.finditer(r"([A-Za-z0-9_]+)\s*=", dec):
                sig = m.group(1)
                can_by_signal.setdefault(sig, []).append(idx)
                if msg:
                    can_by_message_signal.setdefault(f"{msg}::{sig}", []).append(idx)
        for issue in issues:
            refs = dict(getattr(issue, "refs", {}) or {})
            obj = issue.obj
            if "can_indexes" not in refs:
                if obj in can_by_message_signal:
                    refs["can_indexes"] = can_by_message_signal[obj][:50]
                else:
                    sig = obj.split("::")[-1]
                    if sig in can_by_signal:
                        refs["can_indexes"] = can_by_signal[sig][:50]
                    elif obj.upper() in can_by_id:
                        refs["can_indexes"] = can_by_id[obj.upper()][:50]
            if "modbus_indexes" not in refs:
                # Address can be in obj or evidence.
                addr = self._parse_addr(obj) or self._parse_addr(issue.evidence)
                if addr is not None and addr in modbus_by_addr:
                    refs["modbus_indexes"] = modbus_by_addr[addr][:50]
            issue.refs = refs

    def _check_modbus(self, records: list[Any]) -> list[DiagnosisIssue]:
        issues: list[DiagnosisIssue] = []
        if not records:
            return [DiagnosisIssue(
                "Info", "Communication", "-", "Modbus", "modbus_no_packets",
                "No Modbus TCP packets were parsed.",
                "The capture may not contain TCP/502 traffic, may use a non-standard port, or may not be loaded.",
                "Confirm the capture point, TCP port 502, IP pair, and whether the file is pcap/pcapng from Wireshark.",
            )]

        reqs = [r for r in records if getattr(r, "direction", "") == "Request"]
        resps = [r for r in records if getattr(r, "direction", "") == "Response"]
        timeouts = [r for r in records if getattr(r, "status", "") == "Timeout"]
        exceptions = [r for r in records if getattr(r, "status", "") == "Exception"]
        if reqs and not resps:
            issues.append(DiagnosisIssue(
                "Critical", "Communication", self._time(reqs[0]), "Modbus", "modbus_requests_no_responses",
                "The capture contains Modbus requests but no responses.",
                f"requests={len(reqs)}, responses=0",
                "Check BMS/gateway IP, TCP 502 reachability, unit id, firewall, wrong capture direction, and whether the server replied on another interface.",
            ))
        if timeouts:
            issues.append(DiagnosisIssue(
                "Critical" if len(timeouts) >= 3 else "Warning", "Communication", self._time(timeouts[0]), "Modbus", "modbus_timeout",
                "One or more Modbus requests did not receive a response within the configured timeout.",
                f"timeouts={len(timeouts)}",
                "Check network loss, device CPU load, unsupported register range, polling too fast, or timeout setting too short.",
            ))
        if exceptions:
            codes = sorted({str(getattr(r, "exception_code", "")) for r in exceptions if getattr(r, "exception_code", "")})
            issues.append(DiagnosisIssue(
                "Warning", "Protocol", self._time(exceptions[0]), "Modbus", "modbus_exception",
                "Modbus exception responses were detected.",
                f"exceptions={len(exceptions)}, codes={','.join(codes) or '-'}",
                "Check illegal function code, illegal register address, illegal value, read/write permission, and current BMS state.",
            ))

        latencies: list[float] = []
        for r in records:
            try:
                if getattr(r, "latency_ms", ""):
                    latencies.append(float(getattr(r, "latency_ms")))
            except Exception:
                pass
        if latencies:
            avg = sum(latencies) / len(latencies)
            max_v = max(latencies)
            if max_v >= 1000 or avg >= 300:
                issues.append(DiagnosisIssue(
                    "Warning", "Communication", "-", "Modbus", "modbus_high_latency",
                    "Modbus response latency is high.",
                    f"avg={avg:.1f}ms, max={max_v:.1f}ms, samples={len(latencies)}",
                    "Check polling interval, network switch load, BMS/gateway CPU load, and TCP retransmissions.",
                ))

        # Register definition and permission checks.
        if self.point_table is not None:
            for r in records[:50000]:
                addr = self._parse_addr(getattr(r, "address", ""))
                if addr is None:
                    continue
                p = self.point_table.get_by_address(addr)
                fc = self._safe_int(getattr(r, "function_code", None))
                direction = getattr(r, "direction", "")
                if p is None:
                    if direction == "Request":
                        issues.append(DiagnosisIssue(
                            "Warning", "Protocol", self._time(r), f"0x{addr:04X}", "modbus_address_unknown",
                            "A requested register is not present in the loaded V22 point table.",
                            f"FC={fc}, address=0x{addr:04X}",
                            "Check whether the project uses a different point table version, an offset base, or a vendor-specific extension.",
                        ))
                        break
                    continue
                access = (p.access or "").upper()
                if direction == "Request" and fc in (5, 6, 15, 16) and "W" not in access:
                    issues.append(DiagnosisIssue(
                        "Critical", "Protocol", self._time(r), f"0x{addr:04X}", "modbus_write_read_only",
                        "A Modbus write targets a register marked read-only in the V22 point table.",
                        f"FC={fc}, address=0x{addr:04X}, point={p.description}, access={p.access}",
                        "Verify the address, function code, and whether the command should use EMS control registers such as 0x0380~0x0396.",
                    ))
                    break

        return self._dedupe(issues, limit_per_rule=5)

    def _check_can(self, records: list[Any], stats: list[Any], anomalies: list[dict[str, Any]]) -> list[DiagnosisIssue]:
        issues: list[DiagnosisIssue] = []
        if not records:
            return [DiagnosisIssue(
                "Info", "Communication", "-", "CAN", "can_no_frames",
                "No CAN frames were loaded for diagnosis.",
                "CAN log is empty or not loaded.",
                "Load an ASC/TRC/CSV/SocketCAN capture and select the correct DBC.",
            )]

        total = len(records)
        decoded = sum(1 for r in records if getattr(r, "decoded", ""))
        messaged = sum(1 for r in records if getattr(r, "message_name", ""))
        if total and messaged / total < 0.2:
            issues.append(DiagnosisIssue(
                "Warning", "Protocol", "-", "DBC", "can_low_dbc_coverage",
                "DBC coverage appears low for this CAN log.",
                f"message matched={messaged}/{total}, decoded={decoded}/{total}",
                "Check whether the DBC version matches the capture, whether extended-ID normalization is correct, and whether this is the expected CAN bus.",
            ))
        if total and decoded == 0:
            issues.append(DiagnosisIssue(
                "Critical", "Protocol", "-", "DBC", "can_no_decoded_signals",
                "No CAN signals were decoded from the loaded log.",
                f"frames={total}, ids={len(stats)}",
                "Select the correct DBC/mapping and confirm the captured IDs exist in the DBC.",
            ))

        # Unknown frequent IDs are usually version/bus mismatch or missing DBC pages.
        unknown_by_id: dict[str, int] = {}
        for r in records:
            if not getattr(r, "message_name", ""):
                unknown_by_id[getattr(r, "can_id", "-")] = unknown_by_id.get(getattr(r, "can_id", "-"), 0) + 1
        if unknown_by_id:
            top = sorted(unknown_by_id.items(), key=lambda kv: -kv[1])[:5]
            if sum(v for _, v in top) >= max(50, total * 0.05):
                issues.append(DiagnosisIssue(
                    "Warning", "Protocol", "-", "CAN", "can_unknown_frequent_ids",
                    "Frequent CAN IDs are not defined in the selected DBC.",
                    ", ".join(f"{cid}:{cnt}" for cid, cnt in top),
                    "Confirm DBC version, CAN channel, and whether these IDs belong to another device or protocol revision.",
                ))

        for a in anomalies[:80]:
            typ = str(a.get("type", "CAN anomaly"))
            severity = "Warning" if typ in {"Period Gap", "DLC Change"} else "Info"
            issues.append(DiagnosisIssue(
                severity, "Communication", str(a.get("time", "-")), str(a.get("can_id", "CAN")), f"can_{typ.lower().replace(' ', '_')}",
                typ,
                str(a.get("value", "-")),
                str(a.get("detail", "Check the CAN log around this timestamp.")),
            ))

        # Period sanity from stats.
        for s in stats[:2000]:
            try:
                avg_ms = float(getattr(s, "avg_period_ms", "nan"))
            except Exception:
                continue
            if math.isfinite(avg_ms) and avg_ms > 2000 and getattr(s, "count", 0) >= 3:
                issues.append(DiagnosisIssue(
                    "Info", "Communication", "-", getattr(s, "can_id", "CAN"), "can_slow_period",
                    "A CAN message has a slow average period.",
                    f"message={getattr(s, 'message_name', '')}, avg_period={avg_ms:.1f}ms, count={getattr(s, 'count', '-')}",
                    "Confirm whether this signal is event-driven/low-rate. If it should be cyclic, check BMS or bus load.",
                ))
                if len([i for i in issues if i.rule_id == "can_slow_period"]) >= 5:
                    break

        return self._dedupe(issues, limit_per_rule=10)

    def _check_mapping(self, modbus_records: list[Any], can_records: list[Any], joint_rows: list[dict[str, Any]]) -> list[DiagnosisIssue]:
        issues: list[DiagnosisIssue] = []
        if modbus_records and can_records and not joint_rows:
            issues.append(DiagnosisIssue(
                "Warning", "Mapping", "-", "CAN↔Modbus", "joint_no_correlated_rows",
                "CAN and Modbus files were loaded but no correlated rows were found.",
                "No mapped signal/register pair matched within the selected tolerance.",
                "Check whether the files are from the same project/time, time bases overlap, Modbus responses contain values, and mapping addresses match MBMU/SBMU level.",
            ))
            return issues
        if not joint_rows:
            return issues

        diffs: list[float] = []
        bad_rows: list[dict[str, Any]] = []
        for r in joint_rows:
            try:
                diff = float(r.get("abs_diff"))
                cv = abs(float(r.get("can_value")))
                mv = abs(float(r.get("modbus_value")))
            except Exception:
                continue
            diffs.append(diff)
            base = max(cv, mv, 1.0)
            if diff / base > 0.05 and diff > 1.0:
                bad_rows.append(r)
        if bad_rows:
            r = bad_rows[0]
            issues.append(DiagnosisIssue(
                "Warning", "Mapping", f"{r.get('time_can', '-')}", str(r.get("can_signal", "-")), "joint_value_mismatch",
                "CAN value and Modbus value differ beyond the default tolerance.",
                f"CAN={r.get('can_value')} Modbus={r.get('modbus_value')} diff={r.get('abs_diff')} addr={r.get('modbus_address')}",
                "Check scaling factor, offset, signed/unsigned interpretation, byte order, and whether the mapped register is the correct MBMU/SBMU object.",
            ))
        deltas: list[float] = []
        for r in joint_rows:
            try:
                deltas.append(abs(float(r.get("delta_s", 0))))
            except Exception:
                pass
        if deltas and max(deltas) > 1.0:
            issues.append(DiagnosisIssue(
                "Info", "Mapping", "-", "CAN↔Modbus", "joint_high_time_delta",
                "Some correlated CAN/Modbus samples have large time offset.",
                f"max_delta={max(deltas):.3f}s avg_delta={sum(deltas)/len(deltas):.3f}s",
                "Check gateway refresh cycle, logger clock base, and joint-analysis time tolerance.",
            ))
        if diffs:
            avg = sum(diffs) / len(diffs)
            issues.append(DiagnosisIssue(
                "Info", "Mapping", "-", "CAN↔Modbus", "joint_summary",
                "Joint-analysis numeric comparison summary.",
                f"rows={len(joint_rows)}, avg_abs_diff={avg:.4g}, max_abs_diff={max(diffs):.4g}",
                "Use the largest-difference rows to verify scaling and address mapping first.",
            ))
        return issues

    def _check_business_signals(self, buffers: Dict[str, Sequence[tuple[float, float]]]) -> list[DiagnosisIssue]:
        """Value/logic checks driven by point-table span and MBD semantics.

        Priority:
        1) If the signal maps to a Modbus/ToEMS point and that point has an
           Actual Span, use that span as the truth source.
        2) If no span exists, classify by MBD Chinese/English names.
        3) Only then fall back to conservative keyword checks.
        """
        issues: list[DiagnosisIssue] = []
        if not buffers:
            return issues

        for key, points in list(buffers.items())[:20000]:
            pts = [(float(t), float(v)) for t, v in (points or []) if self._is_number(v)]
            if len(pts) < 3:
                continue
            vals = [v for _, v in pts]
            min_v, max_v = min(vals), max(vals)
            value_span = max_v - min_v
            duration = pts[-1][0] - pts[0][0]
            sig = key.split("::")[-1]
            meta = self._meta_for_signal(key)
            category = self._signal_category(key, meta)

            # 1. Point table / mapping span has highest priority.
            span_text = meta.get("modbus_actual_span") or meta.get("actual_span")
            span = self._parse_span(span_text)
            if span is not None:
                outside = self._first_outside_span(pts, span)
                if outside is not None:
                    t, v = outside
                    addr = meta.get("modbus_address") or meta.get("ems_address") or "-"
                    desc = meta.get("modbus_description") or meta.get("ems_name") or meta.get("chinese_name") or sig
                    issues.append(DiagnosisIssue(
                        "Warning", "Business", f"{t:.3f}", key, "value_outside_point_span",
                        "Signal value is outside the mapped point-table Actual Span.",
                        f"value={v:g}, observed_min={min_v:g}, observed_max={max_v:g}, span={span_text}, addr={addr}, point={desc}",
                        "Use the point-table span as the primary validity check. If this is expected, verify protocol version and mapping address; otherwise inspect the highlighted raw CAN frames.",
                        refs={"signal_key": key, "modbus_address": addr},
                    ))
                # If span exists and all values are valid, do not run broad
                # type-based range checks that can cause false positives.
            else:
                # 2. Semantic/category fallback only when no authoritative span exists.
                if category == "soc":
                    if min_v < -1 or max_v > 101:
                        issues.append(DiagnosisIssue(
                            "Warning", "Business", "-", key, "soc_out_of_range",
                            "SOC-like signal is outside the expected 0~100% range.",
                            f"min={min_v:g}, max={max_v:g}",
                            "No mapped point-table span was found. Check MBD semantics, scaling, offset, signedness, and whether this signal is actually SOC/SOH/SOE.",
                            refs={"signal_key": key},
                        ))
                elif category == "temperature":
                    if min_v < -60 or max_v > 220:
                        issues.append(DiagnosisIssue(
                            "Warning", "Business", "-", key, "temperature_out_of_range",
                            "Temperature-like signal is outside conservative BMS temperature range.",
                            f"min={min_v:g}, max={max_v:g}",
                            "No mapped point-table span was found. Check MBD Chinese/English name, offset, unit, and whether this is a temperature value rather than a position/index signal.",
                            refs={"signal_key": key},
                        ))
                elif category == "voltage":
                    if min_v < -10 or max_v > 10000:
                        issues.append(DiagnosisIssue(
                            "Warning", "Business", "-", key, "voltage_out_of_plausible_range",
                            "Voltage-like signal has implausible values.",
                            f"min={min_v:g}, max={max_v:g}",
                            "No mapped point-table span was found. Check scale/unit: system voltage often uses V; cell voltage often uses mV.",
                            refs={"signal_key": key},
                        ))
                elif category == "position":
                    # Position/index signals are not physical values. Only warn
                    # on common invalid sentinels when we cannot find a span.
                    if any(v in (0xFF, 0xFFFF) for v in vals):
                        issues.append(DiagnosisIssue(
                            "Info", "Business", "-", key, "position_invalid_or_reserved_value",
                            "Position/index signal contains a common invalid/reserved sentinel.",
                            f"min={min_v:g}, max={max_v:g}, sentinel=255/65535 possible",
                            "This is often normal when BMS has not located the object yet. Verify corresponding value signal and point-table span before treating it as a fault.",
                            refs={"signal_key": key},
                        ))

            # Generic checks that are safe regardless of value type.
            if duration >= 60 and value_span == 0 and category in {"soc", "voltage", "current", "temperature"}:
                issues.append(DiagnosisIssue(
                    "Info", "Business", f"{pts[0][0]:.3f}", key, "signal_stale",
                    "A decoded battery signal stayed completely unchanged for a long period.",
                    f"duration={duration:.1f}s, value={vals[0]:g}, category={category}",
                    "This can be normal for status bits, but for changing analog values it may indicate stale gateway data, frozen BMS data, or wrong mapping.",
                    refs={"signal_key": key},
                ))

            # SOC jump is still useful, but only for semantic SOC signals.
            if category == "soc" and len(vals) >= 2:
                max_jump = max(abs(vals[i] - vals[i-1]) for i in range(1, len(vals)))
                if max_jump > 5:
                    issues.append(DiagnosisIssue(
                        "Warning", "Business", "-", key, "soc_jump",
                        "SOC/SOH/SOE-like signal has a large step change between consecutive samples.",
                        f"max_jump={max_jump:g}%",
                        "Check sampling gaps, BMS recalibration, or signal/register mapping.",
                        refs={"signal_key": key},
                    ))
        return self._dedupe(issues, limit_per_rule=20)


    # =====================
    # Engineering fault-template library
    # =====================
    def _check_fault_templates(
        self,
        modbus_records: list[Any],
        can_records: list[Any],
        buffers: Dict[str, Sequence[tuple[float, float]]],
        joint_rows: list[dict[str, Any]],
    ) -> list[DiagnosisIssue]:
        """Match common field-debugging problem templates.

        These templates are intentionally higher-level than single span/value
        checks. They look for patterns engineers often meet during BMS/EMS
        commissioning and return a suggested troubleshooting path.
        """
        issues: list[DiagnosisIssue] = []
        numeric_buffers = self._numeric_buffers(buffers)
        if not numeric_buffers:
            return issues

        categorized = self._categorized_signal_buffers(numeric_buffers)
        issues.extend(self._template_soc_stale_under_current(categorized))
        issues.extend(self._template_soc_direction_vs_current(categorized))
        issues.extend(self._template_voltage_current_event(categorized))
        issues.extend(self._template_invalid_sentinel_clusters(categorized))
        issues.extend(self._template_fault_or_alarm_active(categorized))
        issues.extend(self._template_control_write_no_followup(modbus_records, categorized))
        issues.extend(self._template_joint_scaling_offset(joint_rows))
        return self._dedupe(issues, limit_per_rule=6)

    def _numeric_buffers(self, buffers: Dict[str, Sequence[tuple[float, float]]]) -> dict[str, list[tuple[float, float]]]:
        out: dict[str, list[tuple[float, float]]] = {}
        for key, pts in (buffers or {}).items():
            arr: list[tuple[float, float]] = []
            for t, v in pts or []:
                if self._is_number(v):
                    try:
                        arr.append((float(t), float(v)))
                    except Exception:
                        pass
            if len(arr) >= 3:
                arr.sort(key=lambda x: x[0])
                out[key] = arr
        return out

    def _categorized_signal_buffers(self, buffers: dict[str, list[tuple[float, float]]]) -> dict[str, list[tuple[str, list[tuple[float, float]], dict[str, Any]]]]:
        out: dict[str, list[tuple[str, list[tuple[float, float]], dict[str, Any]]]] = {}
        for key, pts in buffers.items():
            meta = self._meta_for_signal(key)
            cat = self._signal_category(key, meta)
            out.setdefault(cat, []).append((key, pts, meta))
        return out

    def _series_span(self, pts: Sequence[tuple[float, float]]) -> tuple[float, float, float, float]:
        vals = [v for _, v in pts]
        return min(vals), max(vals), vals[0], vals[-1]

    def _median_abs(self, pts: Sequence[tuple[float, float]]) -> float:
        vals = sorted(abs(v) for _, v in pts if math.isfinite(float(v)))
        if not vals:
            return 0.0
        mid = len(vals) // 2
        return vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2

    def _slope(self, pts: Sequence[tuple[float, float]]) -> float:
        if len(pts) < 2:
            return 0.0
        dt = pts[-1][0] - pts[0][0]
        if abs(dt) < 1e-9:
            return 0.0
        return (pts[-1][1] - pts[0][1]) / dt

    def _label_for_key(self, key: str, meta: dict[str, Any]) -> str:
        return str(meta.get("chinese_name") or meta.get("english_name") or meta.get("modbus_description") or key)

    def _template_soc_stale_under_current(self, categorized: dict[str, list[tuple[str, list[tuple[float, float]], dict[str, Any]]]]) -> list[DiagnosisIssue]:
        issues: list[DiagnosisIssue] = []
        socs = categorized.get("soc", [])
        currents = categorized.get("current", [])
        if not socs or not currents:
            return issues
        active_current = []
        for key, pts, meta in currents[:20]:
            if self._median_abs(pts) >= 5:
                active_current.append((key, pts, meta))
        if not active_current:
            return issues
        for skey, spts, smeta in socs[:20]:
            smin, smax, s0, s1 = self._series_span(spts)
            duration = spts[-1][0] - spts[0][0]
            if duration >= 120 and (smax - smin) <= 0.05:
                ckey, cpts, cmeta = active_current[0]
                issues.append(DiagnosisIssue(
                    "Warning", "Fault Template", f"{spts[0][0]:.3f}", skey, "template_soc_stale_with_current",
                    "SOC/SOH/SOE remains unchanged while battery current appears active.",
                    f"soc_span={smax-smin:.4g}% over {duration:.1f}s; current_median_abs={self._median_abs(cpts):.3g}; current_signal={ckey}",
                    "常见原因：SOC计算未刷新、网关缓存未更新、CAN→Modbus映射错、采样窗口不是同一测试段。排查：先看CAN SOC原始曲线，再看Modbus SOC，再确认电流方向和网关刷新周期。",
                    refs={"signal_key": skey},
                ))
                break
        return issues

    def _template_soc_direction_vs_current(self, categorized: dict[str, list[tuple[str, list[tuple[float, float]], dict[str, Any]]]]) -> list[DiagnosisIssue]:
        issues: list[DiagnosisIssue] = []
        socs = categorized.get("soc", [])
        currents = categorized.get("current", [])
        if not socs or not currents:
            return issues
        # This is deliberately Info because projects disagree on current sign.
        for skey, spts, smeta in socs[:10]:
            smin, smax, s0, s1 = self._series_span(spts)
            if abs(s1 - s0) < 0.2:
                continue
            for ckey, cpts, cmeta in currents[:10]:
                med = self._median_abs(cpts)
                if med < 5:
                    continue
                cavg = sum(v for _, v in cpts) / len(cpts)
                issues.append(DiagnosisIssue(
                    "Info", "Fault Template", "-", f"{skey} ↔ {ckey}", "template_soc_current_direction_check",
                    "SOC changes while current is active; verify the project's charge/discharge sign convention.",
                    f"soc_delta={s1-s0:.3g}%, current_avg={cavg:.3g}, current_median_abs={med:.3g}",
                    "工程上常见问题：充放电电流符号约定与EMS/PCS相反，导致策略判断反。确认项目定义：充电为正还是放电为正，并与Modbus点表offset/signedness一起检查。",
                    refs={"signal_key": skey},
                ))
                return issues
        return issues

    def _template_voltage_current_event(self, categorized: dict[str, list[tuple[str, list[tuple[float, float]], dict[str, Any]]]]) -> list[DiagnosisIssue]:
        issues: list[DiagnosisIssue] = []
        voltages = categorized.get("voltage", [])
        currents = categorized.get("current", [])
        if not voltages or not currents:
            return issues
        for vkey, vpts, vmeta in voltages[:20]:
            vmin, vmax, v0, v1 = self._series_span(vpts)
            # Avoid cell mV signals causing false reports; focus on system/rack voltage-like signals.
            label = self._label_for_key(vkey, vmeta).lower()
            if (vmax - vmin) < 10:
                continue
            for ckey, cpts, cmeta in currents[:20]:
                cmin, cmax, c0, c1 = self._series_span(cpts)
                if (cmax - cmin) < 20:
                    continue
                issues.append(DiagnosisIssue(
                    "Info", "Fault Template", "-", f"{vkey} ↔ {ckey}", "template_voltage_current_transient",
                    "Voltage and current both show significant movement in the capture window.",
                    f"voltage_span={vmax-vmin:.3g}, current_span={cmax-cmin:.3g}",
                    "这通常对应充放电、合闸、预充或负载变化。若伴随告警/状态跳变，请重点回看该时间段前后5秒的控制命令、接触器状态、母线电压和电流方向。",
                    refs={"signal_key": vkey},
                ))
                return issues
        return issues

    def _template_invalid_sentinel_clusters(self, categorized: dict[str, list[tuple[str, list[tuple[float, float]], dict[str, Any]]]]) -> list[DiagnosisIssue]:
        issues: list[DiagnosisIssue] = []
        for cat in ("temperature", "position", "voltage", "current", "soc"):
            for key, pts, meta in categorized.get(cat, [])[:100]:
                vals = [v for _, v in pts]
                sentinel_count = sum(1 for v in vals if v in (255, 65535, -1))
                if sentinel_count >= max(3, len(vals) * 0.2):
                    issues.append(DiagnosisIssue(
                        "Info" if cat == "position" else "Warning", "Fault Template", f"{pts[0][0]:.3f}", key, "template_invalid_sentinel_repeated",
                        "Signal repeatedly contains common invalid/reserved sentinel values.",
                        f"category={cat}, sentinel_samples={sentinel_count}/{len(vals)}, values include 255/65535/-1",
                        "常见原因：传感器未接入、通道无效、BMS尚未定位对象、该版本协议保留值。先结合中文/英文名称和点表span判断是否允许，再看对应真实值信号是否有效。",
                        refs={"signal_key": key},
                    ))
                    if len(issues) >= 5:
                        return issues
        return issues

    def _template_fault_or_alarm_active(self, categorized: dict[str, list[tuple[str, list[tuple[float, float]], dict[str, Any]]]]) -> list[DiagnosisIssue]:
        issues: list[DiagnosisIssue] = []
        # Signals categorized as status/fault/alarm with non-zero values for a sustained period.
        for key, pts, meta in categorized.get("status", [])[:200]:
            label = (key + " " + self._label_for_key(key, meta)).lower()
            if not any(x in label for x in ["fault", "alarm", "warning", "告警", "故障", "保护"]):
                continue
            vals = [v for _, v in pts]
            nz = sum(1 for v in vals if abs(v) > 1e-9)
            if nz >= max(3, len(vals) * 0.5):
                issues.append(DiagnosisIssue(
                    "Warning", "Fault Template", f"{pts[0][0]:.3f}", key, "template_fault_alarm_active",
                    "Fault/alarm-like signal is active for much of the capture.",
                    f"active_samples={nz}/{len(vals)}, min={min(vals):g}, max={max(vals):g}",
                    "排查顺序：先确认该信号是否为bit位/页码/编号而非故障值；再查MBD/故障表中文描述；最后回看故障出现前的电压、电流、温度和控制命令。",
                    refs={"signal_key": key},
                ))
                if len(issues) >= 5:
                    break
        return issues

    def _template_control_write_no_followup(self, modbus_records: list[Any], categorized: dict[str, list[tuple[str, list[tuple[float, float]], dict[str, Any]]]]) -> list[DiagnosisIssue]:
        issues: list[DiagnosisIssue] = []
        if not modbus_records:
            return issues
        writes = []
        for r in modbus_records[:100000]:
            fc = self._safe_int(getattr(r, "function_code", None))
            direction = str(getattr(r, "direction", ""))
            addr = self._parse_addr(getattr(r, "address", ""))
            if direction == "Request" and fc in (5, 6, 15, 16) and addr is not None:
                writes.append((r, addr))
        if not writes:
            return issues
        # Control area from CATL EMS messages is around 0x0380~0x0396.
        control_writes = [(r, a) for r, a in writes if 0x0380 <= a <= 0x0396]
        if not control_writes:
            return issues
        status_like = categorized.get("status", []) + categorized.get("voltage", []) + categorized.get("current", [])
        if not status_like:
            issues.append(DiagnosisIssue(
                "Info", "Fault Template", self._time(control_writes[0][0]), f"0x{control_writes[0][1]:04X}", "template_control_write_without_can_context",
                "EMS control-register write was detected, but no decoded CAN/status signals are loaded for follow-up verification.",
                f"control_writes={len(control_writes)}, first_address=0x{control_writes[0][1]:04X}",
                "若要判断命令是否生效，需要同时加载同一时间段的CAN日志，并观察BMS high-voltage status、relay/precharge状态、系统电压/电流是否变化。",
                refs={"modbus_indexes": [int(getattr(control_writes[0][0], "index", -1))]},
            ))
            return issues
        r0, a0 = control_writes[0]
        t0 = float(getattr(r0, "timestamp", 0.0) or 0.0)
        changed = False
        for key, pts, meta in status_like[:80]:
            after = [(t, v) for t, v in pts if t0 <= t <= t0 + 5.0]
            before = [(t, v) for t, v in pts if t0 - 2.0 <= t < t0]
            if after and before:
                b = before[-1][1]
                if any(abs(v - b) > 1e-9 for _, v in after):
                    changed = True
                    break
        if not changed:
            issues.append(DiagnosisIssue(
                "Warning", "Fault Template", self._time(r0), f"0x{a0:04X}", "template_control_write_no_observed_effect",
                "Control-register write was detected, but no obvious status/voltage/current change followed in the decoded CAN window.",
                f"address=0x{a0:04X}, check_window=5s",
                "常见原因：命令未被网关转成CAN、BMS拒绝执行、前置条件不满足、CAN日志与Modbus抓包不同步。检查该写操作后的CAN控制帧、BMS状态机、故障状态和高压允许条件。",
                refs={"modbus_indexes": [int(getattr(r0, "index", -1))]},
            ))
        return issues

    def _template_joint_scaling_offset(self, joint_rows: list[dict[str, Any]]) -> list[DiagnosisIssue]:
        issues: list[DiagnosisIssue] = []
        if len(joint_rows) < 5:
            return issues
        ratios: list[float] = []
        diffs: list[float] = []
        for r in joint_rows:
            try:
                cv = float(r.get("can_value"))
                mv = float(r.get("modbus_value"))
            except Exception:
                continue
            if abs(cv) > 1e-9 and abs(mv) > 1e-9:
                ratios.append(mv / cv)
            diffs.append(mv - cv)
        if len(ratios) >= 5:
            avg_ratio = sum(ratios) / len(ratios)
            for expected in (0.01, 0.1, 10.0, 100.0):
                if abs(avg_ratio - expected) / expected < 0.08:
                    issues.append(DiagnosisIssue(
                        "Warning", "Fault Template", "-", "CAN↔Modbus", "template_likely_scaling_factor_error",
                        "Joint rows show a near-constant scaling ratio between CAN and Modbus values.",
                        f"avg_ratio={avg_ratio:.4g}, expected_like={expected:g}, samples={len(ratios)}",
                        "常见原因：factor重复应用或漏应用、Modbus raw值未换算、DBC和点表倍率不一致。检查CAN factor/offset、点表Ratio Factor、网关配置和UI显示层是否重复缩放。",
                    ))
                    break
        if len(diffs) >= 5:
            avg_diff = sum(diffs) / len(diffs)
            spread = max(diffs) - min(diffs)
            if abs(avg_diff) > 1 and spread < max(1.0, abs(avg_diff) * 0.1):
                issues.append(DiagnosisIssue(
                    "Info", "Fault Template", "-", "CAN↔Modbus", "template_likely_constant_offset",
                    "Joint rows show a near-constant offset between CAN and Modbus values.",
                    f"avg_offset={avg_diff:.4g}, spread={spread:.4g}, samples={len(diffs)}",
                    "常见原因：offset漏加/重复加、温度未减50、电流未减20000、符号/基准值处理不同。检查点表Offset和DBC offset。",
                ))
        return issues

    def _summary(self, issues: list[DiagnosisIssue], modbus_records: list[Any], can_records: list[Any], can_stats: list[Any], joint_rows: list[dict[str, Any]]) -> dict[str, Any]:
        counts: dict[str, int] = {"Critical": 0, "Warning": 0, "Info": 0, "OK": 0}
        by_layer: dict[str, int] = {}
        for i in issues:
            counts[i.severity] = counts.get(i.severity, 0) + 1
            by_layer[i.layer] = by_layer.get(i.layer, 0) + 1
        conclusions = [
            f"Loaded evidence: Modbus packets={len(modbus_records)}, CAN frames={len(can_records)}, CAN IDs={len(can_stats)}, joint rows={len(joint_rows)}.",
            f"Diagnosis issues: Critical={counts.get('Critical', 0)}, Warning={counts.get('Warning', 0)}, Info={counts.get('Info', 0)}.",
        ]
        if counts.get("Critical", 0):
            conclusions.append("Critical issues exist. Start from communication/protocol failures before interpreting values.")
        elif counts.get("Warning", 0):
            conclusions.append("No critical issue was detected, but warnings should be reviewed before trusting mapped values.")
        else:
            conclusions.append("No obvious issue was detected by the current rule set.")
        if any(i.rule_id == "joint_no_correlated_rows" for i in issues):
            conclusions.append("For joint analysis, use CAN and Modbus captures from the same device and overlapping time window, or configure a time offset/tolerance.")
        return {"counts": counts, "by_layer": by_layer, "conclusions": conclusions}

    def _dedupe(self, issues: list[DiagnosisIssue], limit_per_rule: int = 5) -> list[DiagnosisIssue]:
        out: list[DiagnosisIssue] = []
        count_by_rule: dict[str, int] = {}
        seen: set[tuple[str, str, str]] = set()
        for i in issues:
            key = (i.rule_id, i.obj, i.description)
            if key in seen:
                continue
            if count_by_rule.get(i.rule_id, 0) >= limit_per_rule:
                continue
            seen.add(key)
            count_by_rule[i.rule_id] = count_by_rule.get(i.rule_id, 0) + 1
            out.append(i)
        return out

    def _parse_addr(self, value: Any) -> Optional[int]:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        m = re.search(r"0x([0-9a-fA-F]+)", text)
        if m:
            return int(m.group(1), 16)
        try:
            return int(text, 0)
        except Exception:
            return None

    def _safe_int(self, value: Any) -> Optional[int]:
        try:
            return int(value)
        except Exception:
            return None

    def _time(self, rec: Any) -> str:
        try:
            return f"{float(getattr(rec, 'timestamp')):.6f}"
        except Exception:
            return "-"

    def _is_number(self, value: Any) -> bool:
        try:
            float(value)
            return True
        except Exception:
            return False

    def _md(self, text: str) -> str:
        return text.replace("|", "\\|").replace("\n", "<br>")
