from __future__ import annotations

from datetime import datetime
import os
import subprocess
import sys

from PySide6.QtWidgets import QMessageBox, QTableWidgetItem

from bms_logger.report_manager import ReportManager


class ReportMixin:
    def _ensure_debug_session(self) -> dict:
        session = getattr(self, "debug_session", None)
        if not isinstance(session, dict):
            session = {
                "name": "Default Session",
                "started_at": "-",
                "ended_at": "-",
                "notes": "",
            }
            self.debug_session = session
        return session

    def start_debug_session(self) -> None:
        session = self._ensure_debug_session()
        name = self.report_session_name_edit.text().strip() if hasattr(self, "report_session_name_edit") else "Debug Session"
        notes = self.report_session_notes_edit.toPlainText().strip() if hasattr(self, "report_session_notes_edit") else ""
        session.update({
            "name": name or "Debug Session",
            "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "ended_at": "-",
            "notes": notes,
        })
        self.log(f"[REPORT] Session started: {session['name']}")
        self.refresh_report_session_view()

    def end_debug_session(self) -> None:
        session = self._ensure_debug_session()
        if session.get("started_at", "-") == "-":
            session["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        session["ended_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if hasattr(self, "report_session_notes_edit"):
            session["notes"] = self.report_session_notes_edit.toPlainText().strip()
        self.log(f"[REPORT] Session ended: {session.get('name','-')}")
        self.refresh_report_session_view()

    def refresh_report_session_view(self) -> None:
        session = self._ensure_debug_session()
        if hasattr(self, "report_session_table"):
            self.report_session_table.setRowCount(0)
            rows = [
                ("Name", session.get("name", "-")),
                ("Started", session.get("started_at", "-")),
                ("Ended", session.get("ended_at", "-")),
                ("Profile", getattr(self, "current_profile_name", "default")),
                ("Profile Dir", str(getattr(self, "current_profile_dir", "-"))),
                ("BMS Count", str(len(getattr(self, "devices", [])))),
                ("PCS Count", str(len(getattr(self, "pcs_configs", {})))),
            ]
            for key, value in rows:
                row = self.report_session_table.rowCount()
                self.report_session_table.insertRow(row)
                self.report_session_table.setItem(row, 0, QTableWidgetItem(str(key)))
                self.report_session_table.setItem(row, 1, QTableWidgetItem(str(value)))
        if hasattr(self, "report_session_name_edit"):
            self.report_session_name_edit.setText(session.get("name", "Default Session"))
        if hasattr(self, "report_session_notes_edit"):
            self.report_session_notes_edit.setPlainText(session.get("notes", ""))

    def generate_debug_report(self) -> None:
        try:
            if hasattr(self, "report_session_notes_edit"):
                self._ensure_debug_session()["notes"] = self.report_session_notes_edit.toPlainText().strip()
            manager = ReportManager(self)
            path = manager.write_report()
            self.last_report_path = path
            with open(path, "r", encoding="utf-8") as f:
                html_text = f.read()
            if hasattr(self, "report_preview_text"):
                self.report_preview_text.setHtml(html_text)
            if hasattr(self, "report_path_label"):
                self.report_path_label.setText(str(path))
            self.log(f"[REPORT] Generated HTML report: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Report", f"Failed to generate report:\n{exc}")
            self.log(f"[ERROR] Report generation failed: {exc}")

    def export_debug_package(self) -> None:
        try:
            if hasattr(self, "report_session_notes_edit"):
                self._ensure_debug_session()["notes"] = self.report_session_notes_edit.toPlainText().strip()
            manager = ReportManager(self)
            path = manager.export_debug_package(include_report=True)
            self.last_debug_package_path = path
            if hasattr(self, "report_path_label"):
                self.report_path_label.setText(str(path))
            self.log(f"[REPORT] Exported debug package: {path}")
            QMessageBox.information(self, "Debug Package", f"Exported:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Debug Package", f"Failed to export debug package:\n{exc}")
            self.log(f"[ERROR] Debug package export failed: {exc}")

    def open_reports_folder(self) -> None:
        path = ReportManager(self).reports_dir()
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            QMessageBox.warning(self, "Reports", f"Failed to open reports folder:\n{exc}")
