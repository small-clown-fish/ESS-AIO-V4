from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .can_dbc import Dbc
from .protocol_mapping import load_mapping
from .packet_analyzer import PacketAnalyzer

ASC_RE = re.compile(r"^\s*(?P<t>\d+(?:\.\d+)?)\s+\d+\s+(?P<id>[0-9A-Fa-f]+)x?\s+\w+\s+d\s+(?P<dlc>\d+)\s+(?P<data>(?:[0-9A-Fa-f]{2}\s*)+)")

@dataclass
class CanEvent:
    time: float
    can_id: int
    values: Dict[str, Any]

@dataclass
class ModbusEvent:
    time: float
    address: int
    raw: int


def parse_asc(path: str | Path, dbc: Dbc, only_ids: set[int] | None = None) -> List[CanEvent]:
    events: List[CanEvent] = []
    with Path(path).open("r", encoding="latin-1", errors="ignore") as f:
        for line in f:
            m = ASC_RE.match(line)
            if not m:
                continue
            can_id = int(m.group("id"), 16) & 0x1FFFFFFF
            if only_ids and can_id not in only_ids:
                continue
            data = bytes(int(x, 16) for x in m.group("data").split()[: int(m.group("dlc"))])
            vals = dbc.decode(can_id, data)
            if vals:
                events.append(CanEvent(float(m.group("t")), can_id, vals))
    return events


def _pick(row: Dict[str, str], names: Iterable[str]) -> str | None:
    low = {k.lower(): v for k, v in row.items()}
    for name in names:
        if name.lower() in low:
            return low[name.lower()]
    return None


