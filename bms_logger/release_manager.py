from __future__ import annotations

import json
import shutil
import traceback
from datetime import datetime
from pathlib import Path
from .paths import user_data_dir
from typing import Any

from .version import APP_NAME, APP_VERSION, BUILD_ID, PROFILE_SCHEMA_VERSION, version_dict


DEFAULT_RUNTIME_CONFIG: dict[str, Any] = {
    "heartbeat_interval": 1.0,
    "hv_step_timeout": 30.0,
    "hv_poll_interval": 1.0,
    "pcs_zero_power_threshold": 0.1,
    "charge_cutoff_max_cell_voltage": 3650.0,
    "discharge_cutoff_min_cell_voltage": 2500.0,
    "cutoff_mode": "Alarm Only",
    "cutoff_trigger_confirm_count": 3,
    "cutoff_recover_confirm_count": 3,
    "alarm_history_window_before_minutes": 5,
    "alarm_history_window_after_minutes": 5,
    "power_tracking_enabled": True,
    "power_tracking_tolerance_kw": 5.0,
    "power_tracking_confirm_count": 3,
    "pcs_fault_protection_mode": "Alarm Only",
    "pcs_fault_confirm_count": 3,
    "fake_mode": False,
    "worker_start_stagger_seconds": 0.25,
    "ui_refresh_interval": 1.0,
}

DEFAULT_STRATEGY: dict[str, Any] = {
    "enabled": True,
    "runtime_overrides": {},
    "rules": [],
}

DEFAULT_DRIVER_CONFIG: dict[str, Any] = {
    "bms_driver": "catl_v17_bms",
    "pcs_driver": "generic_modbus_pcs",
}

DEFAULT_SITE_CONFIG: dict[str, Any] = {
    "site": "Default Site",
    "clusters": [
        {"name": "Cluster-1", "bms_devices": [], "pcs_device": "", "pcs_devices": []}
    ],
}

# Empty PCS list is a valid startup state. Operators add PCS devices explicitly
# and connect them manually from the PCS Devices page.
DEFAULT_PCS_CONFIG: dict[str, Any] = {}


class StartupSelfCheckResult:
    def __init__(self) -> None:
        self.created: list[str] = []
        self.migrated: list[str] = []
        self.warnings: list[str] = []
        self.errors: list[str] = []

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_text(self) -> str:
        lines = ["Startup Self Check", f"Status: {'OK' if self.ok else 'ERROR'}"]
        for title, items in [
            ("Created", self.created),
            ("Migrated", self.migrated),
            ("Warnings", self.warnings),
            ("Errors", self.errors),
        ]:
            lines.append("")
            lines.append(title + ":")
            if items:
                lines.extend(f"  - {item}" for item in items)
            else:
                lines.append("  - none")
        return "\n".join(lines)


def _read_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)



def _looks_like_legacy_bad_alarm_map(data: Any) -> bool:
    """Detect older bundled alarm maps produced from wrapped PDF text.

    The legacy file had shifted names such as 0x0000 Bit15 ending with
    "Low SOC over" and missing basic current bits at 0x0001 Bit2.
    """
    if not isinstance(data, dict):
        return False
    try:
        bit15 = str(data.get("0x0000", {}).get("Bit15", ""))
        bit2 = data.get("0x0001", {}).get("Bit2")
        return ("Low SOC over" in bit15) or bit2 is None
    except Exception:
        return False


def _bundled_clean_alarm_map(project_root: Path | None) -> dict[str, Any] | None:
    candidates = []
    if project_root is not None:
        candidates.append(project_root / "bms_profiles" / "catl_v22" / "alarm_map.json")
        candidates.append(project_root / "alarm_map.json")
    for candidate in candidates:
        try:
            if candidate.exists():
                data = _read_json(candidate, {})
                if isinstance(data, dict) and data:
                    return data
        except Exception:
            pass
    return None

