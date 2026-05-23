from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


class AlarmParser:
    """
    BMS 告警解析器。

    输入：
    - snapshot 里 alarm_0x0000 ~ alarm_0x001f

    输出：
    - active_count
    - active_alarm_text
    - active_alarm_items

    alarm_map.json 格式：
    {
      "0x0010": {
        "Bit10": "communication lost warning"
      }
    }
    """

    def __init__(self, map_path: Path | None = None) -> None:
        self.map_path = map_path or (Path.cwd() / "alarm_map.json")
        self.alarm_map: Dict[str, Dict[str, str]] = {}
        self.load()

    def load(self) -> None:
        if not self.map_path.exists():
            template = {
                "0x0000": {},
                "0x0001": {},
                "0x0002": {},
                "0x0003": {},
                "0x0004": {},
                "0x0005": {},
                "0x0006": {},
                "0x0007": {},
                "0x0008": {},
                "0x0009": {},
                "0x000a": {},
                "0x000b": {},
                "0x000c": {},
                "0x000d": {},
                "0x000e": {},
                "0x000f": {},
                "0x0010": {},
                "0x0011": {},
                "0x0012": {},
                "0x0013": {},
                "0x0014": {},
                "0x0015": {},
                "0x0016": {},
                "0x0017": {},
                "0x0018": {},
                "0x0019": {},
                "0x001a": {},
                "0x001b": {},
                "0x001c": {},
                "0x001d": {},
                "0x001e": {},
                "0x001f": {}
            }

            with open(self.map_path, "w", encoding="utf-8") as f:
                json.dump(template, f, ensure_ascii=False, indent=2)

            self.alarm_map = {}
            return

        with open(self.map_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        normalized: Dict[str, Dict[str, str]] = {}

        for addr, bit_map in raw.items():
            addr_key = addr.lower()
            normalized[addr_key] = {}

            for bit_key, text in bit_map.items():
                normalized[addr_key][bit_key.lower()] = str(text)

        self.alarm_map = normalized

    def parse_snapshot(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        active_items: List[str] = []

        for addr in range(0x0000, 0x0020):
            key = f"alarm_0x{addr:04x}"
            raw_value = snapshot.get(key, 0)

            try:
                # Accept both normal integers and strings such as "0x0004" from CSV/replay paths.
                value = int(raw_value, 0) if isinstance(raw_value, str) else int(raw_value)
            except (TypeError, ValueError):
                value = 0

            if value == 0:
                continue

            addr_key = f"0x{addr:04x}"

            for bit in range(16):
                if value & (1 << bit):
                    bit_key = f"bit{bit}"
                    alarm_name = self.alarm_map.get(addr_key, {}).get(bit_key)

                    if alarm_name:
                        active_items.append(f"{addr_key} Bit{bit}: {alarm_name}")
                    else:
                        active_items.append(f"{addr_key} Bit{bit}: Unknown")

        return {
            "active_count": len(active_items),
            "active_alarm_text": "; ".join(active_items),
            "active_alarm_items": active_items,
        }