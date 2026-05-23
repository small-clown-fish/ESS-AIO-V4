from __future__ import annotations

import json
import csv
from collections import deque
from pathlib import Path
from typing import Any, Dict

from PySide6.QtCharts import QChart, QLineSeries
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem, QInputDialog
from PySide6.QtGui import QColor





class ProfileMixin:
    def get_profile_path(self, filename: str) -> Path:
        self.current_profile_dir.mkdir(parents=True, exist_ok=True)
        return self.current_profile_dir / filename

    def new_profile(self) -> None:
        name, ok = QInputDialog.getText(self, "New Profile", "Profile name:")
        if not ok:
            return

        name = name.strip()
        if not name:
            QMessageBox.warning(self, "Warning", "Profile name cannot be empty.")
            return

        self.current_profile_name = name
        self.current_profile_dir = self.profile_root / name
        self.current_profile_dir.mkdir(parents=True, exist_ok=True)
        if hasattr(self, "strategy_engine"):
            self.strategy_engine.set_profile_dir(self.current_profile_dir)

        self.save_profile()
        self.log(f"[INFO] New profile created: {name}")

    def load_profile(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            "Load Profile",
            str(self.profile_root),
        )

        if not directory:
            return

        self.current_profile_dir = Path(directory)
        self.current_profile_name = self.current_profile_dir.name
        if hasattr(self, "strategy_engine"):
            self.strategy_engine.set_profile_dir(self.current_profile_dir)

        self.auto_load_startup_configs()
        self.log(f"[INFO] Loaded profile: {self.current_profile_name}")

    def save_profile(self) -> None:
        self.current_profile_dir.mkdir(parents=True, exist_ok=True)

        self.save_devices_to_default()
        self.save_site_config()
        self.save_runtime_config()
        try:
            self.save_driver_config()
        except Exception as exc:
            self.log(f"[ERROR] Save driver config failed: {exc}")

        try:
            if hasattr(self, "strategy_editor"):
                data = json.loads(self.strategy_editor.toPlainText())
                self.strategy_engine.save(data)
            elif hasattr(self, "strategy_engine"):
                self.strategy_engine.save()
        except Exception as exc:
            self.log(f"[ERROR] Save strategy failed: {exc}")

        try:
            self.save_pcs_config()
        except Exception as exc:
            self.log(f"[ERROR] Save PCS config failed: {exc}")

        self.log(f"[INFO] Saved profile: {self.current_profile_name}")

    def get_point_template_dir(self) -> Path:
        path = self.get_profile_path("point_tables")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def ensure_default_point_templates(self) -> None:
        """Copy bundled CATL point table into the active profile if available."""
        try:
            template_dir = self.get_point_template_dir()
            docs_dir = Path.cwd() / "docs"
            if not docs_dir.exists():
                return

            for src in docs_dir.glob("*.json"):
                if "point_table" in src.name.lower() or "catl" in src.name.lower():
                    dst = template_dir / src.name
                    if not dst.exists():
                        import shutil
                        shutil.copy2(src, dst)
        except Exception as exc:
            self.log(f"[WARN] Failed to prepare point templates: {exc}")

    def _read_point_template_metadata(self, path: Path) -> Dict[str, str]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            meta = data.get("metadata", {}) if isinstance(data, dict) else {}
            return {
                "title": str(meta.get("document_title", "-")),
                "version": str(meta.get("version", "-")),
                "date": str(meta.get("date", "-")),
            }
        except Exception:
            return {"title": "-", "version": "-", "date": "-"}

    def refresh_point_template_view(self) -> None:
        if not hasattr(self, "point_template_table"):
            return

        self.ensure_default_point_templates()
        template_dir = self.get_point_template_dir()
        active_path = self.get_profile_path("active_point_table.json")

        active_source = ""
        if active_path.exists():
            try:
                with open(active_path, "r", encoding="utf-8") as f:
                    active_data = json.load(f)
                active_source = str(active_data.get("_template_source", ""))
            except Exception:
                active_source = ""

        self.point_template_table.setRowCount(0)

        for path in sorted(template_dir.glob("*.json")):
            row = self.point_template_table.rowCount()
            self.point_template_table.insertRow(row)

            meta = self._read_point_template_metadata(path)
            is_active = "Yes" if path.name == active_source else ""

            values = [
                path.name,
                meta.get("title", "-"),
                meta.get("version", "-"),
                meta.get("date", "-"),
                is_active,
            ]

            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col == 4 and value == "Yes":
                    self._set_table_item_color(item, "online")
                self.point_template_table.setItem(row, col, item)

    def import_point_table_template(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import point table JSON",
            str(Path.cwd()),
            "JSON Files (*.json)",
        )
        if not path:
            return

        src = Path(path)
        dst = self.get_point_template_dir() / src.name

        try:
            import shutil
            shutil.copy2(src, dst)
            self.log(f"[INFO] Imported point table template: {dst}")
            self.refresh_point_template_view()
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to import point table:\n{exc}")

    def apply_selected_point_table_template(self) -> None:
        if not hasattr(self, "point_template_table"):
            return

        row = self.point_template_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Info", "Please select a point table template.")
            return

        item = self.point_template_table.item(row, 0)
        if item is None:
            return

        src = self.get_point_template_dir() / item.text()
        if not src.exists():
            QMessageBox.warning(self, "Warning", "Selected template does not exist.")
            return

        try:
            with open(src, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, dict):
                data["_template_source"] = src.name

            active_path = self.get_profile_path("active_point_table.json")
            with open(active_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            self.log(f"[INFO] Active point table set: {src.name}")
            self.refresh_point_template_view()
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to apply point table:\n{exc}")

    def open_point_templates_folder(self) -> None:
        import os
        import subprocess
        import sys

        path = self.get_point_template_dir()
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            self.log(f"[ERROR] Failed to open templates folder: {exc}")

    def export_profile_package(self) -> None:
        self.save_profile()

        default_path = self.profile_root / f"{self.current_profile_name}.zip"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Profile Package",
            str(default_path),
            "Zip Files (*.zip)",
        )
        if not path:
            return

        try:
            import zipfile
            output_path = Path(path)
            with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for file_path in self.current_profile_dir.rglob("*"):
                    if file_path.is_file():
                        arcname = file_path.relative_to(self.current_profile_dir)
                        zf.write(file_path, arcname)

            self.log(f"[INFO] Exported profile package: {output_path}")

        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to export profile package:\n{exc}")

    def import_profile_package(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Profile Package",
            str(self.profile_root),
            "Zip Files (*.zip)",
        )
        if not path:
            return

        name, ok = QInputDialog.getText(
            self,
            "Import Profile",
            "Profile name:",
            text=Path(path).stem,
        )
        if not ok:
            return

        name = name.strip()
        if not name:
            QMessageBox.warning(self, "Warning", "Profile name cannot be empty.")
            return

        target_dir = self.profile_root / name

        try:
            import zipfile
            import shutil

            if target_dir.exists():
                reply = QMessageBox.question(
                    self,
                    "Overwrite Profile",
                    f"Profile '{name}' already exists. Overwrite?",
                )
                if reply != QMessageBox.Yes:
                    return
                shutil.rmtree(target_dir)

            target_dir.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(path, "r") as zf:
                for member in zf.infolist():
                    member_path = Path(member.filename)
                    if member_path.is_absolute() or ".." in member_path.parts:
                        continue
                    zf.extract(member, target_dir)

            self.current_profile_name = name
            self.current_profile_dir = target_dir
            self.auto_load_startup_configs()
            self.log(f"[INFO] Imported and loaded profile: {name}")

        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to import profile package:\n{exc}")

    # ========================
    # v2.1: Quick Diagnosis
    # ========================