def parse_wireshark_modbus_csv(path: str | Path) -> List[ModbusEvent]:
    """Parse Wireshark/tshark CSV exports.

    Expected columns can be named flexibly, for example:
    frame.time_relative, modbus.regnum / modbus.reference_num / address,
    modbus.regval_uint16 / modbus.regval / value.
    """
    events: List[ModbusEvent] = []
    with Path(path).open("r", encoding="utf-8-sig", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            t = _pick(row, ["frame.time_relative", "time", "timestamp"])
            a = _pick(row, ["modbus.regnum", "modbus.reference_num", "address", "register"])
            v = _pick(row, ["modbus.regval_uint16", "modbus.regval", "value", "raw"])
            if t is None or a is None or v is None:
                continue
            try:
                addr = int(str(a), 0)
                raw = int(str(v).split(",")[0], 0)
                events.append(ModbusEvent(float(t), addr, raw))
            except ValueError:
                continue
    return events



def parse_modbus_capture(path: str | Path) -> List[ModbusEvent]:
    """Parse Modbus evidence from either Wireshark CSV or raw pcap/pcapng.

    CSV mode accepts flexible Wireshark/tshark column names. Raw capture mode parses
    Modbus TCP on port 502 directly, pairs read requests with read responses, and emits
    one ModbusEvent per register value.
    """
    path = Path(path)
    if path.suffix.lower() in {".pcap", ".pcapng", ".cap"}:
        return parse_modbus_pcap(path)
    return parse_wireshark_modbus_csv(path)


def _parse_u16_values(data: bytes, count: int | None = None) -> List[int]:
    values: List[int] = []
    limit = len(data) // 2 if count is None else min(count, len(data) // 2)
    for i in range(limit):
        values.append((data[2 * i] << 8) | data[2 * i + 1])
    return values


def parse_modbus_pcap(path: str | Path) -> List[ModbusEvent]:
    """Extract register values from Modbus TCP .pcap/.pcapng captures.

    Supported function codes:
    - 0x03/0x04 read holding/input registers: values are emitted from the response,
      using the starting address captured from the paired request.
    - 0x06 write single register: value is emitted from the request.
    - 0x10 write multiple registers: values are emitted from the request.
    """
    analyzer = PacketAnalyzer()
    raw = Path(path).read_bytes()
    packets = analyzer._read_capture_packets(raw)
    base_ts = packets[0][0] if packets else 0.0
    events: List[ModbusEvent] = []
    pending_reads: Dict[tuple[int, int, str, str], tuple[int, int, float, int]] = {}

    for ts, frame in packets:
        rel_ts = float(ts - base_ts)
        parsed = analyzer._parse_frame(frame)
        if parsed is None:
            continue
        ip, tcp, payload = parsed
        if tcp["sport"] != analyzer.MODBUS_PORT and tcp["dport"] != analyzer.MODBUS_PORT:
            continue
        if len(payload) < 8:
            continue
        transaction_id = int.from_bytes(payload[0:2], "big")
        protocol_id = int.from_bytes(payload[2:4], "big")
        unit_id = payload[6]
        function_code = payload[7]
        if protocol_id != 0 or function_code & 0x80:
            continue
        pdu = payload[7:]
        is_response = tcp["sport"] == analyzer.MODBUS_PORT

        if not is_response:
            # Request from EMS/client to BMS/server.
            if function_code in (3, 4) and len(pdu) >= 5:
                addr = int.from_bytes(pdu[1:3], "big")
                qty = int.from_bytes(pdu[3:5], "big")
                pending_reads[(transaction_id, unit_id, ip["src"], ip["dst"])] = (addr, qty, rel_ts, function_code)
            elif function_code == 6 and len(pdu) >= 5:
                addr = int.from_bytes(pdu[1:3], "big")
                raw_val = int.from_bytes(pdu[3:5], "big")
                events.append(ModbusEvent(rel_ts, addr, raw_val))
            elif function_code == 16 and len(pdu) >= 6:
                addr = int.from_bytes(pdu[1:3], "big")
                qty = int.from_bytes(pdu[3:5], "big")
                byte_count = pdu[5]
                value_bytes = pdu[6:6 + byte_count]
                for offset, raw_val in enumerate(_parse_u16_values(value_bytes, qty)):
                    events.append(ModbusEvent(rel_ts, addr + offset, raw_val))
        else:
            # Response from BMS/server to EMS/client. Pair with read request to recover address.
            if function_code in (3, 4) and len(pdu) >= 2:
                key = (transaction_id, unit_id, ip["dst"], ip["src"])
                req = pending_reads.pop(key, None)
                if req is None:
                    continue
                start_addr, qty, _req_ts, _req_fc = req
                byte_count = pdu[1]
                value_bytes = pdu[2:2 + byte_count]
                for offset, raw_val in enumerate(_parse_u16_values(value_bytes, qty)):
                    events.append(ModbusEvent(rel_ts, start_addr + offset, raw_val))
    return events

def correlate(asc_path: str | Path, modbus_capture_path: str | Path, dbc_path: str | Path, mapping_path: str | Path, tolerance_s: float = 0.5) -> List[Dict[str, Any]]:
    mapping = load_mapping(mapping_path)
    dbc = Dbc(dbc_path)
    ids = {int(m["can_id"], 16) for m in mapping}
    can_events = parse_asc(asc_path, dbc, ids)
    modbus_events = parse_modbus_capture(modbus_capture_path)
    mb_by_addr: Dict[int, List[ModbusEvent]] = {}
    for e in modbus_events:
        mb_by_addr.setdefault(e.address, []).append(e)
    rows: List[Dict[str, Any]] = []
    for m in mapping:
        addr = int(m["modbus_address"], 16)
        sig = m["can_signal"]
        can_id = int(m["can_id"], 16)
        candidates = [e for e in can_events if e.can_id == can_id and sig in e.values]
        for ce in candidates:
            near = min(mb_by_addr.get(addr, []), key=lambda me: abs(me.time - ce.time), default=None)
            if not near or abs(near.time - ce.time) > tolerance_s:
                continue
            can_val = ce.values[sig]
            mb_val = near.raw * float(m.get("modbus_scale", 1)) + float(m.get("modbus_offset", 0))
            rows.append({
                "time_can": ce.time, "time_modbus": near.time, "delta_s": round(near.time - ce.time, 6),
                "can_id": m["can_id"], "can_signal": sig, "can_value": can_val,
                "modbus_address": m["modbus_address"], "modbus_raw": near.raw, "modbus_value": mb_val,
                "abs_diff": abs(float(can_val) - float(mb_val)) if isinstance(can_val, (int, float)) else None,
            })
    return rows


def write_report(rows: List[Dict[str, Any]], out_csv: str | Path) -> None:
    Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
    fields = ["time_can", "time_modbus", "delta_s", "can_id", "can_signal", "can_value", "modbus_address", "modbus_raw", "modbus_value", "abs_diff"]
    with Path(out_csv).open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(rows)
