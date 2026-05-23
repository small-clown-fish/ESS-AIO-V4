from __future__ import annotations

from pathlib import Path
from ..paths import user_data_dir, resource_path

from PySide6.QtWidgets import QMessageBox

from ..version import version_text, version_dict
from ..release_manager import ensure_profile


class ReleaseMixin:
    def show_about_dialog(self) -> None:
        QMessageBox.information(self, "About ESS-AIO", version_text())

    def run_startup_self_check(self) -> None:
        result = ensure_profile(self.current_profile_dir, resource_path("."))
        self.log(result.to_text())
        QMessageBox.information(self, "Startup Self Check", result.to_text())
        if hasattr(self, "refresh_release_view"):
            self.refresh_release_view()

    def open_crash_log_folder(self) -> None:
        import os
        import subprocess
        import sys

        log_dir = user_data_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(log_dir))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(log_dir)])
            else:
                subprocess.Popen(["xdg-open", str(log_dir)])
        except Exception as exc:
            self.log(f"[ERROR] Failed to open crash log folder: {exc}")

    def refresh_release_view(self) -> None:
        if not hasattr(self, "release_info_table"):
            return

        info = version_dict()
        info["profile"] = self.current_profile_name
        info["profile_dir"] = str(self.current_profile_dir)

        self.release_info_table.setRowCount(0)
        for key, value in info.items():
            row = self.release_info_table.rowCount()
            self.release_info_table.insertRow(row)
            from PySide6.QtWidgets import QTableWidgetItem
            self.release_info_table.setItem(row, 0, QTableWidgetItem(str(key)))
            self.release_info_table.setItem(row, 1, QTableWidgetItem(str(value)))

        if hasattr(self, "release_check_text"):
            result = ensure_profile(self.current_profile_dir, resource_path("."))
            self.release_check_text.setPlainText(result.to_text())