def _merge_defaults(existing: dict[str, Any], defaults: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    changed = False
    merged = dict(existing)
    for key, value in defaults.items():
        if key not in merged:
            merged[key] = value
            changed = True
    return merged, changed


def ensure_profile(profile_dir: Path, project_root: Path | None = None) -> StartupSelfCheckResult:
    """Create missing profile files and migrate old profile structures in-place."""
    result = StartupSelfCheckResult()
    profile_dir.mkdir(parents=True, exist_ok=True)

    for subdir in ["logs", "output", "reports", "debug_packages", "point_tables"]:
        path = profile_dir / subdir
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            result.created.append(str(path))

    manifest_path = profile_dir / "profile_manifest.json"
    manifest = _read_json(manifest_path, {})
    manifest_defaults = {
        "app": APP_NAME,
        "app_version": APP_VERSION,
        "build_id": BUILD_ID,
        "profile_schema_version": PROFILE_SCHEMA_VERSION,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    manifest, manifest_changed = _merge_defaults(manifest if isinstance(manifest, dict) else {}, manifest_defaults)
    manifest["app_version"] = APP_VERSION
    manifest["build_id"] = BUILD_ID
    manifest["profile_schema_version"] = PROFILE_SCHEMA_VERSION
    manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _write_json(manifest_path, manifest)
    if manifest_changed or not manifest_path.exists():
        result.created.append(str(manifest_path))

    file_defaults = {
        "runtime_config.json": DEFAULT_RUNTIME_CONFIG,
        "strategy.json": DEFAULT_STRATEGY,
        "driver_config.json": DEFAULT_DRIVER_CONFIG,
        "site_config.json": DEFAULT_SITE_CONFIG,
        "devices.json": [],
        "pcs_configs.json": DEFAULT_PCS_CONFIG,
        "alarm_map.json": {},
    }

    for filename, defaults in file_defaults.items():
        path = profile_dir / filename
        if not path.exists():
            _write_json(path, defaults)
            result.created.append(str(path))
            continue

        if isinstance(defaults, dict):
            current = _read_json(path, {})
            if not isinstance(current, dict):
                result.warnings.append(f"{filename} is not a JSON object; left unchanged")
                continue
            merged, changed = _merge_defaults(current, defaults)
            if changed:
                backup = path.with_suffix(path.suffix + f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                shutil.copy2(path, backup)
                _write_json(path, merged)
                result.migrated.append(f"{filename} (backup: {backup.name})")

    # Fix legacy/default alarm map if it is empty or generated from the old wrapped-PDF table.
    alarm_path = profile_dir / "alarm_map.json"
    alarm_current = _read_json(alarm_path, {})
    if (not isinstance(alarm_current, dict)) or (not alarm_current) or _looks_like_legacy_bad_alarm_map(alarm_current):
        clean_alarm_map = _bundled_clean_alarm_map(project_root)
        if clean_alarm_map:
            if alarm_path.exists():
                backup = alarm_path.with_suffix(alarm_path.suffix + f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                shutil.copy2(alarm_path, backup)
                result.migrated.append(f"alarm_map.json corrected (backup: {backup.name})")
            else:
                result.created.append(str(alarm_path))
            _write_json(alarm_path, clean_alarm_map)

    # Copy bundled point-table templates into profile if docs are present.
    if project_root is not None:
        docs_dir = project_root / "docs"
        target_dir = profile_dir / "point_tables"
        if docs_dir.exists():
            for src in docs_dir.glob("*.json"):
                if "point_table" in src.name.lower() or "catl" in src.name.lower():
                    dst = target_dir / src.name
                    if not dst.exists():
                        shutil.copy2(src, dst)
                        result.created.append(str(dst))

    selfcheck_path = profile_dir / "logs" / f"startup_selfcheck_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    try:
        selfcheck_path.write_text(result.to_text(), encoding="utf-8")
    except Exception:
        pass

    return result


def install_crash_handler(log_dir: Path | None = None) -> None:
    """Install crash/exception diagnostics for source and PyInstaller builds.

    This intentionally catches more than normal Python exceptions:
    - sys.excepthook for main-thread uncaught exceptions
    - threading.excepthook for worker-thread uncaught exceptions
    - sys.unraisablehook for destructor/callback exceptions
    - faulthandler for native crashes where Python would otherwise just exit
    - Qt message handler for Qt warnings/errors before a crash
    """
    import faulthandler
    import os
    import platform
    import sys
    import threading

    if log_dir is None:
        log_dir = user_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    crash_latest = log_dir / "crash_latest.log"
    fatal_path = log_dir / "native_fault_latest.log"
    qt_path = log_dir / "qt_messages.log"
    lock = threading.RLock()

    def _write_header(f, title: str) -> None:
        f.write(f"{title}\n")
        f.write(f"{APP_NAME} v{APP_VERSION}\n")
        f.write(f"Build: {BUILD_ID}\n")
        f.write(f"Time: {datetime.now().isoformat(timespec='seconds')}\n")
        f.write(f"Python: {sys.version}\n")
        f.write(f"Platform: {platform.platform()}\n")
        f.write(f"PID: {os.getpid()}\n\n")

    def _append_crash(title: str, body_writer) -> None:
        try:
            with lock:
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                stamped = log_dir / f"app_crash_{stamp}.log"
                for path in (crash_latest, stamped):
                    with open(path, "w", encoding="utf-8") as f:
                        _write_header(f, title)
                        body_writer(f)
        except Exception:
            pass

    # Native/extension-level crashes often bypass Python traceback completely.
    try:
        fatal_file = open(fatal_path, "a", encoding="utf-8", buffering=1)
        fatal_file.write("\n\n===== faulthandler armed " + datetime.now().isoformat(timespec="seconds") + " =====\n")
        faulthandler.enable(file=fatal_file, all_threads=True)
    except Exception:
        pass

    original_hook = sys.excepthook

    def _hook(exc_type, exc_value, exc_tb):
        def _body(f):
            traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
        _append_crash("Uncaught main-thread exception", _body)
        try:
            original_hook(exc_type, exc_value, exc_tb)
        except Exception:
            pass

    sys.excepthook = _hook

    try:
        original_thread_hook = threading.excepthook

        def _thread_hook(args):
            def _body(f):
                f.write(f"Thread: {getattr(args.thread, 'name', '-') }\n\n")
                traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback, file=f)
            _append_crash("Uncaught worker-thread exception", _body)
            try:
                original_thread_hook(args)
            except Exception:
                pass

        threading.excepthook = _thread_hook
    except Exception:
        pass

    try:
        original_unraisable = getattr(sys, "unraisablehook", None)

        def _unraisable_hook(unraisable):
            def _body(f):
                f.write(f"Object: {getattr(unraisable, 'object', '-')!r}\n")
                f.write(f"Message: {getattr(unraisable, 'err_msg', '-') }\n\n")
                traceback.print_exception(unraisable.exc_type, unraisable.exc_value, unraisable.exc_traceback, file=f)
            _append_crash("Unraisable exception", _body)
            if original_unraisable:
                try:
                    original_unraisable(unraisable)
                except Exception:
                    pass

        sys.unraisablehook = _unraisable_hook
    except Exception:
        pass

    # Qt can abort the process on some GUI/thread/plugin issues without a Python traceback.
    try:
        from PySide6.QtCore import qInstallMessageHandler

        def _qt_message_handler(mode, context, message):  # noqa: ANN001 - Qt callback signature
            try:
                with lock:
                    with open(qt_path, "a", encoding="utf-8") as f:
                        f.write(
                            f"{datetime.now().isoformat(timespec='seconds')} "
                            f"mode={mode} file={getattr(context, 'file', '')} "
                            f"line={getattr(context, 'line', '')} "
                            f"function={getattr(context, 'function', '')} msg={message}\n"
                        )
            except Exception:
                pass

        qInstallMessageHandler(_qt_message_handler)
    except Exception:
        pass

