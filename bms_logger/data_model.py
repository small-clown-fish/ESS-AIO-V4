from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Mapping


CANONICAL_POINTS = [
    "timestamp",
    "bms_heartbeat",
    "bms_power_on",
    "bms_status",
    "number_of_racks",
    "system_voltage",
    "system_current",
    "soc",
    "soh",
    "max_cell_voltage",
    "min_cell_voltage",
    "avg_cell_voltage",
    "max_cell_temperature",
    "min_cell_temperature",
    "avg_cell_temperature",
    "max_charge_current_allowed",
    "max_discharge_current_allowed",
    "max_charge_power_allowed",
    "max_discharge_power_allowed",
    "system_power",
]

META_KEYS = {"points", "raw", "point_meta", "driver", "driver_key", "device_type", "_data_model_version"}


@dataclass
class PointValue:
    key: str
    value: Any
    label: str = ""
    unit: str = ""
    address: str = ""
    quality: str = "good"
    source: str = "driver"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "label": self.label or self.key,
            "unit": self.unit,
            "address": self.address,
            "quality": self.quality,
            "source": self.source,
        }


@dataclass
class TelemetryFrame:
    device_name: str
    timestamp: str
    points: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)
    point_meta: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    driver_key: str = "unknown"
    device_type: str = "BMS"

    def to_snapshot(self) -> Dict[str, Any]:
        """Return a backward-compatible flat snapshot plus v3 point model."""
        snapshot: Dict[str, Any] = {}
        snapshot.update(self.points)
        snapshot["timestamp"] = self.timestamp
        snapshot["points"] = dict(self.points)
        snapshot["raw"] = dict(self.raw)
        snapshot["point_meta"] = dict(self.point_meta)
        snapshot["driver_key"] = self.driver_key
        snapshot["device_type"] = self.device_type
        snapshot["_data_model_version"] = "3.0.2"
        return snapshot


def _safe_timestamp(raw: Mapping[str, Any] | None = None) -> str:
    if raw:
        ts = raw.get("timestamp")
        if ts:
            return str(ts)
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize_telemetry_snapshot(
    raw_snapshot: Mapping[str, Any] | None,
    *,
    device_name: str = "",
    driver_key: str = "unknown",
    device_type: str = "BMS",
    point_catalog: Mapping[str, Mapping[str, Any]] | None = None,
) -> Dict[str, Any] | None:
    """Normalize driver output into the v3 point data model.

    Compatibility rule: all normal points are also kept as flat top-level keys so
    v1/v2 UI, strategy, alarm and CSV logic keep working while new screens can
    consume snapshot["points"] and snapshot["point_meta"].
    """
    if raw_snapshot is None:
        return None

    raw = dict(raw_snapshot)
    if "points" in raw and isinstance(raw.get("points"), dict):
        points = dict(raw["points"])
        for key, value in raw.items():
            if key not in META_KEYS and key not in points:
                points[key] = value
    else:
        points = {key: value for key, value in raw.items() if key not in META_KEYS}

    # Timestamp is metadata, not a normal point, but keep compatibility flat key.
    timestamp = _safe_timestamp(raw)
    points.pop("timestamp", None)

    catalog = dict(point_catalog or raw.get("point_meta", {}) or {})
    point_meta: Dict[str, Dict[str, Any]] = {}
    for key in points:
        meta = dict(catalog.get(key, {})) if isinstance(catalog.get(key, {}), Mapping) else {}
        meta.setdefault("label", meta.get("name", key))
        meta.setdefault("unit", "")
        meta.setdefault("address", "")
        point_meta[key] = meta

    frame = TelemetryFrame(
        device_name=device_name,
        timestamp=timestamp,
        points=points,
        raw=raw,
        point_meta=point_meta,
        driver_key=str(raw.get("driver_key", driver_key)),
        device_type=str(raw.get("device_type", device_type)),
    )
    return frame.to_snapshot()


def flatten_snapshot_for_csv(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    """Flatten v3 snapshots for CSV output.

    Nested structures are excluded except point values, which are already flat.
    Unknown/dynamic points are included automatically.
    """
    row: Dict[str, Any] = {}
    points = snapshot.get("points")
    if isinstance(points, Mapping):
        row.update(points)

    for key, value in snapshot.items():
        if key in {"raw", "point_meta", "points"}:
            continue
        if isinstance(value, (dict, list, tuple, set)):
            continue
        row[key] = value

    if "timestamp" not in row:
        row["timestamp"] = _safe_timestamp(snapshot)
    return row
