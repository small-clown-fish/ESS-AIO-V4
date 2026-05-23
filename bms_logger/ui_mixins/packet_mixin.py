from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import csv
import re
import shutil

from PySide6.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem
from PySide6.QtGui import QColor

from bms_logger.packet_analyzer import PacketAnalyzer, ModbusPacketRecord
from bms_logger.communication_analyzer import CommunicationAnalyzerPro
from bms_logger.can_semantics import CanSemanticLookup
from bms_logger.packet_store import PacketSQLiteStore, cache_path_for, fingerprint


class PacketAnalyzerMixin:
    def load_packet_capture(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load packet capture",
            str(Path.cwd()),
            "Capture Files (*.pcap *.pcapng);;All Files (*)",
        )
        if not path:
            return
        self.packet_file_edit.setText(path)
        analyzer = PacketAnalyzer()
        cache_path = cache_path_for("modbus", path, profile_dir=getattr(self, "current_profile_dir", None))
        try:
            store = PacketSQLiteStore(cache_path)
            if store.has_kind("modbus", fingerprint(path) or {}):
                records = store.load_modbus()
                self.log(f"[PACKET] Loaded Modbus analysis from SQLite cache: {cache_path}")
            else:
                records = analyzer.analyze(path)
                store.save_modbus(path, records)
                self.log(f"[PACKET] Created SQLite cache: {cache_path}")
            store.close()
        except Exception as exc:
            QMessageBox.critical(self, "Packet Analyzer", f"Failed to analyze capture:\n{exc}")
            self.log(f"[ERROR] Packet analyze failed: {exc}")
            return
        self.packet_records: List[ModbusPacketRecord] = records
        self.packet_modbus_cache_path = str(cache_path)
        self.log(f"[PACKET] Loaded {path}, modbus_packets={len(records)}")
        self.refresh_packet_table()
        self.analyze_modbus_issues()

    def clear_packet_capture(self) -> None:
        """Clear only the loaded Modbus/Wireshark evidence."""
        self.packet_records = []
        self.packet_diagnosis_highlight_modbus = set()
        self.packet_diagnosis_highlight_modbus_severity = {}
        if hasattr(self, "packet_file_edit"):
            self.packet_file_edit.clear()
        if hasattr(self, "packet_issue_table"):
            self.packet_issue_table.setRowCount(0)
        if hasattr(self, "packet_diagnosis_text"):
            self.packet_diagnosis_text.clear()
        if hasattr(self, "packet_detail_text"):
            self.packet_detail_text.clear()
        self.refresh_packet_table()
        self.log("[PACKET] Cleared Modbus capture evidence")

    # =====================
    # Large packet table paging helpers
    # =====================
    def _parse_optional_float(self, widget_name: str):
        try:
            widget = getattr(self, widget_name, None)
            text = widget.text().strip() if widget is not None else ""
            return float(text) if text else None
        except Exception:
            return None

    def _page_size(self, widget_name: str, default: int = 2000) -> int:
        try:
            return int(getattr(self, widget_name).value())
        except Exception:
            return default

    def _page_number(self, widget_name: str) -> int:
        try:
            return max(1, int(getattr(self, widget_name).value()))
        except Exception:
            return 1

    def _set_page_controls(self, prefix: str, total: int, page_size: int, page: int) -> tuple[int, int, int]:
        pages = max(1, (int(total) + int(page_size) - 1) // int(page_size))
        page = min(max(1, int(page)), pages)
        spin = getattr(self, f"{prefix}_page_spin", None)
        if spin is not None:
            try:
                spin.blockSignals(True)
                spin.setRange(1, pages)
                spin.setValue(page)
                spin.blockSignals(False)
            except Exception:
                pass
        label = getattr(self, f"{prefix}_page_label", None)
        if label is not None:
            label.setText(f"Page {page} / {pages}")
        return page, pages, (page - 1) * page_size

    def apply_packet_table_filters(self) -> None:
        if hasattr(self, "packet_page_spin"):
            self.packet_page_spin.setValue(1)
        self.refresh_packet_table()

    def packet_first_page(self) -> None:
        if hasattr(self, "packet_page_spin"):
            self.packet_page_spin.setValue(1)
        self.refresh_packet_table()

    def packet_prev_page(self) -> None:
        if hasattr(self, "packet_page_spin"):
            self.packet_page_spin.setValue(max(1, self.packet_page_spin.value() - 1))
        self.refresh_packet_table()

    def packet_next_page(self) -> None:
        if hasattr(self, "packet_page_spin"):
            self.packet_page_spin.setValue(self.packet_page_spin.value() + 1)
        self.refresh_packet_table()

    def packet_last_page(self) -> None:
        if hasattr(self, "packet_page_spin"):
            self.packet_page_spin.setValue(self.packet_page_spin.maximum())
        self.refresh_packet_table()

    def apply_can_table_filters(self) -> None:
        if hasattr(self, "can_page_spin"):
            self.can_page_spin.setValue(1)
        self.refresh_can_table()

    def can_first_page(self) -> None:
        if hasattr(self, "can_page_spin"):
            self.can_page_spin.setValue(1)
        self.refresh_can_table()

    def can_prev_page(self) -> None:
        if hasattr(self, "can_page_spin"):
            self.can_page_spin.setValue(max(1, self.can_page_spin.value() - 1))
        self.refresh_can_table()

    def can_next_page(self) -> None:
        if hasattr(self, "can_page_spin"):
            self.can_page_spin.setValue(self.can_page_spin.value() + 1)
        self.refresh_can_table()

    def can_last_page(self) -> None:
        if hasattr(self, "can_page_spin"):
            self.can_page_spin.setValue(self.can_page_spin.maximum())
        self.refresh_can_table()

    def _load_modbus_page_from_cache(self):
        cache = getattr(self, "packet_modbus_cache_path", "")
        if not cache or not Path(cache).exists():
            return None
        store = PacketSQLiteStore(cache)
        try:
            text = self.packet_filter_edit.text().strip().lower() if hasattr(self, "packet_filter_edit") else ""
            addr = self.packet_addr_filter_edit.text().strip() if hasattr(self, "packet_addr_filter_edit") else ""
            tmin = self._parse_optional_float("packet_time_from_edit")
            tmax = self._parse_optional_float("packet_time_to_edit")
            page_size = self._page_size("packet_page_size_spin", 2000)
            page = self._page_number("packet_page_spin")
            desc = bool(getattr(self, "packet_desc_check", None) and self.packet_desc_check.isChecked())
            total = store.count_modbus_packets(text=text, address=addr, time_min=tmin, time_max=tmax)
            page, pages, offset = self._set_page_controls("packet", total, page_size, page)
            rows = store.query_modbus_packets(limit=page_size, offset=offset, text=text, address=addr, time_min=tmin, time_max=tmax, order_desc=desc)
            return rows, total, page, pages
        finally:
            store.close()

    def _load_can_page_from_cache(self):
        cache = getattr(self, "packet_can_cache_path", "")
        if not cache or not Path(cache).exists():
            return None
        store = PacketSQLiteStore(cache)
        try:
            text = self.can_filter_edit.text().strip().lower() if hasattr(self, "can_filter_edit") else ""
            can_id = self.can_id_filter_edit.text().strip() if hasattr(self, "can_id_filter_edit") else ""
            tmin = self._parse_optional_float("can_time_from_edit")
            tmax = self._parse_optional_float("can_time_to_edit")
            page_size = self._page_size("can_page_size_spin", 2000)
            page = self._page_number("can_page_spin")
            desc = bool(getattr(self, "can_desc_check", None) and self.can_desc_check.isChecked())
            total = store.count_can_frames(text=text, can_id=can_id, time_min=tmin, time_max=tmax)
            page, pages, offset = self._set_page_controls("can", total, page_size, page)
            rows = store.query_can_frames(limit=page_size, offset=offset, text=text, can_id=can_id, time_min=tmin, time_max=tmax, order_desc=desc)
            return rows, total, page, pages
        finally:
            store.close()

    def refresh_packet_table(self) -> None:
        if not hasattr(self, "packet_table"):
            return

        cached = self._load_modbus_page_from_cache()
        if cached is not None:
            shown_records, matched_total, page, pages = cached
            records_for_stats = getattr(self, "packet_records", [])
        else:
            records = getattr(self, "packet_records", [])
            text = self.packet_filter_edit.text().strip().lower() if hasattr(self, "packet_filter_edit") else ""
            addr = self.packet_addr_filter_edit.text().strip().lower() if hasattr(self, "packet_addr_filter_edit") else ""
            tmin = self._parse_optional_float("packet_time_from_edit")
            tmax = self._parse_optional_float("packet_time_to_edit")
            filtered = []
            for rec in records:
                if addr and rec.address.lower() != addr:
                    continue
                if tmin is not None and rec.timestamp < tmin:
                    continue
                if tmax is not None and rec.timestamp > tmax:
                    continue
                hay = " ".join([rec.src, rec.dst, rec.direction, str(rec.function_code), rec.address, rec.status, rec.summary, str(rec.transaction_id), str(rec.unit_id)]).lower()
                if text and text not in hay:
                    continue
                filtered.append(rec)
            page_size = self._page_size("packet_page_size_spin", int(getattr(self, "packet_table_display_limit", 20000)))
            page = self._page_number("packet_page_spin")
            matched_total = len(filtered)
            page, pages, offset = self._set_page_controls("packet", matched_total, page_size, page)
            shown_records = filtered[offset:offset+page_size]
            records_for_stats = records

        self.packet_table.setRowCount(0)
        for rec in shown_records:
            row = self.packet_table.rowCount()
            self.packet_table.insertRow(row)
            values = [
                str(rec.index), f"{rec.timestamp:.6f}", rec.direction, f"{rec.src}:{rec.sport}", f"{rec.dst}:{rec.dport}",
                str(rec.transaction_id), str(rec.unit_id), str(rec.function_code), rec.address, rec.count_or_value, rec.status, rec.latency_ms,
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if rec.status == "Exception":
                    item.setForeground(QColor("#f59e0b"))
                elif rec.status == "Timeout":
                    item.setForeground(QColor("#ef4444"))
                elif rec.direction == "Response":
                    item.setForeground(QColor("#22c55e"))
                sev_map = getattr(self, "packet_diagnosis_highlight_modbus_severity", {})
                if rec.index in getattr(self, "packet_diagnosis_highlight_modbus", set()):
                    item.setBackground(self._diagnosis_severity_color(sev_map.get(rec.index, "Warning")))
                self.packet_table.setItem(row, col, item)
            self.packet_table.setVerticalHeaderItem(row, QTableWidgetItem(str(rec.index)))

        total = len(records_for_stats) if records_for_stats else getattr(self, "packet_modbus_total_count", matched_total)
        exceptions = sum(1 for r in records_for_stats if r.status == "Exception") if records_for_stats else "-"
        timeouts = sum(1 for r in records_for_stats if r.status == "Timeout") if records_for_stats else "-"
        avg_latencies = []
        for r in records_for_stats:
            try:
                if r.latency_ms:
                    avg_latencies.append(float(r.latency_ms))
            except Exception:
                pass
        avg_latency_text = f"{sum(avg_latencies)/len(avg_latencies):.2f} ms" if avg_latencies else "-"
        if hasattr(self, "packet_summary_label"):
            self.packet_summary_label.setText(
                f"Packets: {total} | Matched: {matched_total} | Displayed: {len(shown_records)} | Page: {page}/{pages} | Exceptions: {exceptions} | Timeouts: {timeouts} | Avg latency: {avg_latency_text}"
            )

    def on_packet_row_selected(self) -> None:
        if not hasattr(self, "packet_table") or not hasattr(self, "packet_detail_text"):
            return
        rows = self.packet_table.selectionModel().selectedRows() if self.packet_table.selectionModel() else []
        if not rows:
            return
        idx_item = self.packet_table.item(rows[0].row(), 0)
        if idx_item is None:
            return
        try:
            index = int(idx_item.text())
        except Exception:
            return
        for rec in getattr(self, "packet_records", []):
            if rec.index == index:
                lines = [
                    f"Index: {rec.index}",
                    f"Timestamp: {rec.timestamp:.6f}",
                    f"Direction: {rec.direction}",
                    f"Source: {rec.src}:{rec.sport}",
                    f"Destination: {rec.dst}:{rec.dport}",
                    f"Transaction ID: {rec.transaction_id}",
                    f"Protocol ID: {rec.protocol_id}",
                    f"Length: {rec.length}",
                    f"Unit ID: {rec.unit_id}",
                    f"Function Code: {rec.function_code}",
                    f"Address: {rec.address or '-'}",
                    f"Count/Value: {rec.count_or_value or '-'}",
                    f"Status: {rec.status}",
                    f"Exception Code: {rec.exception_code or '-'}",
                    f"Latency: {rec.latency_ms or '-'} ms",
                    "",
                    f"Summary: {rec.summary}",
                ]
                self.packet_detail_text.setPlainText("\n".join(lines))
                return

    def export_packet_analysis_csv(self) -> None:
        records = getattr(self, "packet_records", [])
        if not records:
            QMessageBox.information(self, "Packet Analyzer", "No packet analysis to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export packet analysis CSV",
            str(self.get_profile_path("packet_analysis.csv") if hasattr(self, "get_profile_path") else Path.cwd() / "packet_analysis.csv"),
            "CSV Files (*.csv)",
        )
        if not path:
            return
        try:
            PacketAnalyzer().export_csv(records, path)
            self.log(f"[PACKET] Exported packet analysis: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Packet Analyzer", f"Failed to export CSV:\n{exc}")


    def analyze_modbus_issues(self) -> None:
        """Build field-friendly Modbus issue hints from the current capture."""
        if not hasattr(self, "packet_issue_table"):
            return
        records = list(getattr(self, "packet_records", []))
        self.packet_issue_table.setRowCount(0)
        analyzer = CommunicationAnalyzerPro()
        analysis = analyzer.analyze_modbus(records)
        self.communication_analysis = analysis

        if hasattr(self, "packet_diagnosis_text"):
            conclusions = analysis.get("conclusions", [])
            latency = analysis.get("latency", {}) or {}
            header = [
                "Communication Analyzer Pro",
                f"Packets: {analysis.get('total', 0)} | Requests: {analysis.get('request_count', 0)} | Responses: {analysis.get('response_count', 0)}",
                f"Timeouts: {analysis.get('timeout_count', 0)} | Exceptions: {analysis.get('exception_count', 0)} | Error rate: {analysis.get('error_rate', 0.0):.2f}%",
            ]
            if latency.get("count"):
                header.append(
                    f"Latency: avg={latency.get('avg', 0):.2f}ms, "
                    f"p50={latency.get('p50', 0):.2f}ms, "
                    f"p90={latency.get('p90', 0):.2f}ms, "
                    f"max={latency.get('max', 0):.2f}ms"
                )
            body = [f"- {line}" for line in conclusions] or ["- No conclusion available."]
            self.packet_diagnosis_text.setPlainText("\n".join(header + [""] + body))

        issues = list(analysis.get("issues", []))
        for issue in issues:
            row = self.packet_issue_table.rowCount()
            self.packet_issue_table.insertRow(row)
            values = issue.as_row() if hasattr(issue, "as_row") else list(issue)
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                severity = str(values[5]).lower() if len(values) > 5 else ""
                typ = str(values[0]) if values else ""
                if severity == "critical" or typ == "Timeout":
                    item.setForeground(QColor("#ef4444"))
                elif severity == "warning" or typ in ["Exception", "Possible Retry", "High Error Rate"]:
                    item.setForeground(QColor("#f59e0b"))
                elif severity == "info":
                    item.setForeground(QColor("#2563eb"))
                self.packet_issue_table.setItem(row, col, item)

        if not issues:
            row = self.packet_issue_table.rowCount()
            self.packet_issue_table.insertRow(row)
            values = [
                "OK",
                "No obvious communication issue found",
                "0",
                "-",
                "Capture looks healthy based on parsed Modbus TCP traffic.",
                "Info",
            ]
            for col, value in enumerate(values):
                self.packet_issue_table.setItem(row, col, QTableWidgetItem(value))

    def send_selected_modbus_to_register_tool(self) -> None:
        """Use a selected Modbus request as a template for the Register Debug tab."""
        if not hasattr(self, "packet_table"):
            return
        rows = self.packet_table.selectionModel().selectedRows() if self.packet_table.selectionModel() else []
        if not rows:
            QMessageBox.information(self, "Packet Replay", "Select a Modbus request row first.")
            return
        idx_item = self.packet_table.item(rows[0].row(), 0)
        if idx_item is None:
            return
        try:
            index = int(idx_item.text())
        except Exception:
            return

        rec = None
        for candidate in getattr(self, "packet_records", []):
            if candidate.index == index:
                rec = candidate
                break
        if rec is None:
            return
        if rec.direction != "Request":
            QMessageBox.information(self, "Packet Replay", "Select a Request row, not a Response row.")
            return
        if not rec.address:
            QMessageBox.information(self, "Packet Replay", "Selected request has no register address to replay.")
            return

        # Replay is intentionally conservative: it fills the Register Debug tool,
        # then the engineer decides when to press Read/Write.
        if hasattr(self, "reg_address_edit"):
            self.reg_address_edit.setText(rec.address)
        if hasattr(self, "reg_count_spin"):
            match = re.search(r"\d+", rec.count_or_value or "")
            if match:
                try:
                    self.reg_count_spin.setValue(max(1, min(125, int(match.group(0)))))
                except Exception:
                    pass
        if hasattr(self, "reg_table_combo"):
            if rec.function_code == 4:
                self.reg_table_combo.setCurrentText("input")
            else:
                self.reg_table_combo.setCurrentText("holding")
        if hasattr(self, "register_debug_log"):
            self.register_debug_log.append(
                f"[REPLAY TEMPLATE] From packet #{rec.index}: FC={rec.function_code}, address={rec.address}, count/value={rec.count_or_value}"
            )
        self.log(f"[PACKET] Sent packet #{rec.index} to Register Debug template")

    # =====================
    # CAN analyzer
    # =====================
    def choose_can_mapping(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose CAN DBC / JSON mapping",
            str(Path.cwd()),
            "CAN Mapping (*.dbc *.json);;DBC Files (*.dbc);;JSON Files (*.json);;All Files (*)",
        )
        if not path:
            return

        selected = Path(path)
        final_path = path
        # Keep a profile-local copy so the same project remains portable.
        try:
            if hasattr(self, "current_profile_dir"):
                target_dir = Path(self.current_profile_dir) / "can_mappings"
                target_dir.mkdir(parents=True, exist_ok=True)
                target = target_dir / selected.name
                if selected.resolve() != target.resolve():
                    shutil.copy2(selected, target)
                final_path = str(target)
                self.log(f"[CAN] Mapping loaded into profile: {target}")
        except Exception as exc:
            self.log(f"[WARN] Failed to copy CAN mapping into profile: {exc}")
            final_path = path

        self.can_mapping_edit.setText(final_path)

        # Important UX fix: if a CAN log was already loaded, re-run the analysis
        # immediately with the newly selected DBC/JSON mapping. Previously the
        # Decoded column stayed blank until the user manually loaded the CAN log
        # again, which made it look like DBC decoding failed.
        current_log = self.can_file_edit.text().strip() if hasattr(self, "can_file_edit") else ""
        if current_log:
            self._analyze_can_log_path(current_log)

    def load_can_log(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load CAN log",
            str(Path.cwd()),
            "CAN Logs (*.asc *.log *.trc *.csv *.txt *.pcap *.pcapng);;All Files (*)",
        )
        if not path:
            return

        self.can_file_edit.setText(path)
        self._analyze_can_log_path(path)

    def _analyze_can_log_path(self, path: str) -> None:
        from bms_logger.can_analyzer import CanAnalyzer

        mapping_path = self.can_mapping_edit.text().strip() if hasattr(self, "can_mapping_edit") else ""
        # Do not auto-load the built-in DBC here. Large DBC parsing can make
        # first file import feel frozen. Workflow is now explicit:
        # 1) load CAN log quickly as raw frames; 2) choose DBC/mapping manually
        # to re-run decoding only when needed.
        cache_path = cache_path_for("can", path, mapping_path or None, profile_dir=getattr(self, "current_profile_dir", None))
        try:
            store = PacketSQLiteStore(cache_path)
            if store.has_kind("can", fingerprint(path) or {}, fingerprint(mapping_path) if mapping_path else None):
                records, stats, anomalies = store.load_can()
                self.log(f"[CAN] Loaded analysis from SQLite cache: {cache_path}")
            else:
                records, stats = CanAnalyzer().analyze(path, mapping_path or None)
                semantic = self._get_can_semantic_lookup()
                semantic_count_tmp = 0
                if semantic and semantic.loaded:
                    for rec in records:
                        if getattr(rec, "decoded", ""):
                            rec.semantic_decoded = semantic.enrich_decoded_text(rec.decoded, getattr(rec, "message_name", ""))
                            if rec.semantic_decoded:
                                semantic_count_tmp += 1
                anomalies = self.compute_can_anomalies(records, stats)
                store.save_can(path, mapping_path or None, records, stats, anomalies)
                self.log(f"[CAN] Created SQLite cache: {cache_path}")
            store.close()
        except Exception as exc:
            QMessageBox.critical(self, "CAN Analyzer", f"Failed to analyze CAN log:\n{exc}")
            self.log(f"[ERROR] CAN analyze failed: {exc}")
            return

        semantic_count = sum(1 for r in records if getattr(r, "semantic_decoded", ""))
        self.can_records = records
        self.can_stats = stats
        self.can_anomalies = anomalies
        self.packet_can_cache_path = str(cache_path)
        self.rebuild_packet_can_signal_buffers(records)
        mapping_kind = "DBC" if mapping_path.lower().endswith(".dbc") else ("JSON" if mapping_path else "raw")
        decoded_count = sum(1 for r in records if getattr(r, "decoded", ""))
        message_count = sum(1 for r in records if getattr(r, "message_name", ""))
        signal_count = len(getattr(self, "packet_can_signal_buffers", {}))
        self.log(
            f"[CAN] Loaded {path}, frames={len(records)}, ids={len(stats)}, "
            f"messages={message_count}, decoded={decoded_count}, signals={signal_count}, "
            f"mapping={mapping_kind}, semantic={semantic_count}, anomalies={len(self.can_anomalies)}"
        )
        if mapping_path and records and decoded_count == 0:
            self.log(
                "[CAN][WARN] Mapping loaded but no decoded signals. Check whether CAN IDs/DLC match the DBC. "
                "This build normalizes Vector extended IDs automatically."
            )
        self.refresh_can_table()

    def clear_can_log(self) -> None:
        """Clear only the loaded CAN evidence and decoded signal buffers."""
        self.can_records = []
        self.can_stats = []
        self.can_anomalies = []
        self.packet_can_signal_buffers = {}
        self.packet_can_signal_labels = {}
        self.packet_selected_can_signals = []
        self.packet_diagnosis_highlight_can = set()
        self.packet_diagnosis_highlight_can_severity = {}
        if hasattr(self, "can_file_edit"):
            self.can_file_edit.clear()
        if hasattr(self, "can_detail_text"):
            self.can_detail_text.clear()
        if hasattr(self, "can_summary_label"):
            self.can_summary_label.setText("No CAN log loaded")
        if hasattr(self, "can_frame_table"):
            self.can_frame_table.setRowCount(0)
        if hasattr(self, "can_stats_table"):
            self.can_stats_table.setRowCount(0)
        if hasattr(self, "can_anomaly_table"):
            self.can_anomaly_table.setRowCount(0)
        self.refresh_packet_can_signal_options()
        self.refresh_packet_can_selected_signals_list()
        self.refresh_packet_can_signal_chart()
        self.log("[CAN] Cleared CAN log evidence")

    def clear_can_mapping(self) -> None:
        """Clear selected DBC/mapping. Already loaded CAN frames stay loaded as raw frames."""
        if hasattr(self, "can_mapping_edit"):
            self.can_mapping_edit.clear()
        # Re-run loaded log without mapping so stale decoded signals disappear.
        current_log = self.can_file_edit.text().strip() if hasattr(self, "can_file_edit") else ""
        if current_log:
            self._analyze_can_log_path(current_log)
        self.log("[CAN] Cleared CAN DBC/mapping")


    def compute_can_anomalies(self, records, stats):
        """Basic field diagnostics for CAN logs: period gaps, DLC changes and payload jumps."""
        by_id: Dict[str, List[Any]] = {}
        expected_period: Dict[str, float] = {}
        for stat in stats:
            try:
                expected_period[stat.can_id.upper()] = float(stat.avg_period_ms) / 1000.0
            except Exception:
                pass
        for rec in records:
            by_id.setdefault(rec.can_id.upper(), []).append(rec)

        anomalies = []
        for can_id, items in by_id.items():
            items = sorted(items, key=lambda r: r.timestamp)
            period = expected_period.get(can_id)
            last = None
            last_data = None
            dlc_set = {r.dlc for r in items}
            if len(dlc_set) > 1:
                anomalies.append({
                    "type": "DLC Change",
                    "can_id": can_id,
                    "index": "-",
                    "time": "-",
                    "value": ",".join(str(v) for v in sorted(dlc_set)),
                    "detail": "Same CAN ID appears with different DLC values.",
                })
            for rec in items:
                if last is not None and period and period > 0:
                    gap = rec.timestamp - last.timestamp
                    if gap > period * 3 and gap > 0.05:
                        anomalies.append({
                            "type": "Period Gap",
                            "can_id": can_id,
                            "index": rec.index,
                            "time": f"{rec.timestamp:.6f}",
                            "value": f"gap={gap*1000:.2f}ms exp={period*1000:.2f}ms",
                            "detail": "Frame arrived much later than the average period; possible lost frame or bus pause.",
                        })
                if last_data is not None:
                    try:
                        cur = bytes(int(x, 16) for x in str(rec.data).split())
                        prev = bytes(int(x, 16) for x in str(last_data).split())
                        if len(cur) == len(prev) and cur and sum(a != b for a, b in zip(cur, prev)) >= max(4, len(cur) // 2):
                            anomalies.append({
                                "type": "Payload Jump",
                                "can_id": can_id,
                                "index": rec.index,
                                "time": f"{rec.timestamp:.6f}",
                                "value": rec.data,
                                "detail": "Payload changed sharply compared with previous frame of same ID.",
                            })
                    except Exception:
                        pass
                last = rec
                last_data = rec.data
        return anomalies[:500]

    def refresh_can_table(self) -> None:
        if not hasattr(self, "can_frame_table"):
            return

        view = self.can_view_combo.currentText() if hasattr(self, "can_view_combo") else "Frames"
        text = self.can_filter_edit.text().strip().lower() if hasattr(self, "can_filter_edit") else ""
        records = getattr(self, "can_records", [])
        stats = getattr(self, "can_stats", [])
        anomalies = getattr(self, "can_anomalies", [])

        if hasattr(self, "can_anomaly_table"):
            self.can_anomaly_table.hide()

        if view == "Anomalies":
            self.can_frame_table.hide()
            self.can_stats_table.hide()
            self.can_anomaly_table.show()
            self.can_anomaly_table.setRowCount(0)
            displayed = 0
            for anomaly in anomalies:
                hay = " ".join(str(v) for v in anomaly.values()).lower()
                if text and text not in hay:
                    continue
                row = self.can_anomaly_table.rowCount()
                self.can_anomaly_table.insertRow(row)
                values = [
                    anomaly.get("type", ""),
                    anomaly.get("can_id", ""),
                    str(anomaly.get("index", "")),
                    str(anomaly.get("time", "")),
                    str(anomaly.get("value", "")),
                    anomaly.get("detail", ""),
                ]
                for col, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setForeground(QColor("#f59e0b"))
                    self.can_anomaly_table.setItem(row, col, item)
                displayed += 1
            if hasattr(self, "can_summary_label"):
                self.can_summary_label.setText(
                    f"CAN Frames: {len(records)} | CAN IDs: {len(stats)} | Anomalies: {len(anomalies)} | Displayed: {displayed}"
                )
            return

        if view == "ID Statistics":
            self.can_frame_table.hide()
            self.can_stats_table.show()
            self.can_stats_table.setRowCount(0)
            displayed = 0
            for stat in stats:
                hay = " ".join([
                    stat.can_id,
                    getattr(stat, "message_name", ""),
                    str(stat.count),
                    stat.avg_period_ms,
                    stat.frequency_hz,
                    stat.dlc_set,
                ]).lower()
                if text and text not in hay:
                    continue
                row = self.can_stats_table.rowCount()
                self.can_stats_table.insertRow(row)
                values = [
                    stat.can_id,
                    getattr(stat, "message_name", ""),
                    str(stat.count),
                    f"{stat.first_ts:.6f}",
                    f"{stat.last_ts:.6f}",
                    stat.avg_period_ms,
                    stat.frequency_hz,
                    stat.dlc_set,
                ]
                for col, value in enumerate(values):
                    self.can_stats_table.setItem(row, col, QTableWidgetItem(value))
                displayed += 1
            if hasattr(self, "can_summary_label"):
                self.can_summary_label.setText(
                    f"CAN Frames: {len(records)} | CAN IDs: {len(stats)} | Displayed IDs: {displayed}"
                )
            return

        self.can_stats_table.hide()
        if hasattr(self, "can_anomaly_table"):
            self.can_anomaly_table.hide()
        self.can_frame_table.show()
        self.can_frame_table.setRowCount(0)

        cached = self._load_can_page_from_cache()
        if cached is not None:
            page_records, matched, page, pages = cached
            records_for_counts = getattr(self, "can_records", [])
        else:
            can_id_filter = self.can_id_filter_edit.text().strip().lower() if hasattr(self, "can_id_filter_edit") else ""
            tmin = self._parse_optional_float("can_time_from_edit")
            tmax = self._parse_optional_float("can_time_to_edit")
            filtered = []
            for rec in records:
                if can_id_filter and rec.can_id.lower() != can_id_filter:
                    continue
                if tmin is not None and rec.timestamp < tmin:
                    continue
                if tmax is not None and rec.timestamp > tmax:
                    continue
                hay = " ".join([
                    rec.channel, rec.can_id, getattr(rec, "message_name", ""), rec.data, rec.direction, rec.frame_type, rec.status,
                    getattr(rec, "semantic_decoded", ""), rec.decoded, rec.raw,
                ]).lower()
                if text and text not in hay:
                    continue
                filtered.append(rec)
            page_size = self._page_size("can_page_size_spin", int(getattr(self, "packet_table_display_limit", 20000)))
            page = self._page_number("can_page_spin")
            matched = len(filtered)
            page, pages, offset = self._set_page_controls("can", matched, page_size, page)
            if hasattr(self, "can_desc_check") and self.can_desc_check.isChecked():
                filtered = list(reversed(filtered))
            page_records = filtered[offset:offset+page_size]
            records_for_counts = records

        error_count = sum(1 for r in records_for_counts if r.status != "OK") if records_for_counts else "-"
        decoded_count = sum(1 for r in records_for_counts if r.decoded) if records_for_counts else "-"
        displayed = 0
        for rec in page_records:
            row = self.can_frame_table.rowCount()
            self.can_frame_table.insertRow(row)
            values = [
                str(rec.index), f"{rec.timestamp:.6f}", rec.channel, rec.can_id, getattr(rec, "message_name", ""), str(rec.dlc),
                rec.data, rec.direction, rec.frame_type, rec.status, getattr(rec, "semantic_decoded", "") or "-", rec.decoded,
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if rec.status != "OK" or rec.frame_type == "Error":
                    item.setForeground(QColor("#ef4444"))
                elif rec.decoded:
                    item.setForeground(QColor("#22c55e"))
                sev_map = getattr(self, "packet_diagnosis_highlight_can_severity", {})
                if rec.index in getattr(self, "packet_diagnosis_highlight_can", set()):
                    item.setBackground(self._diagnosis_severity_color(sev_map.get(rec.index, "Warning")))
                self.can_frame_table.setItem(row, col, item)
            displayed += 1

        if hasattr(self, "can_summary_label"):
            self.can_summary_label.setText(
                f"CAN Frames: {len(records_for_counts) if records_for_counts else matched} | Matched: {matched} | Displayed: {displayed} | Page: {page}/{pages} | CAN IDs: {len(stats)} | Errors: {error_count} | Decoded: {decoded_count}"
            )

    def on_can_row_selected(self) -> None:
        if not hasattr(self, "can_frame_table") or not hasattr(self, "can_detail_text"):
            return
        rows = self.can_frame_table.selectionModel().selectedRows() if self.can_frame_table.selectionModel() else []
        if not rows:
            return
        idx_item = self.can_frame_table.item(rows[0].row(), 0)
        if idx_item is None:
            return
        try:
            index = int(idx_item.text())
        except Exception:
            return
        for rec in getattr(self, "can_records", []):
            if rec.index == index:
                lines = [
                    f"Index: {rec.index}",
                    f"Timestamp: {rec.timestamp:.6f}",
                    f"Channel: {rec.channel}",
                    f"CAN ID: {rec.can_id}",
                    f"Message: {getattr(rec, 'message_name', '') or '-'}",
                    f"DLC: {rec.dlc}",
                    f"Data: {rec.data}",
                    f"Direction: {rec.direction or '-'}",
                    f"Frame Type: {rec.frame_type}",
                    f"Frequency: {rec.frequency_hz or '-'} Hz",
                    f"Status: {rec.status}",
                    f"Decoded: {rec.decoded or '-'}",
                    f"Semantic: {getattr(rec, 'semantic_decoded', '') or '-'}",
                    "",
                ]
                semantic = self._get_can_semantic_lookup()
                if semantic and semantic.loaded and rec.decoded:
                    verbose = semantic.verbose_lines(rec.decoded, getattr(rec, "message_name", ""))
                    if verbose:
                        lines.extend(["Semantic Detail:", *verbose, ""])
                lines.append(f"Raw: {rec.raw}")
                self.can_detail_text.setPlainText("\n".join(lines))
                return

    def export_can_frames_csv(self) -> None:
        from bms_logger.can_analyzer import CanAnalyzer

        records = getattr(self, "can_records", [])
        if not records:
            QMessageBox.information(self, "CAN Analyzer", "No CAN frames to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export CAN frames CSV",
            str(self.get_profile_path("can_frames.csv") if hasattr(self, "get_profile_path") else Path.cwd() / "can_frames.csv"),
            "CSV Files (*.csv)",
        )
        if not path:
            return
        try:
            CanAnalyzer().export_records_csv(records, path)
            self.log(f"[CAN] Exported frames: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "CAN Analyzer", f"Failed to export CAN frames:\n{exc}")

    def export_can_stats_csv(self) -> None:
        from bms_logger.can_analyzer import CanAnalyzer

        stats = getattr(self, "can_stats", [])
        if not stats:
            QMessageBox.information(self, "CAN Analyzer", "No CAN stats to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export CAN stats CSV",
            str(self.get_profile_path("can_id_stats.csv") if hasattr(self, "get_profile_path") else Path.cwd() / "can_id_stats.csv"),
            "CSV Files (*.csv)",
        )
        if not path:
            return
        try:
            CanAnalyzer().export_stats_csv(stats, path)
            self.log(f"[CAN] Exported stats: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "CAN Analyzer", f"Failed to export CAN stats:\n{exc}")

    # =====================
    # CAN + Modbus joint analyzer
    # =====================
    def _default_protocol_path(self, filename: str) -> str:
        return str(Path(__file__).resolve().parents[1] / "protocols" / filename)

    def choose_joint_asc(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose CAN ASC log",
            str(Path.cwd()),
            "CAN ASC Logs (*.asc);;CAN Logs (*.asc *.log *.trc *.csv *.txt);;All Files (*)",
        )
        if path:
            self.joint_asc_edit.setText(path)

    def choose_joint_modbus_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Wireshark Modbus capture",
            str(Path.cwd()),
            "Wireshark Capture (*.pcapng *.pcap *.cap);;CSV Files (*.csv);;All Files (*)",
        )
        if path:
            self.joint_modbus_edit.setText(path)

    def choose_joint_dbc(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose V22 DBC",
            str(Path.cwd()),
            "DBC Files (*.dbc);;All Files (*)",
        )
        if path:
            self.joint_dbc_edit.setText(path)

    def choose_joint_mapping(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose CAN to Modbus mapping JSON",
            str(Path.cwd()),
            "JSON Files (*.json);;All Files (*)",
        )
        if path:
            self.joint_mapping_edit.setText(path)

    def _get_joint_paths(self) -> tuple[str, str, str, str]:
        asc = self.joint_asc_edit.text().strip() if hasattr(self, "joint_asc_edit") else ""
        modbus_capture = self.joint_modbus_edit.text().strip() if hasattr(self, "joint_modbus_edit") else ""
        dbc = self.joint_dbc_edit.text().strip() if hasattr(self, "joint_dbc_edit") else ""
        mapping = self.joint_mapping_edit.text().strip() if hasattr(self, "joint_mapping_edit") else ""
        if not dbc:
            dbc = self._default_protocol_path("ESS_PLT_MCAN_V3.28_20250611_Saveas.dbc")
            if hasattr(self, "joint_dbc_edit"):
                self.joint_dbc_edit.setText(dbc)
        if not mapping:
            mapping = self._default_protocol_path("catl_v22_can_modbus_mapping.json")
            if hasattr(self, "joint_mapping_edit"):
                self.joint_mapping_edit.setText(mapping)
        return asc, modbus_capture, dbc, mapping

    def run_joint_analysis_ui(self) -> None:
        from bms_logger.joint_analyzer import correlate

        asc, modbus_capture, dbc, mapping = self._get_joint_paths()
        missing = [name for name, path in [("CAN ASC", asc), ("Modbus capture", modbus_capture), ("DBC", dbc), ("Mapping", mapping)] if not path or not Path(path).exists()]
        if missing:
            QMessageBox.warning(self, "Joint Analysis", "Missing file(s): " + ", ".join(missing))
            return

        tolerance = float(self.joint_tolerance_spin.value()) if hasattr(self, "joint_tolerance_spin") else 0.5
        try:
            rows = correlate(asc, modbus_capture, dbc, mapping, tolerance)
        except Exception as exc:
            QMessageBox.critical(self, "Joint Analysis", f"Failed to run joint analysis:\n{exc}")
            self.log(f"[JOINT][ERROR] {exc}")
            return

        self.joint_rows = rows
        self.refresh_joint_table()
        self.log(f"[JOINT] Completed: rows={len(rows)}, tolerance={tolerance}s")

    def refresh_joint_table(self) -> None:
        if not hasattr(self, "joint_table"):
            return
        rows = list(getattr(self, "joint_rows", []))
        self.joint_table.setRowCount(0)
        for result in rows[:20000]:
            row = self.joint_table.rowCount()
            self.joint_table.insertRow(row)
            values = [
                result.get("time_can", ""),
                result.get("time_modbus", ""),
                result.get("delta_s", ""),
                result.get("can_id", ""),
                result.get("can_signal", ""),
                result.get("can_value", ""),
                result.get("modbus_address", ""),
                result.get("modbus_raw", ""),
                result.get("modbus_value", ""),
                result.get("abs_diff", ""),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                try:
                    if col == 9 and value not in (None, "") and float(value) > 0.001:
                        item.setForeground(QColor("#f59e0b"))
                except Exception:
                    pass
                self.joint_table.setItem(row, col, item)

        if hasattr(self, "joint_summary_label"):
            diffs = []
            for r in rows:
                try:
                    if r.get("abs_diff") is not None:
                        diffs.append(float(r.get("abs_diff")))
                except Exception:
                    pass
            max_diff = max(diffs) if diffs else None
            avg_diff = sum(diffs) / len(diffs) if diffs else None
            shown = min(len(rows), 20000)
            diff_text = f" | Avg diff: {avg_diff:.4g} | Max diff: {max_diff:.4g}" if avg_diff is not None else ""
            self.joint_summary_label.setText(f"Correlated rows: {len(rows)} | Displayed: {shown}{diff_text}")

        if hasattr(self, "joint_detail_text"):
            if rows:
                self.joint_detail_text.setPlainText(
                    "Joint analysis completed. Select a row to inspect CAN value, Modbus raw/value and time delta.\n"
                    "Non-zero Abs Diff usually means scaling, offset, address mapping, or time alignment should be checked."
                )
            else:
                self.joint_detail_text.setPlainText(
                    "No correlated rows found. Check whether the Modbus capture contains function 03/04 read responses or CSV time/address/value columns, "
                    "whether the ASC and Modbus capture time bases overlap, and whether the mapping addresses match the capture."
                )

    def on_joint_row_selected(self) -> None:
        if not hasattr(self, "joint_table") or not hasattr(self, "joint_detail_text"):
            return
        rows = self.joint_table.selectionModel().selectedRows() if self.joint_table.selectionModel() else []
        if not rows:
            return
        idx = rows[0].row()
        data = list(getattr(self, "joint_rows", []))
        if idx >= len(data):
            return
        r = data[idx]
        lines = [
            "CAN + Modbus Correlation Detail",
            f"CAN time: {r.get('time_can')}",
            f"Modbus time: {r.get('time_modbus')}",
            f"Delta: {r.get('delta_s')} s",
            "",
            f"CAN ID: {r.get('can_id')}",
            f"CAN signal: {r.get('can_signal')}",
            f"CAN value: {r.get('can_value')}",
            "",
            f"Modbus address: {r.get('modbus_address')}",
            f"Modbus raw: {r.get('modbus_raw')}",
            f"Modbus scaled value: {r.get('modbus_value')}",
            f"Abs diff: {r.get('abs_diff')}",
        ]
        self.joint_detail_text.setPlainText("\n".join(lines))

    def export_joint_analysis_csv(self) -> None:
        from bms_logger.joint_analyzer import write_report

        rows = list(getattr(self, "joint_rows", []))
        if not rows:
            QMessageBox.information(self, "Joint Analysis", "No joint analysis result to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export joint analysis CSV",
            str(self.get_profile_path("joint_analysis_report.csv") if hasattr(self, "get_profile_path") else Path.cwd() / "joint_analysis_report.csv"),
            "CSV Files (*.csv)",
        )
        if not path:
            return
        try:
            write_report(rows, path)
            self.log(f"[JOINT] Exported joint analysis: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Joint Analysis", f"Failed to export CSV:\n{exc}")

    # =====================
    # Packet Analyzer CAN semantics + local plots
    # =====================
    def _get_can_semantic_lookup(self):
        lookup = getattr(self, "_can_semantic_lookup", None)
        if lookup is None:
            try:
                lookup = CanSemanticLookup()
            except Exception:
                lookup = None
            self._can_semantic_lookup = lookup
        return lookup

    def rebuild_packet_can_signal_buffers(self, records=None) -> None:
        """Build Packet Analyzer-local CAN signal buffers.

        Curves page is kept for live Modbus/driver monitoring. Imported CAN
        frame plots are owned by Packet Analyzer so offline packet analysis stays
        in one place.
        """
        from collections import defaultdict

        self.packet_can_signal_buffers = defaultdict(list)
        self.packet_can_signal_labels = {}
        semantic = self._get_can_semantic_lookup()
        records = records if records is not None else getattr(self, "can_records", [])
        if not records:
            self.refresh_packet_can_signal_options()
            self.refresh_packet_can_signal_chart()
            return
        for rec in records:
            decoded = getattr(rec, "decoded", "") or ""
            if not decoded:
                continue
            message_name = getattr(rec, "message_name", "") or ""
            parser = semantic.parse_decoded if semantic and semantic.loaded else None
            values = parser(decoded) if parser else []
            if not values:
                for part in decoded.split(";"):
                    m = re.match(r"^\s*([^=]+)=\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)", part)
                    if not m:
                        continue
                    class _V:
                        pass
                    v = _V()
                    v.signal = m.group(1).strip()
                    v.value = float(m.group(2))
                    values.append(v)
            for val in values:
                key = f"{message_name}::{val.signal}" if message_name else val.signal
                try:
                    self.packet_can_signal_buffers[key].append((float(rec.timestamp), float(val.value)))
                except Exception:
                    continue
                if key not in self.packet_can_signal_labels:
                    label = semantic.short_label(val.signal, message_name) if semantic and semantic.loaded else val.signal
                    self.packet_can_signal_labels[key] = f"{message_name} / {label}" if message_name else label
        self.refresh_packet_can_signal_options()
        if not getattr(self, "packet_selected_can_signals", []) and getattr(self, "packet_can_signal_buffers", {}):
            # Keep CAN signal plot usable out-of-the-box: auto-select the first
            # decoded numeric signal after a DBC/mapping decode.
            self.packet_selected_can_signals = [sorted(self.packet_can_signal_buffers.keys())[0]]
        self.refresh_packet_can_selected_signals_list()
        self.refresh_packet_can_signal_chart()

    def refresh_packet_can_signal_options(self) -> None:
        if not hasattr(self, "packet_can_signal_combo"):
            return
        current = self.packet_can_signal_combo.currentText()
        self.packet_can_signal_combo.blockSignals(True)
        self.packet_can_signal_combo.clear()
        for key in sorted(getattr(self, "packet_can_signal_buffers", {}).keys()):
            label = getattr(self, "packet_can_signal_labels", {}).get(key, key)
            self.packet_can_signal_combo.addItem(label, key)
        if current:
            idx = self.packet_can_signal_combo.findText(current)
            if idx >= 0:
                self.packet_can_signal_combo.setCurrentIndex(idx)
        self.packet_can_signal_combo.blockSignals(False)

    def add_packet_can_signal_from_combo(self) -> None:
        if not hasattr(self, "packet_can_signal_combo"):
            return
        key = self.packet_can_signal_combo.currentData() or self.packet_can_signal_combo.currentText()
        if not key:
            return
        selected = getattr(self, "packet_selected_can_signals", [])
        if key not in selected:
            if len(selected) >= len(getattr(self, "packet_can_signal_series", [])):
                QMessageBox.information(self, "CAN Plot", "You can plot up to 4 CAN signals at once.")
                return
            selected.append(key)
        self.packet_selected_can_signals = selected
        self.refresh_packet_can_selected_signals_list()
        self.refresh_packet_can_signal_chart()

    def clear_packet_can_signals(self) -> None:
        self.packet_selected_can_signals = []
        self.refresh_packet_can_selected_signals_list()
        self.refresh_packet_can_signal_chart()

    def refresh_packet_can_selected_signals_list(self) -> None:
        if not hasattr(self, "packet_can_selected_signals_list"):
            return
        self.packet_can_selected_signals_list.clear()
        labels = getattr(self, "packet_can_signal_labels", {})
        for key in getattr(self, "packet_selected_can_signals", []):
            self.packet_can_selected_signals_list.addItem(labels.get(key, key))

    def refresh_packet_can_signal_chart(self) -> None:
        if not hasattr(self, "packet_can_signal_series"):
            return
        selected = list(getattr(self, "packet_selected_can_signals", []))
        buffers = getattr(self, "packet_can_signal_buffers", {})
        labels = getattr(self, "packet_can_signal_labels", {})
        all_x, all_y = [], []
        for idx, series in enumerate(self.packet_can_signal_series):
            series.clear()
            if idx >= len(selected):
                series.setName(f"Signal {idx + 1}")
                continue
            key = selected[idx]
            series.setName(labels.get(key, key)[:80])
            points = buffers.get(key, [])
            if not points:
                continue
            # Down-sample to keep Qt responsive on very large ASC files.
            step = max(1, len(points) // 5000)
            for x, y in points[::step]:
                series.append(float(x), float(y))
                all_x.append(float(x)); all_y.append(float(y))
        if all_x and all_y:
            min_x, max_x = min(all_x), max(all_x)
            min_y, max_y = min(all_y), max(all_y)
            if min_x == max_x:
                max_x = min_x + 1
            if min_y == max_y:
                min_y -= 1; max_y += 1
            pad_y = (max_y - min_y) * 0.08 or 1
            self.packet_can_signal_axis_x.setRange(min_x, max_x)
            self.packet_can_signal_axis_y.setRange(min_y - pad_y, max_y + pad_y)
        else:
            self.packet_can_signal_axis_x.setRange(0, 1)
            self.packet_can_signal_axis_y.setRange(0, 1)

    def export_packet_can_signals_csv(self) -> None:
        buffers = getattr(self, "packet_can_signal_buffers", {})
        if not buffers:
            QMessageBox.information(self, "CAN Plot", "No decoded CAN signals to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export decoded CAN signals CSV",
            str(self.get_profile_path("packet_can_decoded_signals.csv") if hasattr(self, "get_profile_path") else Path.cwd() / "packet_can_decoded_signals.csv"),
            "CSV Files (*.csv)",
        )
        if not path:
            return
        try:
            labels = getattr(self, "packet_can_signal_labels", {})
            with open(path, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["signal_key", "label", "time", "value"])
                for key in sorted(buffers.keys()):
                    for ts, value in buffers[key]:
                        writer.writerow([key, labels.get(key, key), f"{ts:.6f}", value])
            self.log(f"[CAN] Exported Packet Analyzer signal curves: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "CAN Plot", f"Failed to export CAN signal CSV:\n{exc}")

    # =====================
    # Packet health diagnosis
    # =====================
    def run_packet_diagnosis(self) -> None:
        """Run cross-layer packet diagnosis from currently loaded evidence."""
        from bms_logger.packet_diagnosis import PacketDiagnosisEngine

        engine = PacketDiagnosisEngine()
        scope = self.packet_diagnosis_scope_combo.currentText() if hasattr(self, "packet_diagnosis_scope_combo") else "Auto"
        has_modbus = bool(getattr(self, "packet_records", []))
        has_can = bool(getattr(self, "can_records", []))
        has_joint = bool(getattr(self, "joint_rows", []))
        if scope == "CAN only":
            check_modbus, check_can, check_mapping, check_business = False, True, False, True
        elif scope == "Modbus only":
            check_modbus, check_can, check_mapping, check_business = True, False, False, False
        elif scope == "Cross / Joint":
            check_modbus, check_can, check_mapping, check_business = True, True, True, True
        else:
            # Auto only diagnoses evidence that is actually loaded, so two
            # unrelated files do not force a joint/cross diagnosis.
            check_modbus = has_modbus
            check_can = has_can
            check_mapping = has_joint or (has_modbus and has_can)
            check_business = has_can
        try:
            analysis = engine.analyze(
                modbus_records=getattr(self, "packet_records", []),
                can_records=getattr(self, "can_records", []),
                can_stats=getattr(self, "can_stats", []),
                can_anomalies=getattr(self, "can_anomalies", []),
                joint_rows=getattr(self, "joint_rows", []),
                can_signal_buffers=getattr(self, "packet_can_signal_buffers", {}),
                check_modbus=check_modbus,
                check_can=check_can,
                check_mapping=check_mapping,
                check_business=check_business,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Packet Diagnosis", f"Failed to run diagnosis:\n{exc}")
            self.log(f"[ERROR] Packet diagnosis failed: {exc}")
            return

        self.packet_diagnosis_analysis = analysis
        self._precompute_packet_diagnosis_highlights(analysis)
        self.refresh_packet_diagnosis_view()
        # Highlight raw evidence once after diagnosis. Selecting an issue no
        # longer needs to re-scan/refresh large packet tables.
        if hasattr(self, "refresh_can_table"):
            self.refresh_can_table()
        if hasattr(self, "refresh_packet_table"):
            self.refresh_packet_table()
        summary = analysis.get("summary", {}) or {}
        counts = summary.get("counts", {}) or {}
        self.log(
            "[DIAGNOSIS] "
            f"critical={counts.get('Critical', 0)}, warning={counts.get('Warning', 0)}, info={counts.get('Info', 0)}"
        )

    def refresh_packet_diagnosis_view(self) -> None:
        analysis = getattr(self, "packet_diagnosis_analysis", {}) or {}
        issues = list(analysis.get("issues", []))
        summary = analysis.get("summary", {}) or {}

        if hasattr(self, "packet_diagnosis_summary"):
            counts = summary.get("counts", {}) or {}
            by_layer = summary.get("by_layer", {}) or {}
            lines = [
                "Packet Health Check / Fault Diagnosis",
                f"Critical: {counts.get('Critical', 0)} | Warning: {counts.get('Warning', 0)} | Info: {counts.get('Info', 0)}",
                "Layer distribution: " + (", ".join(f"{k}={v}" for k, v in sorted(by_layer.items())) or "-"),
                "",
            ]
            lines.extend(f"- {x}" for x in summary.get("conclusions", []))
            self.packet_diagnosis_summary.setPlainText("\n".join(lines))

        if not hasattr(self, "packet_diagnosis_table"):
            return
        self.packet_diagnosis_table.setRowCount(0)
        if not issues:
            self.packet_diagnosis_table.insertRow(0)
            row = ["OK", "All", "-", "-", "no_issue", "No issue found by current rules", "-", "Keep captures from the same test window for joint diagnosis."]
            for col, value in enumerate(row):
                self.packet_diagnosis_table.setItem(0, col, QTableWidgetItem(value))
            return

        for issue in issues:
            row_idx = self.packet_diagnosis_table.rowCount()
            self.packet_diagnosis_table.insertRow(row_idx)
            row = issue.as_row() if hasattr(issue, "as_row") else list(issue)
            for col, value in enumerate(row):
                item = QTableWidgetItem(str(value))
                sev = str(row[0]).lower() if row else ""
                if sev == "critical":
                    item.setForeground(QColor("#ef4444"))
                elif sev == "warning":
                    item.setForeground(QColor("#f59e0b"))
                elif sev == "info":
                    item.setForeground(QColor("#2563eb"))
                elif sev == "ok":
                    item.setForeground(QColor("#22c55e"))
                self.packet_diagnosis_table.setItem(row_idx, col, item)

    def _diagnosis_severity_color(self, severity: str) -> QColor:
        sev = str(severity or "").lower()
        if sev == "critical":
            return QColor("#fecaca")  # red-200
        if sev == "warning":
            return QColor("#fef3c7")  # amber-100
        if sev == "info":
            return QColor("#dbeafe")  # blue-100
        return QColor("#dcfce7")      # green-100

    def _rank_severity(self, old: str | None, new: str) -> str:
        rank = {"Critical": 3, "Warning": 2, "Info": 1, "OK": 0, None: -1, "": -1}
        return new if rank.get(new, 0) > rank.get(old, -1) else (old or new)

    def _precompute_packet_diagnosis_highlights(self, analysis) -> None:
        can_indexes = set()
        modbus_indexes = set()
        can_severity = {}
        modbus_severity = {}
        for issue in (analysis or {}).get("issues", []) or []:
            refs = dict(getattr(issue, "refs", {}) or {})
            severity = str(getattr(issue, "severity", "Warning") or "Warning")
            for x in refs.get("can_indexes", []) or []:
                try:
                    idx = int(x)
                    can_indexes.add(idx)
                    can_severity[idx] = self._rank_severity(can_severity.get(idx), severity)
                except Exception:
                    pass
            for x in refs.get("modbus_indexes", []) or []:
                try:
                    idx = int(x)
                    modbus_indexes.add(idx)
                    modbus_severity[idx] = self._rank_severity(modbus_severity.get(idx), severity)
                except Exception:
                    pass
        self.packet_diagnosis_highlight_can = can_indexes
        self.packet_diagnosis_highlight_modbus = modbus_indexes
        self.packet_diagnosis_highlight_can_severity = can_severity
        self.packet_diagnosis_highlight_modbus_severity = modbus_severity

    def clear_packet_all_evidence(self) -> None:
        """Clear CAN, Modbus, joint-analysis and diagnosis evidence."""
        if hasattr(self, "clear_packet_capture"):
            self.clear_packet_capture()
        if hasattr(self, "clear_can_log"):
            self.clear_can_log()
        self.joint_rows = []
        if hasattr(self, "joint_table"):
            self.joint_table.setRowCount(0)
        self.packet_diagnosis_analysis = {"issues": [], "summary": {"conclusions": ["Evidence cleared."], "counts": {}}}
        self.packet_diagnosis_highlight_can = set()
        self.packet_diagnosis_highlight_can_severity = {}
        self.packet_diagnosis_highlight_modbus = set()
        self.packet_diagnosis_highlight_modbus_severity = {}
        if hasattr(self, "packet_diagnosis_table"):
            self.packet_diagnosis_table.setRowCount(0)
        if hasattr(self, "packet_diagnosis_summary"):
            self.packet_diagnosis_summary.setPlainText("Evidence cleared.")
        if hasattr(self, "packet_diagnosis_detail"):
            self.packet_diagnosis_detail.clear()
        self.log("[DIAGNOSIS] Cleared all packet analyzer evidence")

    def on_packet_diagnosis_row_selected(self) -> None:
        if not hasattr(self, "packet_diagnosis_table") or not hasattr(self, "packet_diagnosis_detail"):
            return
        rows = self.packet_diagnosis_table.selectionModel().selectedRows() if self.packet_diagnosis_table.selectionModel() else []
        if not rows:
            return
        r = rows[0].row()
        vals = []
        for c in range(self.packet_diagnosis_table.columnCount()):
            item = self.packet_diagnosis_table.item(r, c)
            vals.append(item.text() if item else "")
        labels = ["Severity", "Layer", "Time", "Object", "Rule", "Description", "Evidence", "Suggested Action"]
        lines = [f"{labels[i]}: {vals[i]}" for i in range(min(len(labels), len(vals)))]

        issue = None
        try:
            issues = list((getattr(self, "packet_diagnosis_analysis", {}) or {}).get("issues", []))
            if 0 <= r < len(issues):
                issue = issues[r]
        except Exception:
            issue = None
        refs = dict(getattr(issue, "refs", {}) or {}) if issue is not None else {}
        can_indexes = [int(x) for x in refs.get("can_indexes", []) if str(x).lstrip("-").isdigit()]
        modbus_indexes = [int(x) for x in refs.get("modbus_indexes", []) if str(x).lstrip("-").isdigit()]
        joint_rows = refs.get("joint_rows", []) or []

        # Raw packet/frame rows were already highlighted when diagnosis ran.
        # On selection we only scroll to the first linked row, which is much
        # faster on large captures.

        if can_indexes or modbus_indexes or joint_rows:
            lines.extend(["", "Linked Raw Evidence:"])
            if can_indexes:
                lines.append("CAN frame index(es): " + ", ".join(str(x) for x in can_indexes[:20]) + (" ..." if len(can_indexes) > 20 else ""))
                self._select_can_frame_index(can_indexes[0])
            if modbus_indexes:
                lines.append("Modbus packet index(es): " + ", ".join(str(x) for x in modbus_indexes[:20]) + (" ..." if len(modbus_indexes) > 20 else ""))
                self._select_modbus_packet_index(modbus_indexes[0])
            if joint_rows:
                lines.append("Joint row index(es): " + ", ".join(str(x) for x in joint_rows[:20]) + (" ..." if len(joint_rows) > 20 else ""))
        else:
            lines.extend(["", "Linked Raw Evidence: none; this issue is aggregate-level or needs the matching raw file loaded."])

        lines.extend([
            "",
            "Troubleshooting order:",
            "1. Fix Critical communication/protocol issues first; value analysis is unreliable if packets are missing.",
            "2. For Mapping warnings, verify MBMU vs SBMU level, address offset, scaling, signedness and byte order.",
            "3. For Business warnings, this version uses point-table span first, then MBD Chinese/English semantics, and only then keyword fallback.",
            "4. Highlighted yellow rows in CAN/Modbus tabs are the raw packets/frames related to this issue.",
        ])
        self.packet_diagnosis_detail.setPlainText("\n".join(lines))

    def _select_can_frame_index(self, index: int) -> None:
        if not hasattr(self, "can_frame_table"):
            return
        try:
            if hasattr(self, "can_view_combo") and self.can_view_combo.currentText() != "Frames":
                self.can_view_combo.setCurrentText("Frames")
                self.refresh_can_table()
            for row in range(self.can_frame_table.rowCount()):
                item = self.can_frame_table.item(row, 0)
                if item and item.text() == str(index):
                    self.can_frame_table.selectRow(row)
                    self.can_frame_table.scrollToItem(item)
                    return
        except Exception:
            pass

    def _select_modbus_packet_index(self, index: int) -> None:
        if not hasattr(self, "packet_table"):
            return
        try:
            for row in range(self.packet_table.rowCount()):
                item = self.packet_table.item(row, 0)
                if item and item.text() == str(index):
                    self.packet_table.selectRow(row)
                    self.packet_table.scrollToItem(item)
                    return
        except Exception:
            pass

    def export_packet_diagnosis_csv(self) -> None:
        from bms_logger.packet_diagnosis import PacketDiagnosisEngine

        analysis = getattr(self, "packet_diagnosis_analysis", None)
        if not analysis:
            self.run_packet_diagnosis()
            analysis = getattr(self, "packet_diagnosis_analysis", None)
        if not analysis:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export packet diagnosis CSV",
            str(self.get_profile_path("packet_diagnosis.csv") if hasattr(self, "get_profile_path") else Path.cwd() / "packet_diagnosis.csv"),
            "CSV Files (*.csv)",
        )
        if not path:
            return
        try:
            PacketDiagnosisEngine().export_csv(analysis, path)
            self.log(f"[DIAGNOSIS] Exported CSV: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Packet Diagnosis", f"Failed to export CSV:\n{exc}")

    def export_packet_diagnosis_markdown(self) -> None:
        from bms_logger.packet_diagnosis import PacketDiagnosisEngine

        analysis = getattr(self, "packet_diagnosis_analysis", None)
        if not analysis:
            self.run_packet_diagnosis()
            analysis = getattr(self, "packet_diagnosis_analysis", None)
        if not analysis:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export packet diagnosis Markdown",
            str(self.get_profile_path("packet_diagnosis_report.md") if hasattr(self, "get_profile_path") else Path.cwd() / "packet_diagnosis_report.md"),
            "Markdown Files (*.md);;Text Files (*.txt)",
        )
        if not path:
            return
        try:
            PacketDiagnosisEngine().export_markdown(analysis, path)
            self.log(f"[DIAGNOSIS] Exported Markdown: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Packet Diagnosis", f"Failed to export Markdown:\n{exc}")
