from __future__ import annotations

import json
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from .paths import resource_path
from typing import Any


@dataclass
class TemplateValidationResult:
    ok: bool
    messages: list[str]
    meta: dict[str, Any]


class TemplateManager:
    """Manage ESS-AIO template packages (.ess-template.zip or .zip).

    Template package layout:
        meta.json
        dbc/*.dbc
        points/*.json
        strategy/strategy.json
        driver/driver_config.json
        pcs/pcs_config.json or pcs/pcs_configs.json
        alarm/alarm_map.json
    """

    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx
        self.template_dir = resource_path("templates")
        self.template_dir.mkdir(parents=True, exist_ok=True)

    def _safe_name(self, name: str) -> str:
        text = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(name).strip())
        return text or "template"

    def _template_path(self, name: str) -> Path:
        return self.template_dir / self._safe_name(name)

    def list_templates(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if not self.template_dir.exists():
            return rows
        for folder in sorted(p for p in self.template_dir.iterdir() if p.is_dir()):
            meta = self.load_meta(folder.name)
            rows.append({
                "folder": folder.name,
                "name": meta.get("name", folder.name),
                "version": meta.get("version", "-"),
                "type": meta.get("type", "-"),
                "description": meta.get("description", ""),
                "path": str(folder),
            })
        return rows

    def load_meta(self, name: str) -> dict[str, Any]:
        meta_file = self._template_path(name) / "meta.json"
        if not meta_file.exists():
            return {}
        try:
            return json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def validate_folder(self, folder: Path) -> TemplateValidationResult:
        messages: list[str] = []
        meta: dict[str, Any] = {}
        ok = True

        if not folder.exists() or not folder.is_dir():
            return TemplateValidationResult(False, [f"Template folder not found: {folder}"], {})

        meta_path = folder / "meta.json"
        if not meta_path.exists():
            ok = False
            messages.append("Missing meta.json")
        else:
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if not meta.get("name"):
                    messages.append("meta.json has no 'name'; folder name will be used")
                if not meta.get("version"):
                    messages.append("meta.json has no 'version'")
                if not meta.get("type"):
                    messages.append("meta.json has no 'type'")
            except Exception as exc:
                ok = False
                messages.append(f"Invalid meta.json: {exc}")

        payload_found = False
        checks = [
            ("dbc", "*.dbc"),
            ("points", "*.json"),
            ("strategy", "strategy.json"),
            ("driver", "driver_config.json"),
            ("pcs", "pcs_config.json"),
            ("pcs", "pcs_configs.json"),
            ("alarm", "alarm_map.json"),
        ]
        for subdir, pattern in checks:
            d = folder / subdir
            if d.exists() and any(d.glob(pattern)):
                payload_found = True

        if not payload_found:
            ok = False
            messages.append("No supported template payload found: dbc/, points/, strategy/, driver/, pcs/, alarm/")

        # Validate JSON payloads where possible.
        for json_file in list((folder / "points").glob("*.json")) + list((folder / "strategy").glob("*.json")) + list((folder / "driver").glob("*.json")) + list((folder / "pcs").glob("*.json")) + list((folder / "alarm").glob("*.json")):
            try:
                json.loads(json_file.read_text(encoding="utf-8"))
            except Exception as exc:
                ok = False
                messages.append(f"Invalid JSON: {json_file.relative_to(folder)} - {exc}")

        if ok:
            messages.insert(0, "Template validation passed")
        return TemplateValidationResult(ok, messages, meta)

    def validate_template(self, name: str) -> TemplateValidationResult:
        return self.validate_folder(self._template_path(name))

    def import_template(self, zip_path: str | Path) -> str:
        zip_path = Path(zip_path)
        if not zip_path.exists():
            raise FileNotFoundError(str(zip_path))
        if zip_path.suffix.lower() not in {".zip", ".ess-template"} and not zip_path.name.lower().endswith(".ess-template.zip"):
            raise ValueError("Template package must be .zip or .ess-template.zip")

        temp_dir = self.template_dir / f".__import_{zip_path.stem}"
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(temp_dir)

            # Accept either root/meta.json or a single nested folder/meta.json.
            root = temp_dir
            if not (root / "meta.json").exists():
                children = [p for p in temp_dir.iterdir() if p.is_dir()]
                if len(children) == 1 and (children[0] / "meta.json").exists():
                    root = children[0]

            validation = self.validate_folder(root)
            if not validation.ok:
                raise ValueError("; ".join(validation.messages))

            meta = validation.meta
            folder_name = self._safe_name(str(meta.get("name") or zip_path.stem))
            target = self.template_dir / folder_name
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(root, target)
            return target.name
        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    def export_template(self, name: str, output_path: str | Path) -> Path:
        folder = self._template_path(name)
        if not folder.exists():
            raise FileNotFoundError(str(folder))
        output_path = Path(output_path)
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_path in folder.rglob("*"):
                if file_path.is_file():
                    zf.write(file_path, file_path.relative_to(folder))
        return output_path

    def apply_template(self, name: str) -> list[str]:
        folder = self._template_path(name)
        validation = self.validate_folder(folder)
        if not validation.ok:
            raise ValueError("; ".join(validation.messages))

        profile = Path(self.ctx.current_profile_dir)
        profile.mkdir(parents=True, exist_ok=True)
        applied: list[str] = []

        copy_rules = [
            (folder / "dbc", profile / "can_mappings", "*.dbc"),
            (folder / "points", profile / "point_tables", "*.json"),
        ]
        for src_dir, dst_dir, pattern in copy_rules:
            if src_dir.exists():
                dst_dir.mkdir(parents=True, exist_ok=True)
                for src in src_dir.glob(pattern):
                    shutil.copy2(src, dst_dir / src.name)
                    applied.append(str((dst_dir / src.name).relative_to(profile)))

        single_files = [
            (folder / "strategy" / "strategy.json", profile / "strategy.json"),
            (folder / "driver" / "driver_config.json", profile / "driver_config.json"),
            (folder / "pcs" / "pcs_config.json", profile / "pcs_config.json"),
            (folder / "pcs" / "pcs_configs.json", profile / "pcs_configs.json"),
            (folder / "alarm" / "alarm_map.json", profile / "alarm_map.json"),
        ]
        for src, dst in single_files:
            if src.exists():
                shutil.copy2(src, dst)
                applied.append(str(dst.relative_to(profile)))

        # If a point table was provided, set the first one active for convenience.
        point_dir = profile / "point_tables"
        point_files = sorted(point_dir.glob("*.json")) if point_dir.exists() else []
        if point_files:
            try:
                data = json.loads(point_files[0].read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    data["_template_source"] = point_files[0].name
                (profile / "active_point_table.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                applied.append("active_point_table.json")
            except Exception:
                pass

        return applied

    def preview_template(self, name: str) -> str:
        folder = self._template_path(name)
        if not folder.exists():
            return "Template not found."
        validation = self.validate_folder(folder)
        lines: list[str] = []
        meta = validation.meta or self.load_meta(name)
        lines.append("Template Preview")
        lines.append("=" * 60)
        lines.append(f"Folder: {folder.name}")
        lines.append(f"Name: {meta.get('name', '-')}")
        lines.append(f"Version: {meta.get('version', '-')}")
        lines.append(f"Type: {meta.get('type', '-')}")
        lines.append(f"Description: {meta.get('description', '-')}")
        lines.append("")
        lines.append("Validation")
        lines.append("-" * 60)
        for msg in validation.messages:
            lines.append(f"- {msg}")
        lines.append("")
        lines.append("Files")
        lines.append("-" * 60)
        for file_path in sorted(p for p in folder.rglob("*") if p.is_file()):
            lines.append(str(file_path.relative_to(folder)))
        return "\n".join(lines)
