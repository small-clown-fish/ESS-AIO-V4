from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from .paths import resource_path

PROTOCOL_DIR = resource_path("bms_logger/protocols")

@dataclass(frozen=True)
class PointDef:
    key: str
    address: int
    description: str
    scale: float = 1.0
    offset: float = 0.0
    access: str = "R"
    section: str = ""
    raw: Dict[str, Any] | None = None


def _to_float(value: Any, default: float = 1.0) -> float:
    if value is None:
        return default
    text = str(value).strip()
    if not text or text.upper() in {"NA", "N/A"}:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def parse_addr(text: Any) -> Optional[int]:
    if text is None:
        return None
    m = re.search(r"0x([0-9a-fA-F]+)", str(text))
    if not m:
        return None
    return int(m.group(1), 16)


def normalize_key(text: str) -> str:
    text = text.lower().replace(".", " ")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "point"


class PointTable:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        with self.path.open("r", encoding="utf-8") as f:
            self.data = json.load(f)
        self.metadata = self.data.get("metadata", {})
        self.points: Dict[str, PointDef] = {}
        self.by_address: Dict[int, PointDef] = {}
        self._load_points()

    def _load_points(self) -> None:
        for section, rows in self.data.get("sections", {}).items():
            if not isinstance(rows, list):
                continue
            for row in rows:
                addr = parse_addr(row.get("register_address"))
                if addr is None:
                    continue
                desc = str(row.get("description") or row.get("variable_description") or "").strip()
                if not desc:
                    desc = f"register_0x{addr:04x}"
                key_base = normalize_key(desc)
                key = key_base
                i = 2
                while key in self.points:
                    key = f"{key_base}_{i}"
                    i += 1
                p = PointDef(
                    key=key,
                    address=addr,
                    description=desc,
                    scale=_to_float(row.get("ratio_factor"), 1.0),
                    offset=_to_float(row.get("offset"), 0.0),
                    access=str(row.get("access") or "R"),
                    section=section,
                    raw=row,
                )
                self.points[key] = p
                self.by_address.setdefault(addr, p)

    def get_by_address(self, address: int) -> Optional[PointDef]:
        return self.by_address.get(address)

    def get(self, key: str) -> Optional[PointDef]:
        return self.points.get(key)

    def catalog(self) -> Dict[str, Dict[str, Any]]:
        return {
            key: {
                "label": p.description,
                "address": f"0x{p.address:04x}",
                "scale": p.scale,
                "offset": p.offset,
                "access": p.access,
                "section": p.section,
            }
            for key, p in sorted(self.points.items(), key=lambda kv: kv[1].address)
        }


def resolve_point_table_path(
    protocol: str | None = None,
    explicit_path: str | None = None,
    profile: str | None = None,
) -> Path:
    """Resolve BMS point-table path.

    Preferred v3.11+ source:
        bms_profiles/<profile>/bms_register_map.json

    Legacy fallback:
        bms_logger/protocols/catl_*_point_table.json
    """
    if explicit_path:
        return Path(explicit_path)

    profile_key = (profile or "").strip()
    if not profile_key:
        proto = (protocol or "").lower()
        if "v17" in proto:
            profile_key = "catl_v17"
        elif "v22" in proto or not proto:
            profile_key = "catl_v22"

    if profile_key:
        profile_path = resource_path("bms_profiles") / profile_key / "bms_register_map.json"
        if profile_path.exists():
            return profile_path

    protocol = (protocol or "catl_v22_bms").lower()
    if "v17" in protocol:
        return PROTOCOL_DIR / "catl_v17_point_table.json"
    return PROTOCOL_DIR / "catl_teners_tenerx_0_5p_v22_point_table.json"
