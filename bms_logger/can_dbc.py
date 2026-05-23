from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

@dataclass
class SignalDef:
    name: str
    start_bit: int
    length: int
    byte_order: int
    signed: bool
    factor: float
    offset: float
    unit: str = ""

@dataclass
class MessageDef:
    frame_id: int
    name: str
    dlc: int
    sender: str
    signals: List[SignalDef] = field(default_factory=list)

class Dbc:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.messages: Dict[int, MessageDef] = {}
        self._parse()

    def _parse(self) -> None:
        current: Optional[MessageDef] = None
        sig_re = re.compile(r"\s*SG_\s+(\w+)\s*:\s*(\d+)\|(\d+)@(\d)([+-])\s+\(([^,]+),([^\)]+)\).*?\"([^\"]*)\"")
        with self.path.open("r", encoding="latin-1", errors="ignore") as f:
            for line in f:
                if line.startswith("BO_ "):
                    parts = line.split()
                    if len(parts) >= 5:
                        raw_id = int(parts[1])
                        frame_id = raw_id & 0x1FFFFFFF
                        current = MessageDef(frame_id, parts[2].rstrip(":"), int(parts[3]), parts[4])
                        self.messages[frame_id] = current
                    continue
                if current and line.lstrip().startswith("SG_ "):
                    m = sig_re.match(line)
                    if not m:
                        continue
                    current.signals.append(SignalDef(
                        name=m.group(1), start_bit=int(m.group(2)), length=int(m.group(3)),
                        byte_order=int(m.group(4)), signed=(m.group(5) == "-"),
                        factor=float(m.group(6)), offset=float(m.group(7)), unit=m.group(8)
                    ))

    def decode(self, frame_id: int, data: bytes) -> Dict[str, float | int]:
        msg = self.messages.get(frame_id & 0x1FFFFFFF)
        if not msg:
            return {}
        return {s.name: self.decode_signal(s, data) for s in msg.signals}

    @staticmethod
    def decode_signal(sig: SignalDef, data: bytes) -> float | int:
        # Full support for Intel signals used by CATL DBC. Motorola falls back to a simple big-endian slice.
        if sig.byte_order == 1:
            raw_all = int.from_bytes(data, "little", signed=False)
            raw = (raw_all >> sig.start_bit) & ((1 << sig.length) - 1)
        else:
            raw_all = int.from_bytes(data, "big", signed=False)
            shift = max(0, len(data) * 8 - sig.start_bit - sig.length)
            raw = (raw_all >> shift) & ((1 << sig.length) - 1)
        if sig.signed and sig.length and raw & (1 << (sig.length - 1)):
            raw -= 1 << sig.length
        val = raw * sig.factor + sig.offset
        return int(val) if float(val).is_integer() else val
