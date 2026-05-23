from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem


class TemplateMixin:
    def _selected_template_folder(self) -> str:
        if not hasattr(self, "template_package_table"):
            return ""
        row = self.template_package_table.currentRow()
        if row < 0:
            return ""
        item = self.template_package_table.item(row, 0)
        return item.text() if item is not None else ""

    def refresh_template_package_view(self) -> None:
        if not hasattr(self, "template_package_table"):
            return
        manager = getattr(self, "template_manager", None)
        if manager is None:
            return

        self.template_package_table.setRowCount(0)
        for tmpl in manager.list_templates():
            row = self.template_package_table.rowCount()
            self.template_package_table.insertRow(row)
            values = [
                tmpl.get("folder", ""),
                tmpl.get("name", "-"),
                tmpl.get("version", "-"),
                tmpl.get("type", "-"),
                tmpl.get("description", ""),
            ]
            for col, value in enumerate(values):
                self.template_package_table.setItem(row, col, QTableWidgetItem(str(value)))

        if hasattr(self, "template_preview_text"):
            self.template_preview_text.setPlainText("Select a template to preview its contents.")

    def on_template_package_selected(self) -> None:
        name = self._selected_template_folder()
        if not name or not hasattr(self, "template_preview_text"):
            return
        try:
            self.template_preview_text.setPlainText(self.template_manager.preview_template(name))
        except Exception as exc:
            self.template_preview_text.setPlainText(f"Preview failed: {exc}")

    def import_template_package(self, path: str | None = None) -> None:
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Import ESS-AIO Template Package",
                str(Path.cwd()),
                "ESS Template (*.ess-template.zip *.zip);;Zip Files (*.zip);;All Files (*)",
            )
        if not path:
            return
        try:
            name = self.template_manager.import_template(path)
            self.log(f"[TEMPLATE] Imported template package: {name}")
            self.refresh_template_package_view()
        except Exception as exc:
            QMessageBox.critical(self, "Template Import Failed", str(exc))
            self.log(f"[ERROR] Template import failed: {exc}")

    def validate_selected_template_package(self) -> None:
        name = self._selected_template_folder()
        if not name:
            QMessageBox.information(self, "Info", "Please select a template package.")
            return
        result = self.template_manager.validate_template(name)
        text = "\n".join(result.messages)
        if hasattr(self, "template_preview_text"):
            self.template_preview_text.setPlainText(self.template_manager.preview_template(name))
        if result.ok:
            QMessageBox.information(self, "Template Validation", text)
        else:
            QMessageBox.warning(self, "Template Validation", text)

    def apply_selected_template_package(self) -> None:
        name = self._selected_template_folder()
        if not name:
            QMessageBox.information(self, "Info", "Please select a template package.")
            return
        try:
            applied = self.template_manager.apply_template(name)
            self.log(f"[TEMPLATE] Applied template package: {name}; files={applied}")
            # Reload affected profile resources.
            try:
                self.reload_alarm_map()
            except Exception:
                pass
            try:
                self.reload_pcs_config()
            except Exception:
                pass
            try:
                self.load_driver_config()
                self.refresh_driver_binding_view()
            except Exception:
                pass
            try:
                self.refresh_point_template_view()
            except Exception:
                pass
            try:
                if hasattr(self, "strategy_engine"):
                    self.strategy_engine.load()
                    self.refresh_strategy_view()
            except Exception:
                pass
            QMessageBox.information(self, "Template Applied", "Applied files:\n" + "\n".join(applied or ["No files copied"]))
        except Exception as exc:
            QMessageBox.critical(self, "Template Apply Failed", str(exc))
            self.log(f"[ERROR] Template apply failed: {exc}")

    def export_selected_template_package(self) -> None:
        name = self._selected_template_folder()
        if not name:
            QMessageBox.information(self, "Info", "Please select a template package.")
            return
        default = Path.cwd() / f"{name}.ess-template.zip"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export ESS-AIO Template Package",
            str(default),
            "ESS Template (*.ess-template.zip);;Zip Files (*.zip)",
        )
        if not path:
            return
        try:
            output = self.template_manager.export_template(name, path)
            self.log(f"[TEMPLATE] Exported template package: {output}")
        except Exception as exc:
            QMessageBox.critical(self, "Template Export Failed", str(exc))
            self.log(f"[ERROR] Template export failed: {exc}")
