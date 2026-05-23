from __future__ import annotations

import csv
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Iterable

from .data_model import CANONICAL_POINTS, flatten_snapshot_for_csv


class CsvRecorder:
    """Dynamic CSV recorder.

    v3 behavior:
    - Keeps v1/v2 canonical fields first for compatibility.
    - Adds any driver-provided points automatically.
    - If a new point appears later, it rotates to a new CSV segment so headers
      stay valid and old files remain readable.
    """

    BASE_FIELDNAMES = list(CANONICAL_POINTS)
    META_FIELDNAMES = ["driver_key", "device_type", "_data_model_version"]

    def __init__(self, output_dir: Path, device_name: str) -> None:
        self.output_dir = Path(output_dir)
        self.device_name = device_name
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.current_date: Optional[str] = None
        self.current_file_path: Optional[Path] = None
        self.current_file = None
        self.writer: Optional[csv.DictWriter] = None
        self.fieldnames: list[str] = []
        self._write_count = 0
        self._schema_version = 1
        self._write_blocked_until = 0.0

    def _build_file_path(self, date_str: str) -> Path:
        suffix = "" if self._schema_version <= 1 else f"_schema{self._schema_version}"
        filename = f"{self.device_name}_{date_str}{suffix}.csv"
        return self.output_dir / filename

    def _ordered_fields(self, row: Dict[str, Any]) -> list[str]:
        fields: list[str] = []
        for key in [*self.BASE_FIELDNAMES, *self.META_FIELDNAMES]:
            if key in row and key not in fields:
                fields.append(key)
        for key in sorted(row.keys()):
            if key not in fields:
                fields.append(key)
        if "timestamp" not in fields:
            fields.insert(0, "timestamp")
        return fields

    def _open_for_date(self, date_str: str, fieldnames: Iterable[str]) -> None:
        if self.current_file:
            try:
                self.current_file.flush()
            except Exception:
                pass
            self.current_file.close()
            self.current_file = None
            self.writer = None

        self.current_date = date_str
        self.fieldnames = list(fieldnames)
        self.current_file_path = self._build_file_path(date_str)
        file_exists = self.current_file_path.exists()

        self.current_file = open(self.current_file_path, "a", newline="", encoding="utf-8")
        self.writer = csv.DictWriter(self.current_file, fieldnames=self.fieldnames, extrasaction="ignore")

        if not file_exists or self.current_file_path.stat().st_size == 0:
            self.writer.writeheader()
            self.current_file.flush()

    def write_row(self, snapshot: Dict[str, Any]) -> None:
        if time.time() < self._write_blocked_until:
            return
        try:
            self._write_row_impl(snapshot)
        except (PermissionError, OSError):
            # Usually means the CSV is opened/locked by Excel or AV scanning.
            # Drop a few rows and retry later instead of blocking sampling.
            self._write_blocked_until = time.time() + 10.0
            try:
                if self.current_file:
                    self.current_file.close()
            except Exception:
                pass
            self.current_file = None
            self.writer = None

    def _write_row_impl(self, snapshot: Dict[str, Any]) -> None:
        row = flatten_snapshot_for_csv(snapshot)
        timestamp = str(row.get("timestamp", "")) or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row["timestamp"] = timestamp
        date_part = timestamp.split(" ")[0].replace("-", "")

        desired_fields = self._ordered_fields(row)
        field_changed = bool(self.fieldnames) and any(key not in self.fieldnames for key in desired_fields)
        if field_changed:
            self._schema_version += 1

        if self.current_date != date_part or self.writer is None or field_changed:
            self._open_for_date(date_part, desired_fields)

        assert self.writer is not None
        assert self.current_file is not None

        self.writer.writerow(row)
        self._write_count += 1
        # Buffered flush: avoid forcing Windows/Defender to scan the CSV file on
        # every sample. close() still flushes all pending data.
        if self._write_count >= 100:
            self.current_file.flush()
            self._write_count = 0

    def close(self) -> None:
        if self.current_file:
            try:
                self.current_file.flush()
            except Exception:
                pass

            self.current_file.close()
            self.current_file = None
            self.writer = None


class AlarmRecorder:
    """Per-device alarm CSV recorder."""

    FIELDNAMES = [
        "timestamp",
        "device_name",
        "alarm_hex",
        "alarm_active_count",
        "active_alarm_text",
    ]

    def __init__(self, output_dir: Path, device_name: str) -> None:
        self.output_dir = Path(output_dir)
        self.device_name = device_name
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.current_date: Optional[str] = None
        self.current_file_path: Optional[Path] = None
        self.current_file = None
        self.writer: Optional[csv.DictWriter] = None
        self._write_count = 0
        self._write_blocked_until = 0.0

    def _build_file_path(self, date_str: str) -> Path:
        filename = f"{self.device_name}_alarm_{date_str}.csv"
        return self.output_dir / filename

    def _open_for_date(self, date_str: str) -> None:
        if self.current_file:
            self.current_file.close()
            self.current_file = None
            self.writer = None

        self.current_date = date_str
        self.current_file_path = self._build_file_path(date_str)
        file_exists = self.current_file_path.exists()

        self.current_file = open(self.current_file_path, "a", newline="", encoding="utf-8")
        self.writer = csv.DictWriter(self.current_file, fieldnames=self.FIELDNAMES)

        if not file_exists or self.current_file_path.stat().st_size == 0:
            self.writer.writeheader()
            self.current_file.flush()

    def write_row(self, device_name: str, snapshot: Dict[str, Any], parsed_alarm: Dict[str, Any]) -> None:
        if time.time() < self._write_blocked_until:
            return
        try:
            self._write_row_impl(device_name, snapshot, parsed_alarm)
        except (PermissionError, OSError):
            self._write_blocked_until = time.time() + 10.0
            try:
                if self.current_file:
                    self.current_file.close()
            except Exception:
                pass
            self.current_file = None
            self.writer = None

    def _write_row_impl(self, device_name: str, snapshot: Dict[str, Any], parsed_alarm: Dict[str, Any]) -> None:
        timestamp = str(snapshot.get("timestamp", ""))
        if not timestamp:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        date_part = timestamp.split(" ")[0].replace("-", "")

        if self.current_date != date_part or self.writer is None:
            self._open_for_date(date_part)

        alarm_values = []
        points = snapshot.get("points", {}) if isinstance(snapshot.get("points"), dict) else {}
        for addr in range(0x0000, 0x0020):
            key = f"alarm_0x{addr:04x}"
            try:
                value = int(snapshot.get(key, points.get(key, 0)))
            except (TypeError, ValueError):
                value = 0
            alarm_values.append(value)

        alarm_hex = "-".join(f"{v:04x}" for v in alarm_values)

        row = {
            "timestamp": timestamp,
            "device_name": device_name,
            "alarm_hex": alarm_hex,
            "alarm_active_count": parsed_alarm.get("active_count", 0),
            "active_alarm_text": parsed_alarm.get("active_alarm_text", ""),
        }

        assert self.writer is not None
        assert self.current_file is not None

        self.writer.writerow(row)

        self._write_count += 1
        # Buffered flush: avoid forcing Windows/Defender to scan the CSV file on
        # every sample. close() still flushes all pending data.
        if self._write_count >= 100:
            self.current_file.flush()
            self._write_count = 0

    def close(self) -> None:
        if self.current_file:
            try:
                self.current_file.flush()
            except Exception:
                pass

            self.current_file.close()
            self.current_file = None
            self.writer = None
