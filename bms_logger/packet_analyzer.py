from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import csv
import struct


@dataclass
class ModbusPacketRecord:
    index: int
    timestamp: float
    src: str
    dst: str
    sport: int
    dport: int
    direction: str
    transaction_id: int
    protocol_id: int
    length: int
    unit_id: int
    function_code: int
    address: str = ""
    count_or_value: str = ""
    status: str = "OK"
    exception_code: str = ""
    latency_ms: str = ""
    summary: str = ""

    def to_row(self) -> Dict[str, Any]:
        return asdict(self)


class PacketAnalyzer:
    """Lightweight PCAP/PCAPNG Modbus TCP analyzer.

    It intentionally avoids external dependencies so ESS-AIO can run on field laptops
    without Wireshark/tshark/scapy installed. Supported inputs:
    - classic .pcap Ethernet captures
    - basic .pcapng Enhanced Packet Block captures
    """

    MODBUS_PORT = 502

    def analyze(self, path: str | Path, timeout_seconds: float = 2.0) -> List[ModbusPacketRecord]:
        path = Path(path)
        raw = path.read_bytes()
        packets = self._read_capture_packets(raw)
        records: List[ModbusPacketRecord] = []

        for idx, (ts, frame) in enumerate(packets, start=1):
            parsed = self._parse_frame(frame)
            if parsed is None:
                continue
            ip, tcp, payload = parsed
            if tcp["sport"] != self.MODBUS_PORT and tcp["dport"] != self.MODBUS_PORT:
                continue
            record = self._parse_modbus_payload(
                index=len(records) + 1,
                timestamp=ts,
                src=ip["src"],
                dst=ip["dst"],
                sport=tcp["sport"],
                dport=tcp["dport"],
                payload=payload,
            )
            if record is not None:
                records.append(record)

        self._annotate_latency_and_timeouts(records, timeout_seconds=timeout_seconds)
        return records

    def export_csv(self, records: List[ModbusPacketRecord], path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = list(ModbusPacketRecord.__dataclass_fields__.keys())
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for record in records:
                writer.writerow(record.to_row())

    # =====================
    # Capture readers
    # =====================
    def _read_capture_packets(self, raw: bytes) -> List[Tuple[float, bytes]]:
        if len(raw) < 4:
            return []
        if raw[:4] in (b"\xd4\xc3\xb2\xa1", b"\xa1\xb2\xc3\xd4", b"\x4d\x3c\xb2\xa1", b"\xa1\xb2\x3c\x4d"):
            return self._read_pcap(raw)
        if raw[:4] == b"\x0a\x0d\x0d\x0a":
            return self._read_pcapng(raw)
        return []

    def _read_pcap(self, raw: bytes) -> List[Tuple[float, bytes]]:
        magic = raw[:4]
        endian = "<" if magic in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1") else ">"
        ns_resolution = magic in (b"\x4d\x3c\xb2\xa1", b"\xa1\xb2\x3c\x4d")
        offset = 24
        packets: List[Tuple[float, bytes]] = []
        while offset + 16 <= len(raw):
            ts_sec, ts_frac, incl_len, _orig_len = struct.unpack_from(endian + "IIII", raw, offset)
            offset += 16
            if incl_len < 0 or offset + incl_len > len(raw):
                break
            divisor = 1_000_000_000 if ns_resolution else 1_000_000
            ts = ts_sec + ts_frac / divisor
            packets.append((ts, raw[offset: offset + incl_len]))
            offset += incl_len
        return packets

    def _read_pcapng(self, raw: bytes) -> List[Tuple[float, bytes]]:
        packets: List[Tuple[float, bytes]] = []
        offset = 0
        endian = "<"
        while offset + 12 <= len(raw):
            block_type = struct.unpack_from(endian + "I", raw, offset)[0]
            block_len = struct.unpack_from(endian + "I", raw, offset + 4)[0]
            if block_len < 12 or offset + block_len > len(raw):
                break
            body_off = offset + 8
            if block_type == 0x0A0D0D0A and block_len >= 28:
                bom = struct.unpack_from("I", raw, body_off)[0]
                if bom == 0x1A2B3C4D:
                    endian = "<"
                elif bom == 0x4D3C2B1A:
                    endian = ">"
            elif block_type == 0x00000006 and block_len >= 32:  # Enhanced Packet Block
                try:
                    _iface_id, ts_high, ts_low, cap_len, _orig_len = struct.unpack_from(endian + "IIIII", raw, body_off)
                    pkt_off = body_off + 20
                    if pkt_off + cap_len <= offset + block_len - 4:
                        ts_raw = (ts_high << 32) | ts_low
                        # Most Wireshark captures use microsecond resolution unless options say otherwise.
                        ts = ts_raw / 1_000_000
                        packets.append((ts, raw[pkt_off: pkt_off + cap_len]))
                except Exception:
                    pass
            offset += block_len
        return packets

    # =====================
    # Protocol parsers
    # =====================
    def _parse_frame(self, frame: bytes) -> Optional[Tuple[Dict[str, Any], Dict[str, Any], bytes]]:
        if len(frame) < 14:
            return None
        eth_type = struct.unpack_from("!H", frame, 12)[0]
        ip_offset = 14
        if eth_type == 0x8100 and len(frame) >= 18:  # VLAN
            eth_type = struct.unpack_from("!H", frame, 16)[0]
            ip_offset = 18
        if eth_type != 0x0800:
            return None
        if len(frame) < ip_offset + 20:
            return None
        first = frame[ip_offset]
        version = first >> 4
        ihl = (first & 0x0F) * 4
        if version != 4 or len(frame) < ip_offset + ihl:
            return None
        proto = frame[ip_offset + 9]
        if proto != 6:  # TCP
            return None
        total_len = struct.unpack_from("!H", frame, ip_offset + 2)[0]
        src = ".".join(str(b) for b in frame[ip_offset + 12: ip_offset + 16])
        dst = ".".join(str(b) for b in frame[ip_offset + 16: ip_offset + 20])
        tcp_offset = ip_offset + ihl
        if len(frame) < tcp_offset + 20:
            return None
        sport, dport = struct.unpack_from("!HH", frame, tcp_offset)
        data_offset = (frame[tcp_offset + 12] >> 4) * 4
        payload_offset = tcp_offset + data_offset
        ip_payload_end = ip_offset + total_len if total_len else len(frame)
        if payload_offset > len(frame):
            return None
        payload = frame[payload_offset:min(ip_payload_end, len(frame))]
        return {"src": src, "dst": dst}, {"sport": sport, "dport": dport}, payload

    def _parse_modbus_payload(self, index: int, timestamp: float, src: str, dst: str, sport: int, dport: int, payload: bytes) -> Optional[ModbusPacketRecord]:
        if len(payload) < 8:
            return None
        transaction_id, protocol_id, length = struct.unpack_from("!HHH", payload, 0)
        unit_id = payload[6]
        function_code = payload[7]
        if protocol_id != 0:
            return None
        direction = "Response" if sport == self.MODBUS_PORT else "Request"
        status = "OK"
        exception_code = ""
        address = ""
        count_or_value = ""
        summary = f"FC {function_code}"
        pdu = payload[7:]

        if function_code & 0x80:
            status = "Exception"
            exception_code = str(pdu[1]) if len(pdu) > 1 else ""
            summary = f"Exception FC {function_code & 0x7F}, code={exception_code}"
        elif direction == "Request":
            if function_code in (1, 2, 3, 4) and len(pdu) >= 5:
                addr, qty = struct.unpack_from("!HH", pdu, 1)
                address = f"0x{addr:04X}"
                count_or_value = str(qty)
                summary = f"Read addr={address}, count={qty}"
            elif function_code == 5 and len(pdu) >= 5:
                addr, val = struct.unpack_from("!HH", pdu, 1)
                address = f"0x{addr:04X}"
                count_or_value = f"0x{val:04X}"
                summary = f"Write Coil addr={address}, value={count_or_value}"
            elif function_code == 6 and len(pdu) >= 5:
                addr, val = struct.unpack_from("!HH", pdu, 1)
                address = f"0x{addr:04X}"
                count_or_value = f"{val} / 0x{val:04X}"
                summary = f"Write Register addr={address}, value={count_or_value}"
            elif function_code == 16 and len(pdu) >= 6:
                addr, qty = struct.unpack_from("!HH", pdu, 1)
                address = f"0x{addr:04X}"
                count_or_value = str(qty)
                summary = f"Write Multiple addr={address}, count={qty}"
        else:
            if function_code in (1, 2, 3, 4) and len(pdu) >= 2:
                byte_count = pdu[1]
                count_or_value = f"{byte_count} bytes"
                summary = f"Read Response bytes={byte_count}"
            elif function_code in (5, 6, 16) and len(pdu) >= 5:
                addr, val = struct.unpack_from("!HH", pdu, 1)
                address = f"0x{addr:04X}"
                count_or_value = str(val)
                summary = f"Write Response addr={address}, value/count={val}"

        return ModbusPacketRecord(
            index=index,
            timestamp=timestamp,
            src=src,
            dst=dst,
            sport=sport,
            dport=dport,
            direction=direction,
            transaction_id=transaction_id,
            protocol_id=protocol_id,
            length=length,
            unit_id=unit_id,
            function_code=function_code,
            address=address,
            count_or_value=count_or_value,
            status=status,
            exception_code=exception_code,
            summary=summary,
        )

    def _annotate_latency_and_timeouts(self, records: List[ModbusPacketRecord], timeout_seconds: float) -> None:
        pending: Dict[Tuple[int, int, str, str], ModbusPacketRecord] = {}
        for rec in records:
            if rec.direction == "Request":
                key = (rec.transaction_id, rec.unit_id, rec.src, rec.dst)
                pending[key] = rec
            else:
                key = (rec.transaction_id, rec.unit_id, rec.dst, rec.src)
                req = pending.pop(key, None)
                if req is not None:
                    latency = max(0.0, (rec.timestamp - req.timestamp) * 1000)
                    req.latency_ms = f"{latency:.2f}"
                    rec.latency_ms = f"{latency:.2f}"
        for req in pending.values():
            # Only mark as timeout if capture continues long enough after request.
            if records and records[-1].timestamp - req.timestamp >= timeout_seconds:
                req.status = "Timeout"
                req.summary = (req.summary + " | timeout").strip()
