from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from openpyxl import Workbook
from openpyxl.styles import Font

from .models import SampleRecord


HEADERS = [
    "timestamp",
    "device_name",
    "host",
    "port",
    "unit_id",
    "soc_pct",
    "voltage_v",
    "current_a",
    "status",
    "error",
]


def _sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]+', "_", name).strip() or "device"


def _write_records_to_workbook(records: Iterable[SampleRecord], output_path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "BMS Data"

    ws.append(HEADERS)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for record in records:
        ws.append(record.to_row())

    widths = {
        "A": 24,
        "B": 20,
        "C": 18,
        "D": 10,
        "E": 10,
        "F": 10,
        "G": 12,
        "H": 12,
        "I": 12,
        "J": 40,
    }
    for column, width in widths.items():
        ws.column_dimensions[column].width = width

    wb.save(output_path)
    return output_path


def export_samples_to_excel(records: Iterable[SampleRecord], output_path: str | Path) -> Path:
    path = Path(output_path)
    return _write_records_to_workbook(records, path)


def export_samples_to_device_files(records: Iterable[SampleRecord], output_dir: str | Path) -> list[Path]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)

    grouped: dict[str, list[SampleRecord]] = defaultdict(list)
    for record in records:
        grouped[record.device_name].append(record)

    output_paths: list[Path] = []
    for device_name, device_records in grouped.items():
        if not device_records:
            continue
        first_ts = device_records[0].timestamp.strftime("%Y%m%d_%H%M%S")
        last_ts = device_records[-1].timestamp.strftime("%Y%m%d_%H%M%S")
        safe_name = _sanitize_filename(device_name)
        file_name = f"{safe_name}_{first_ts}_{last_ts}.xlsx"
        output_paths.append(_write_records_to_workbook(device_records, directory / file_name))

    return output_paths
