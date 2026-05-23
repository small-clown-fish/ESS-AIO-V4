from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


_VALUE_RE = re.compile(r"^\s*([^=;]+?)\s*=\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*([^;]*)\s*$")


@dataclass(frozen=True)
class DecodedSignalValue:
    signal: str
    value: float
    unit: str = ""


class CanSemanticLookup:
    """Runtime semantic layer generated from MBD4.18.

    DBC answers: which bits make which signal and value.
    This lookup answers: what that signal means in the project: Chinese name,
    English name, MBMU/SBMU instance, ToEMS address/type, and source sheet.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else self.default_path()
        self.by_signal: Dict[str, Dict[str, Any]] = {}
        self.by_message_signal: Dict[str, Dict[str, Any]] = {}
        self.metadata: Dict[str, Any] = {}
        self._loaded = False
        self.load()

    @staticmethod
    def default_path() -> Path:
        return Path(__file__).resolve().parent / "protocols" / "catl_mbd4_18_runtime_semantic_lookup_v2.json"

    def load(self) -> None:
        if not self.path.exists():
            self._loaded = False
            return
        with self.path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        self.metadata = data.get("metadata", {}) if isinstance(data, dict) else {}
        self.by_signal = data.get("by_signal", {}) if isinstance(data, dict) and isinstance(data.get("by_signal"), dict) else {}
        self.by_message_signal = data.get("by_message_signal", {}) if isinstance(data, dict) and isinstance(data.get("by_message_signal"), dict) else {}
        self._loaded = True

    @property
    def loaded(self) -> bool:
        return self._loaded

    def lookup(self, signal_name: str, message_name: str = "") -> Optional[Dict[str, Any]]:
        signal_name = str(signal_name or "").strip()
        message_name = str(message_name or "").strip()
        if not signal_name:
            return None
        if message_name:
            item = self.by_message_signal.get(f"{message_name}::{signal_name}")
            if item:
                return item
        return self.by_signal.get(signal_name)

    def parse_decoded(self, decoded: str) -> list[DecodedSignalValue]:
        values: list[DecodedSignalValue] = []
        for part in str(decoded or "").split(";"):
            m = _VALUE_RE.match(part)
            if not m:
                continue
            try:
                values.append(DecodedSignalValue(m.group(1).strip(), float(m.group(2)), m.group(3).strip()))
            except Exception:
                continue
        return values

    def short_label(self, signal_name: str, message_name: str = "") -> str:
        item = self.lookup(signal_name, message_name) or {}
        cn = str(item.get("chinese_name") or "").strip()
        obj = self.object_label(item)
        ems = str(item.get("ems_address") or "").strip()
        bits = [x for x in [obj, cn, signal_name, f"EMS {ems}" if ems else ""] if x]
        return " / ".join(bits)

    def object_label(self, item: Dict[str, Any]) -> str:
        typ = str(item.get("object_type") or "").strip()
        inst = str(item.get("object_instance") or "").strip()
        if typ and inst:
            return f"{typ}{inst}"
        return typ or ""

    def enrich_decoded_text(self, decoded: str, message_name: str = "") -> str:
        parts: list[str] = []
        for value in self.parse_decoded(decoded):
            item = self.lookup(value.signal, message_name) or {}
            cn = str(item.get("chinese_name") or "").strip()
            obj = self.object_label(item)
            ems = str(item.get("ems_address") or "").strip()
            prefix = " / ".join(x for x in [obj, cn, value.signal] if x)
            suffix = f"{value.value:g}{value.unit}"
            if ems:
                suffix += f" [EMS {ems}]"
            parts.append(f"{prefix}={suffix}" if prefix else f"{value.signal}={suffix}")
        return "; ".join(parts)

    def verbose_lines(self, decoded: str, message_name: str = "") -> list[str]:
        lines: list[str] = []
        for value in self.parse_decoded(decoded):
            item = self.lookup(value.signal, message_name) or {}
            cn = str(item.get("chinese_name") or "-").strip() or "-"
            en = str(item.get("english_name") or "-").strip() or "-"
            obj = self.object_label(item) or "-"
            ems = str(item.get("ems_address") or "-").strip() or "-"
            ems_name = str(item.get("ems_name") or "-").strip() or "-"
            ems_type = str(item.get("ems_type") or "-").strip() or "-"
            sheet = str(item.get("source_sheet") or "-").strip() or "-"
            lines.extend([
                f"{value.signal} = {value.value:g}{value.unit}",
                f"  中文名: {cn}",
                f"  English: {en}",
                f"  对象: {obj}",
                f"  EMS点号: {ems}",
                f"  EMS名称/类型: {ems_name} / {ems_type}",
                f"  来源Sheet: {sheet}",
            ])
        return lines
