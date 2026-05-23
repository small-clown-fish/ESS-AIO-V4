from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List
import csv
from pathlib import Path


@dataclass
class CommunicationIssue:
    issue_type: str
    key: str
    count: int
    value: str
    suggestion: str
    severity: str = "Info"

    def as_row(self) -> list[str]:
        return [self.issue_type, self.key, str(self.count), self.value, self.suggestion, self.severity]


class CommunicationAnalyzerPro:
    """Field-friendly Modbus communication diagnostics.

    This class is intentionally UI-agnostic so it can be reused by reports,
    future APIs, and automated tests.
    """

    def analyze_modbus(self, records: Iterable[Any]) -> Dict[str, Any]:
        records = list(records or [])
        requests = [r for r in records if getattr(r, "direction", "") == "Request"]
        responses = [r for r in records if getattr(r, "direction", "") == "Response"]
        timeouts = [r for r in records if getattr(r, "status", "") == "Timeout"]
        exceptions = [r for r in records if getattr(r, "status", "") == "Exception"]

        latencies: list[float] = []
        latency_by_key: dict[str, list[float]] = {}
        timeout_by_key: dict[str, int] = {}
        exception_by_key: dict[str, int] = {}
        retry_by_key: dict[str, int] = {}
        device_error_count: dict[str, int] = {}
        device_total_count: dict[str, int] = {}
        last_request_ts: dict[str, float] = {}

        for rec in records:
            unit = getattr(rec, "unit_id", "-")
            fc = getattr(rec, "function_code", "-")
            addr = getattr(rec, "address", "-") or "-"
            key = f"Unit {unit} FC{fc} {addr}"
            endpoint = f"{getattr(rec, 'src', '-')} -> {getattr(rec, 'dst', '-')} Unit {unit}"
            device_total_count[endpoint] = device_total_count.get(endpoint, 0) + 1

            status = getattr(rec, "status", "")
            if status in ["Timeout", "Exception"]:
                device_error_count[endpoint] = device_error_count.get(endpoint, 0) + 1

            if status == "Timeout":
                timeout_by_key[key] = timeout_by_key.get(key, 0) + 1

            if status == "Exception":
                base_fc = fc
                try:
                    base_fc = int(fc) & 0x7F
                except Exception:
                    pass
                ex_key = f"Unit {unit} FC{base_fc} exception={getattr(rec, 'exception_code', '') or '-'} {addr}"
                exception_by_key[ex_key] = exception_by_key.get(ex_key, 0) + 1

            try:
                latency_text = getattr(rec, "latency_ms", "")
                if latency_text:
                    latency = float(latency_text)
                    latencies.append(latency)
                    latency_by_key.setdefault(key, []).append(latency)
            except Exception:
                pass

            if getattr(rec, "direction", "") == "Request":
                req_key = (
                    f"{getattr(rec, 'src', '-')}->{getattr(rec, 'dst', '-')} "
                    f"Unit {unit} FC{fc} {addr} {getattr(rec, 'count_or_value', '') or '-'}"
                )
                prev = last_request_ts.get(req_key)
                try:
                    ts = float(getattr(rec, "timestamp", 0.0))
                    if prev is not None and ts - prev < 1.0:
                        retry_by_key[req_key] = retry_by_key.get(req_key, 0) + 1
                    last_request_ts[req_key] = ts
                except Exception:
                    pass

        latency_summary = self._latency_summary(latencies)
        issues: list[CommunicationIssue] = []

        for key, count in sorted(timeout_by_key.items(), key=lambda kv: -kv[1])[:10]:
            issues.append(CommunicationIssue(
                "Timeout", key, count, "-",
                "Check network loss, device response time, wrong register range, or timeout setting.",
                "Critical" if count >= 3 else "Warning",
            ))

        for key, count in sorted(exception_by_key.items(), key=lambda kv: -kv[1])[:10]:
            issues.append(CommunicationIssue(
                "Exception", key, count, "-",
                "Check function code, register address, access permission, or device state.",
                "Warning",
            ))

        slow_items = []
        for key, vals in latency_by_key.items():
            if vals:
                slow_items.append((key, len(vals), max(vals), sum(vals) / len(vals)))
        for key, count, worst, avg in sorted(slow_items, key=lambda x: -x[2])[:10]:
            if worst >= 500 or avg >= 200:
                severity = "Warning"
            else:
                severity = "Info"
            issues.append(CommunicationIssue(
                "Slow Response", key, count, f"max={worst:.2f}ms avg={avg:.2f}ms",
                "Check polling interval, device CPU load, Ethernet switch latency, or TCP congestion.",
                severity,
            ))

        for key, count in sorted(retry_by_key.items(), key=lambda kv: -kv[1])[:10]:
            issues.append(CommunicationIssue(
                "Possible Retry", key, count, "<1s repeat",
                "Repeated identical requests may indicate timeout/retry behavior or overly aggressive polling.",
                "Warning",
            ))

        for endpoint, total in sorted(device_total_count.items(), key=lambda kv: -kv[1])[:12]:
            errors = device_error_count.get(endpoint, 0)
            if total <= 0:
                continue
            rate = errors / total * 100.0
            if rate >= 5.0:
                issues.append(CommunicationIssue(
                    "High Error Rate", endpoint, errors, f"{rate:.1f}% of {total}",
                    "Communication path or target device may be unstable. Check cable, IP, timeout and polling load.",
                    "Critical" if rate >= 15.0 else "Warning",
                ))

        conclusions = self._build_conclusions(
            total=len(records), request_count=len(requests), response_count=len(responses),
            timeout_count=len(timeouts), exception_count=len(exceptions),
            latency_summary=latency_summary, issues=issues,
        )

        return {
            "total": len(records),
            "request_count": len(requests),
            "response_count": len(responses),
            "timeout_count": len(timeouts),
            "exception_count": len(exceptions),
            "error_rate": ((len(timeouts) + len(exceptions)) / len(records) * 100.0) if records else 0.0,
            "latency": latency_summary,
            "issues": issues,
            "conclusions": conclusions,
        }

    def export_issues_csv(self, analysis: Dict[str, Any], path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["type", "key", "count", "value", "suggestion", "severity"])
            for issue in analysis.get("issues", []):
                writer.writerow(issue.as_row() if hasattr(issue, "as_row") else issue)

    def _latency_summary(self, values: list[float]) -> Dict[str, Any]:
        if not values:
            return {"count": 0, "avg": None, "p50": None, "p90": None, "p95": None, "max": None}
        vals = sorted(values)
        return {
            "count": len(vals),
            "avg": sum(vals) / len(vals),
            "p50": self._percentile(vals, 50),
            "p90": self._percentile(vals, 90),
            "p95": self._percentile(vals, 95),
            "max": max(vals),
        }

    def _percentile(self, sorted_values: list[float], percentile: float) -> float:
        if not sorted_values:
            return 0.0
        if len(sorted_values) == 1:
            return sorted_values[0]
        pos = (len(sorted_values) - 1) * percentile / 100.0
        low = int(pos)
        high = min(low + 1, len(sorted_values) - 1)
        frac = pos - low
        return sorted_values[low] * (1.0 - frac) + sorted_values[high] * frac

    def _build_conclusions(
        self,
        total: int,
        request_count: int,
        response_count: int,
        timeout_count: int,
        exception_count: int,
        latency_summary: Dict[str, Any],
        issues: list[CommunicationIssue],
    ) -> list[str]:
        if total <= 0:
            return ["No Modbus TCP packets were parsed from the capture."]

        conclusions: list[str] = []
        error_rate = (timeout_count + exception_count) / total * 100.0
        max_latency = latency_summary.get("max")
        p90 = latency_summary.get("p90")

        conclusions.append(
            f"Parsed {total} Modbus packets: {request_count} requests, {response_count} responses."
        )
        conclusions.append(
            f"Communication error rate is {error_rate:.2f}% ({timeout_count} timeouts, {exception_count} exceptions)."
        )

        if timeout_count:
            conclusions.append("Timeouts were detected. Prioritize checking target responsiveness, polling interval, network loss and timeout setting.")
        if exception_count:
            conclusions.append("Modbus exceptions were detected. Check register address, function code, access permission and device state.")
        if max_latency is not None:
            conclusions.append(
                f"Latency summary: avg={latency_summary.get('avg', 0):.2f}ms, p50={latency_summary.get('p50', 0):.2f}ms, p90={p90:.2f}ms, max={max_latency:.2f}ms."
            )
            if max_latency >= 1000 or (p90 is not None and p90 >= 500):
                conclusions.append("Latency is high. This points to network congestion, overloaded device CPU, switch latency, or overly aggressive polling.")
        if not any(i.severity in ["Critical", "Warning"] for i in issues):
            conclusions.append("No obvious critical communication issue was found in the parsed traffic.")
        return conclusions
