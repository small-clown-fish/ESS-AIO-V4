from __future__ import annotations

import csv
from pathlib import Path
from typing import List

from PySide6.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem
from PySide6.QtGui import QColor

from bms_logger.event_timeline import EventTimelineBuilder, TimelineEvent


class TimelineMixin:
    def refresh_event_timeline(self) -> None:
        builder = EventTimelineBuilder(self)
        events = builder.build()
        summary = builder.summarize(events)
        self.timeline_events = events
        self.timeline_summary = summary
        self.refresh_event_timeline_table()
        if hasattr(self, "timeline_hint_text"):
            hints = summary.get("root_cause_hints", [])
            self.timeline_hint_text.setPlainText("\n".join(f"• {h}" for h in hints) if hints else "No hints available.")
        self.log(f"[TIMELINE] Built event timeline, events={len(events)}")

    def _timeline_event_visible(self, event: TimelineEvent, view: str, text: str) -> bool:
        if view == "Critical/Error" and event.severity not in {"CRITICAL", "ERROR"}:
            return False
        if view == "Warning" and event.severity != "WARN":
            return False
        if view == "Control" and event.category != "Control":
            return False
        if view == "Modbus" and not event.category.startswith("Modbus"):
            return False
        if view == "CAN" and event.category != "CAN Anomaly":
            return False
        if view == "Cutoff/Derating" and event.category not in {"Cutoff", "Derating"}:
            return False
        if view == "Signal Compare" and event.category != "Signal Compare":
            return False
        if text:
            hay = " ".join([event.time_text, event.source, event.category, event.severity, event.title, event.detail, event.suggestion]).lower()
            if text not in hay:
                return False
        return True

    def refresh_event_timeline_table(self) -> None:
        if not hasattr(self, "timeline_table"):
            return
        if not hasattr(self, "timeline_events"):
            self.timeline_events = EventTimelineBuilder(self).build()
            self.timeline_summary = EventTimelineBuilder(self).summarize(self.timeline_events)

        view = self.timeline_filter_combo.currentText() if hasattr(self, "timeline_filter_combo") else "All"
        text = self.timeline_search_edit.text().strip().lower() if hasattr(self, "timeline_search_edit") else ""
        events: List[TimelineEvent] = list(getattr(self, "timeline_events", []))
        filtered = [e for e in events if self._timeline_event_visible(e, view, text)]

        self.timeline_table.setRowCount(0)
        for order, event in enumerate(filtered, start=1):
            row = self.timeline_table.rowCount()
            self.timeline_table.insertRow(row)
            values = [
                event.time_text,
                event.severity,
                event.category,
                event.source,
                event.title,
                event.detail,
                event.suggestion,
                str(order),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if event.severity == "CRITICAL":
                    item.setForeground(QColor("#ef4444"))
                elif event.severity == "ERROR":
                    item.setForeground(QColor("#f97316"))
                elif event.severity == "WARN":
                    item.setForeground(QColor("#f59e0b"))
                elif event.severity == "INFO":
                    item.setForeground(QColor("#38bdf8"))
                self.timeline_table.setItem(row, col, item)

        summary = getattr(self, "timeline_summary", {}) or {}
        if hasattr(self, "timeline_summary_label"):
            self.timeline_summary_label.setText(
                f"Events: {summary.get('total', len(events))} | Displayed: {len(filtered)} | "
                f"Critical/Error: {summary.get('critical_or_error', 0)} | Warning: {summary.get('warning', 0)} | "
                f"Range: {summary.get('first_event', '-')} → {summary.get('last_event', '-')}"
            )

    def on_timeline_row_selected(self) -> None:
        if not hasattr(self, "timeline_table") or not hasattr(self, "timeline_hint_text"):
            return
        rows = self.timeline_table.selectionModel().selectedRows() if self.timeline_table.selectionModel() else []
        if not rows:
            return
        row = rows[0].row()
        vals = []
        for col in range(self.timeline_table.columnCount()):
            item = self.timeline_table.item(row, col)
            vals.append(item.text() if item else "")
        detail = (
            f"Time: {vals[0]}\nSeverity: {vals[1]}\nCategory: {vals[2]}\nSource: {vals[3]}\n"
            f"Title: {vals[4]}\n\nDetail:\n{vals[5]}\n\nSuggestion:\n{vals[6]}"
        )
        self.timeline_hint_text.setPlainText(detail)

    def export_event_timeline_csv(self) -> None:
        events = list(getattr(self, "timeline_events", []))
        if not events:
            self.refresh_event_timeline()
            events = list(getattr(self, "timeline_events", []))
        if not events:
            QMessageBox.information(self, "Event Timeline", "No timeline events to export.")
            return
        default = self.get_profile_path("event_timeline.csv") if hasattr(self, "get_profile_path") else Path.cwd() / "event_timeline.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Export Event Timeline CSV", str(default), "CSV Files (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["time", "severity", "category", "source", "title", "detail", "suggestion"])
                for e in events:
                    writer.writerow([e.time_text, e.severity, e.category, e.source, e.title, e.detail, e.suggestion])
            self.log(f"[TIMELINE] Exported event timeline: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Event Timeline", f"Failed to export timeline:\n{exc}")
