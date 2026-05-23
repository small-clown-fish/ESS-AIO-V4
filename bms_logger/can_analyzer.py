from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import csv
import json
import re
import struct


@dataclass
class CanFrameRecord:
    index: int
    timestamp: float
    channel: str
    can_id: str
    dlc: int
    data: str
    direction: str = ""
    frame_type: str = "Data"
    message_name: str = ""
    frequency_hz: str = ""
    decoded: str = ""
    semantic_decoded: str = ""
    status: str = "OK"
    raw: str = ""

    def to_row(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CanIdStat:
    can_id: str
    message_name: str
    count: int
    first_ts: float
    last_ts: float
    avg_period_ms: str
    frequency_hz: str
    dlc_set: str

    def to_row(self) -> Dict[str, Any]:
        return asdict(self)


class CanAnalyzer:
    """Lightweight CAN log analyzer for field diagnostics.

    Supported text inputs:
    - Linux candump: `(1690000000.123456) can0 18FF50E5#11223344`
    - candump compact: `can0 18FF50E5 [8] 11 22 33 44 55 66 77 88`
    - Vector ASC-like rows containing timestamp, channel, id, Rx/Tx, d, dlc, bytes
    - CSV files with columns such as timestamp/time, channel, id/can_id, data/bytes

    Supported pcap:
    - Classic PCAP with Linux SocketCAN linktype 227 (common Wireshark SocketCAN capture).

    Mapping support:
    - DBC files: BO_ / SG_ message and signal definitions. Intel/little-endian signals are fully supported; Motorola/big-endian is supported for common byte-aligned and field cases.
    - JSON fallback format:
      {
        "messages": {"0x18FF50E5": "BMS_Status"},
        "signals": {
          "0x18FF50E5": [
            {"name":"voltage", "start_byte":0, "length":2, "endian":"big", "scale":0.1, "offset":0, "unit":"V"}
          ]
        }
      }
    """

    SOCKETCAN_LINKTYPE = 227

    def analyze(self, path: str | Path, mapping_path: str | Path | None = None) -> Tuple[List[CanFrameRecord], List[CanIdStat]]:
        path = Path(path)
        mapping = self._load_mapping(mapping_path)
        if path.suffix.lower() in {".pcap", ".pcapng"}:
            records = self._analyze_capture(path, mapping)
        elif path.suffix.lower() == ".csv":
            records = self._analyze_csv(path, mapping)
        else:
            records = self._analyze_text(path, mapping)
        stats = self.compute_stats(records)
        freq_by_id = {stat.can_id.upper(): stat.frequency_hz for stat in stats}
        for rec in records:
            rec.frequency_hz = freq_by_id.get(rec.can_id.upper(), "")
        return records, stats

    def export_records_csv(self, records: List[CanFrameRecord], path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = list(CanFrameRecord.__dataclass_fields__.keys())
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for record in records:
                writer.writerow(record.to_row())

    def export_stats_csv(self, stats: List[CanIdStat], path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = list(CanIdStat.__dataclass_fields__.keys())
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for stat in stats:
                writer.writerow(stat.to_row())

    def compute_stats(self, records: List[CanFrameRecord]) -> List[CanIdStat]:
        by_id: Dict[str, List[CanFrameRecord]] = {}
        for rec in records:
            by_id.setdefault(rec.can_id.upper(), []).append(rec)
        stats: List[CanIdStat] = []
        for can_id, items in sorted(by_id.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            times = [r.timestamp for r in items]
            dlc_set = sorted({r.dlc for r in items})
            first_ts = min(times) if times else 0.0
            last_ts = max(times) if times else 0.0
            if len(times) >= 2 and last_ts > first_ts:
                avg_period = (last_ts - first_ts) * 1000 / (len(times) - 1)
                frequency = 1000 / avg_period if avg_period > 0 else 0.0
                avg_period_text = f"{avg_period:.2f}"
                frequency_text = f"{frequency:.2f}"
            else:
                avg_period_text = "-"
                frequency_text = "-"
            message_name = next((r.message_name for r in items if r.message_name), "")
            stats.append(CanIdStat(
                can_id=can_id,
                message_name=message_name,
                count=len(items),
                first_ts=first_ts,
                last_ts=last_ts,
                avg_period_ms=avg_period_text,
                frequency_hz=frequency_text,
                dlc_set=",".join(str(v) for v in dlc_set),
            ))
        return stats

    # =====================
    # Text / CSV parsers
    # =====================
    def _analyze_text(self, path: Path, mapping: Dict[str, Any]) -> List[CanFrameRecord]:
        records: List[CanFrameRecord] = []
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            rec = self._parse_text_line(line, len(records) + 1, mapping)
            if rec is not None:
                records.append(rec)
        return records

    def _analyze_csv(self, path: Path, mapping: Dict[str, Any]) -> List[CanFrameRecord]:
        records: List[CanFrameRecord] = []
        with path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
            sample = f.read(4096)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample)
            except Exception:
                dialect = csv.excel
            reader = csv.DictReader(f, dialect=dialect)
            if reader.fieldnames:
                for row in reader:
                    rec = self._parse_csv_row(row, len(records) + 1, mapping)
                    if rec is not None:
                        records.append(rec)
            else:
                f.seek(0)
                for raw_line in f:
                    rec = self._parse_text_line(raw_line, len(records) + 1, mapping)
                    if rec is not None:
                        records.append(rec)
        return records

    def _parse_csv_row(self, row: Dict[str, str], index: int, mapping: Dict[str, Any]) -> Optional[CanFrameRecord]:
        lower = {str(k).strip().lower(): v for k, v in row.items()}
        ts_text = self._first(lower, ["timestamp", "time", "ts", "date time"])
        id_text = self._first(lower, ["can_id", "id", "identifier", "arbitration_id"])
        data_text = self._first(lower, ["data", "payload", "bytes", "data bytes"])
        channel = self._first(lower, ["channel", "bus", "interface"])
        direction = self._first(lower, ["direction", "dir", "rx/tx"])
        dlc_text = self._first(lower, ["dlc", "len", "length"])
        if not id_text or not data_text:
            return None
        timestamp = self._parse_float(ts_text, default=float(index - 1))
        can_id = self._normalize_can_id(id_text)
        data_bytes = self._parse_data_bytes(data_text)
        dlc = int(dlc_text) if str(dlc_text).strip().isdigit() else len(data_bytes)
        message_name, decoded = self._decode_with_mapping(can_id, data_bytes, mapping)
        return CanFrameRecord(index, timestamp, channel or "-", can_id, dlc, self._bytes_to_hex(data_bytes), direction, "Data", message_name=message_name, decoded=decoded, raw=str(row))

    def _parse_text_line(self, line: str, index: int, mapping: Dict[str, Any]) -> Optional[CanFrameRecord]:
        raw = line.strip()
        if not raw or raw.startswith("//") or raw.startswith("#"):
            return None

        # candump: (1690000000.123456) can0 18FF50E5#1122334455667788
        m = re.search(r"\((?P<ts>\d+(?:\.\d+)?)\)\s+(?P<ch>\S+)\s+(?P<id>[0-9A-Fa-f]+)#(?P<data>[0-9A-Fa-f]*)", raw)
        if m:
            return self._make_record(index, m.group("ts"), m.group("ch"), m.group("id"), m.group("data"), "", raw, mapping)

        # candump -L / compact: can0 18FF50E5 [8] 11 22 ...
        m = re.search(r"(?P<ch>can\S*|vcan\S*)\s+(?P<id>[0-9A-Fa-f]+)\s+\[(?P<dlc>\d+)\]\s+(?P<data>(?:[0-9A-Fa-f]{2}\s*)+)", raw)
        if m:
            return self._make_record(index, str(index - 1), m.group("ch"), m.group("id"), m.group("data"), "", raw, mapping)

        # ASC-like: 0.123456 1 18FF50E5x Rx d 8 11 22 ...
        m = re.search(
            r"^(?P<ts>\d+(?:\.\d+)?)\s+(?P<ch>\S+)\s+(?P<id>[0-9A-Fa-f]+)x?\s+(?P<dir>Rx|Tx|RX|TX)?\s*\S*\s*(?P<dlc>\d)\s+(?P<data>(?:[0-9A-Fa-f]{2}\s*)+)",
            raw,
        )
        if m:
            rec = self._make_record(index, m.group("ts"), m.group("ch"), m.group("id"), m.group("data"), m.group("dir") or "", raw, mapping)
            return rec

        return None

    def _make_record(self, index: int, ts_text: str, channel: str, can_id_text: str, data_text: str, direction: str, raw: str, mapping: Dict[str, Any]) -> CanFrameRecord:
        timestamp = self._parse_float(ts_text, default=float(index - 1))
        can_id = self._normalize_can_id(can_id_text)
        data_bytes = self._parse_data_bytes(data_text)
        message_name, decoded = self._decode_with_mapping(can_id, data_bytes, mapping)
        return CanFrameRecord(index, timestamp, channel or "-", can_id, len(data_bytes), self._bytes_to_hex(data_bytes), direction or "", "Data", message_name=message_name, decoded=decoded, raw=raw)

    # =====================
    # PCAP parser: SocketCAN only
    # =====================
    def _analyze_capture(self, path: Path, mapping: Dict[str, Any]) -> List[CanFrameRecord]:
        raw = path.read_bytes()
        if path.suffix.lower() == ".pcapng":
            # Keep this intentionally simple for now: many CAN pcapng files use interface metadata.
            # Text exports from Wireshark/candump are preferred until pcapng linktype handling is expanded.
            return []
        packets, linktype = self._read_pcap_packets(raw)
        if linktype != self.SOCKETCAN_LINKTYPE:
            return []
        records: List[CanFrameRecord] = []
        for ts, frame in packets:
            rec = self._parse_socketcan_frame(len(records) + 1, ts, frame, mapping)
            if rec is not None:
                records.append(rec)
        return records

    def _read_pcap_packets(self, raw: bytes) -> Tuple[List[Tuple[float, bytes]], int]:
        if len(raw) < 24:
            return [], 0
        magic = raw[:4]
        endian = "<" if magic in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1") else ">"
        ns_resolution = magic in (b"\x4d\x3c\xb2\xa1", b"\xa1\xb2\x3c\x4d")
        try:
            _magic, _maj, _min, _tz, _sig, _snaplen, network = struct.unpack_from(endian + "IHHIIII", raw, 0)
        except Exception:
            return [], 0
        offset = 24
        packets: List[Tuple[float, bytes]] = []
        while offset + 16 <= len(raw):
            ts_sec, ts_frac, incl_len, _orig_len = struct.unpack_from(endian + "IIII", raw, offset)
            offset += 16
            if offset + incl_len > len(raw):
                break
            divisor = 1_000_000_000 if ns_resolution else 1_000_000
            packets.append((ts_sec + ts_frac / divisor, raw[offset:offset + incl_len]))
            offset += incl_len
        return packets, network

    def _parse_socketcan_frame(self, index: int, timestamp: float, frame: bytes, mapping: Dict[str, Any]) -> Optional[CanFrameRecord]:
        if len(frame) < 16:
            return None
        try:
            can_id_raw, can_dlc, _pad, _res0, _res1 = struct.unpack_from("=IBBBB", frame, 0)
            data = frame[8:8 + min(8, can_dlc)]
        except Exception:
            return None
        is_eff = bool(can_id_raw & 0x80000000)
        is_rtr = bool(can_id_raw & 0x40000000)
        is_err = bool(can_id_raw & 0x20000000)
        can_id = can_id_raw & (0x1FFFFFFF if is_eff else 0x7FF)
        can_id_text = f"0x{can_id:08X}" if is_eff else f"0x{can_id:03X}"
        frame_type = "Error" if is_err else ("Remote" if is_rtr else "Data")
        message_name, decoded = self._decode_with_mapping(can_id_text, data, mapping)
        status = "Error" if is_err else "OK"
        return CanFrameRecord(index, timestamp, "socketcan", can_id_text, can_dlc, self._bytes_to_hex(data), "", frame_type, message_name=message_name, decoded=decoded, status=status, raw=frame.hex(" "))

    # =====================
    # Decode helpers
    # =====================
    def _load_mapping(self, mapping_path: str | Path | None) -> Dict[str, Any]:
        if not mapping_path:
            return {}
        path = Path(mapping_path)
        if not path.exists():
            return {}
        try:
            if path.suffix.lower() == ".dbc":
                return self._load_dbc(path)
            data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
            if isinstance(data, dict):
                data.setdefault("type", "json")
                return data
        except Exception as exc:
            return {"type": "error", "error": str(exc)}
        return {}

    def _load_dbc(self, path: Path) -> Dict[str, Any]:
        messages: Dict[str, str] = {}
        signals: Dict[str, List[Dict[str, Any]]] = {}
        current_id = ""

        bo_re = re.compile(r"^BO_\s+(?P<id>\d+)\s+(?P<name>[^:]+):\s+(?P<dlc>\d+)")
        sg_re = re.compile(
            r"^\s*SG_\s+(?P<name>\w+)\s*(?:m\d+)?\s*:\s*"
            r"(?P<start>\d+)\|(?P<len>\d+)@(?P<endian>[01])(?P<sign>[+-])\s*"
            r"\((?P<scale>[-+0-9.eE]+),(?P<offset>[-+0-9.eE]+)\)\s*"
            r"\[(?P<min>[^|]*)\|(?P<max>[^\]]*)\]\s*"
            r"\"(?P<unit>[^\"]*)\""
        )

        for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            bo = bo_re.match(line)
            if bo:
                # Vector DBC stores extended 29-bit CAN IDs with the EFF flag
                # added in bit 31 (0x80000000). ASC/candump files usually show
                # the plain 29-bit ID. Normalize both forms to the same key.
                current_id = self._normalize_can_id(bo.group("id"))
                messages[current_id] = bo.group("name").strip()
                signals.setdefault(current_id, [])
                continue

            sg = sg_re.match(line)
            if sg and current_id:
                signals.setdefault(current_id, []).append({
                    "name": sg.group("name"),
                    "start_bit": int(sg.group("start")),
                    "bit_length": int(sg.group("len")),
                    "byte_order": "little" if sg.group("endian") == "1" else "big",
                    "signed": sg.group("sign") == "-",
                    "scale": float(sg.group("scale")),
                    "offset": float(sg.group("offset")),
                    "unit": sg.group("unit"),
                    "source": "dbc",
                })

        return {"type": "dbc", "path": str(path), "messages": messages, "signals": signals}

    def _decode_with_mapping(self, can_id: str, data: bytes, mapping: Dict[str, Any]) -> Tuple[str, str]:
        if not isinstance(mapping, dict):
            return "", ""

        can_keys = self._can_id_keys(can_id)
        messages = mapping.get("messages", {}) if isinstance(mapping.get("messages", {}), dict) else {}
        message_name = ""
        for key in can_keys:
            if key in messages:
                message_name = str(messages[key])
                break

        signals = mapping.get("signals", {}) if isinstance(mapping.get("signals", {}), dict) else {}
        entries = None
        for key in can_keys:
            if key in signals:
                entries = signals[key]
                break
        if not entries:
            return message_name, ""

        decoded = []
        for sig in entries:
            try:
                name = sig.get("name", "signal")
                unit = sig.get("unit", "")
                scale = float(sig.get("scale", 1.0))
                offset = float(sig.get("offset", 0.0))

                if sig.get("source") == "dbc" or "start_bit" in sig:
                    raw_value = self._extract_dbc_signal(
                        data=data,
                        start_bit=int(sig.get("start_bit", 0)),
                        bit_length=int(sig.get("bit_length", 1)),
                        byte_order=str(sig.get("byte_order", "little")),
                        signed=bool(sig.get("signed", False)),
                    )
                else:
                    start_byte = int(sig.get("start_byte", 0))
                    length = int(sig.get("length", 1))
                    endian = str(sig.get("endian", "big")).lower()
                    raw_bytes = data[start_byte:start_byte + length]
                    if len(raw_bytes) != length:
                        continue
                    raw_value = int.from_bytes(raw_bytes, byteorder="little" if endian == "little" else "big", signed=bool(sig.get("signed", False)))

                value = raw_value * scale + offset
                decoded.append(f"{name}={value:g}{unit}")
            except Exception:
                continue
        return message_name, "; ".join(decoded)

    def _can_id_int(self, value: Any) -> int:
        """Parse CAN ID from DBC/ASC/CSV formats and normalize EFF flag.

        Important: Vector DBC extended IDs are often stored as
        ``0x80000000 | can_id``. Logs usually contain only the 29-bit ID.
        This helper removes SocketCAN/DBC flags and keeps the actual 11/29-bit ID.
        """
        if isinstance(value, int):
            raw_value = value
        else:
            text = str(value).strip()
            text = text.replace("0x", "").replace("0X", "")
            # ASC often appends an 'x' to extended IDs, e.g. 18FF50E5x.
            text = text.rstrip("xX")
            text = re.sub(r"[^0-9A-Fa-f]", "", text)
            if not text:
                return 0
            # DBC BO_ IDs are decimal; most text logs are hex. Treat pure decimal
            # values longer than 8 hex digits as decimal only when no A-F exists.
            if re.search(r"[A-Fa-f]", text):
                raw_value = int(text, 16)
            else:
                # For DBC IDs like 2566918373, decimal is intended. For ASC IDs
                # like 18FF50E5 the A-F branch above is used. For numeric IDs such
                # as 123, hex/decimal are both acceptable for 11-bit diagnostics;
                # prefer decimal only if the original string had no 0x and is large.
                original = str(value).strip()
                if original.lower().startswith("0x"):
                    raw_value = int(text, 16)
                elif len(text) > 8:
                    raw_value = int(text, 10)
                else:
                    raw_value = int(text, 16)

        # Remove SocketCAN flags / Vector DBC extended flag / error/RTR bits.
        return raw_value & 0x1FFFFFFF

    def _format_can_id(self, value: int) -> str:
        width = 8 if value > 0x7FF else 3
        return f"0x{value:0{width}X}"

    def _can_id_keys(self, can_id: str) -> List[str]:
        try:
            value = self._can_id_int(can_id)
        except Exception:
            return [str(can_id), str(can_id).upper(), str(can_id).lower()]

        # Include both normalized 29-bit form and common textual variants.
        return list(dict.fromkeys([
            self._format_can_id(value),
            f"0x{value:08X}",
            f"0x{value:03X}",
            f"{value:08X}",
            f"{value:03X}",
            str(value),
            str(value | 0x80000000),  # Vector DBC extended decimal form
            f"0x{(value | 0x80000000):08X}",
            f"{(value | 0x80000000):08X}",
        ]))

    def _extract_dbc_signal(self, data: bytes, start_bit: int, bit_length: int, byte_order: str, signed: bool) -> int:
        if bit_length <= 0:
            return 0

        if byte_order.lower() == "little":
            raw_int = int.from_bytes(data, byteorder="little", signed=False)
            value = (raw_int >> start_bit) & ((1 << bit_length) - 1)
        else:
            # DBC Motorola bit numbering is awkward. This implementation covers the
            # common field cases by building the physical bit positions in MSB-first
            # order starting at the DBC start bit.
            bits = []
            bit = start_bit
            for _ in range(bit_length):
                byte_index = bit // 8
                bit_in_byte = bit % 8
                if byte_index >= len(data):
                    bits.append(0)
                else:
                    bits.append((data[byte_index] >> bit_in_byte) & 1)
                if bit_in_byte == 0:
                    bit += 15
                else:
                    bit -= 1
            value = 0
            for b in bits:
                value = (value << 1) | b

        if signed and bit_length > 0 and value & (1 << (bit_length - 1)):
            value -= 1 << bit_length
        return value

    def _first(self, mapping: Dict[str, str], keys: List[str]) -> str:
        for key in keys:
            value = mapping.get(key)
            if value is not None:
                return str(value).strip()
        return ""

    def _parse_float(self, value: str, default: float = 0.0) -> float:
        try:
            return float(str(value).strip())
        except Exception:
            return default

    def _normalize_can_id(self, value: Any) -> str:
        return self._format_can_id(self._can_id_int(value))

    def _parse_data_bytes(self, value: str) -> bytes:
        text = str(value).strip()
        if "#" in text:
            text = text.split("#", 1)[1]
        pairs = re.findall(r"[0-9A-Fa-f]{2}", text)
        return bytes(int(p, 16) for p in pairs[:64])

    def _bytes_to_hex(self, data: bytes) -> str:
        return " ".join(f"{b:02X}" for b in data)
