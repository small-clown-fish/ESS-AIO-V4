from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable, Optional
import hashlib
import json
import os
import sqlite3
import time

from bms_logger.can_analyzer import CanFrameRecord, CanIdStat
from bms_logger.packet_analyzer import ModbusPacketRecord

SCHEMA_VERSION = 1


def _file_fingerprint(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    st = p.stat()
    return {
        "path": str(p.resolve()),
        "size": st.st_size,
        "mtime_ns": st.st_mtime_ns,
    }


def _stable_key(*parts: Any) -> str:
    h = hashlib.sha256()
    for part in parts:
        if part is None:
            h.update(b"<none>")
        elif isinstance(part, (str, Path)) and part and Path(str(part)).exists():
            fp = _file_fingerprint(str(part))
            h.update(json.dumps(fp, sort_keys=True).encode("utf-8"))
        else:
            h.update(str(part).encode("utf-8", errors="ignore"))
        h.update(b"\0")
    return h.hexdigest()[:24]


def default_cache_dir(profile_dir: str | Path | None = None) -> Path:
    if profile_dir:
        base = Path(profile_dir) / ".packet_cache"
    else:
        base = Path.home() / ".ess_aio_packet_cache"
    base.mkdir(parents=True, exist_ok=True)
    return base


class PacketSQLiteStore:
    """SQLite cache for large packet/CAN analyses.

    This is deliberately small and dependency-free. It stores parsed rows so UI,
    diagnosis and evidence highlighting can re-open large captures without
    reparsing the original ASC/PCAPNG every time.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass

    def _init_schema(self) -> None:
        cur = self.conn.cursor()
        cur.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS can_frames (
                idx INTEGER PRIMARY KEY,
                timestamp REAL,
                channel TEXT,
                can_id TEXT,
                dlc INTEGER,
                data TEXT,
                direction TEXT,
                frame_type TEXT,
                message_name TEXT,
                frequency_hz TEXT,
                decoded TEXT,
                semantic_decoded TEXT,
                status TEXT,
                raw TEXT
            );
            CREATE INDEX IF NOT EXISTS ix_can_frames_time ON can_frames(timestamp);
            CREATE INDEX IF NOT EXISTS ix_can_frames_id ON can_frames(can_id);
            CREATE TABLE IF NOT EXISTS can_stats (
                can_id TEXT PRIMARY KEY,
                message_name TEXT,
                count INTEGER,
                first_ts REAL,
                last_ts REAL,
                avg_period_ms TEXT,
                frequency_hz TEXT,
                dlc_set TEXT
            );
            CREATE TABLE IF NOT EXISTS can_anomalies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT,
                can_id TEXT,
                idx TEXT,
                time TEXT,
                value TEXT,
                detail TEXT
            );
            CREATE TABLE IF NOT EXISTS modbus_packets (
                idx INTEGER PRIMARY KEY,
                timestamp REAL,
                src TEXT,
                dst TEXT,
                sport INTEGER,
                dport INTEGER,
                direction TEXT,
                transaction_id INTEGER,
                protocol_id INTEGER,
                length INTEGER,
                unit_id INTEGER,
                function_code INTEGER,
                address TEXT,
                count_or_value TEXT,
                status TEXT,
                exception_code TEXT,
                latency_ms TEXT,
                summary TEXT
            );
            CREATE INDEX IF NOT EXISTS ix_modbus_packets_time ON modbus_packets(timestamp);
            CREATE INDEX IF NOT EXISTS ix_modbus_packets_addr ON modbus_packets(address);
            """
        )
        self.conn.commit()

    def put_meta(self, **items: Any) -> None:
        cur = self.conn.cursor()
        cur.execute("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", ("schema_version", str(SCHEMA_VERSION)))
        for k, v in items.items():
            cur.execute("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", (k, json.dumps(v, ensure_ascii=False)))
        self.conn.commit()

    def get_meta(self, key: str, default: Any = None) -> Any:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except Exception:
            return row["value"]

    def has_kind(self, kind: str, expected_fingerprint: dict[str, Any], mapping_fingerprint: Optional[dict[str, Any]] = None) -> bool:
        if str(self.get_meta("schema_version", "")) != str(SCHEMA_VERSION):
            return False
        if self.get_meta("kind") != kind:
            return False
        if self.get_meta("source") != expected_fingerprint:
            return False
        if kind == "can" and self.get_meta("mapping") != mapping_fingerprint:
            return False
        table = "can_frames" if kind == "can" else "modbus_packets"
        try:
            n = self.conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
            return n >= 0
        except Exception:
            return False

    def save_modbus(self, source: str | Path, records: Iterable[ModbusPacketRecord]) -> None:
        rows = [asdict(r) for r in records]
        cur = self.conn.cursor()
        cur.execute("DELETE FROM modbus_packets")
        cur.executemany(
            """INSERT INTO modbus_packets VALUES(
            :index,:timestamp,:src,:dst,:sport,:dport,:direction,:transaction_id,:protocol_id,:length,:unit_id,:function_code,
            :address,:count_or_value,:status,:exception_code,:latency_ms,:summary)""",
            rows,
        )
        self.put_meta(kind="modbus", source=_file_fingerprint(source), created_at=time.time(), record_count=len(rows))
        self.conn.commit()

    def load_modbus(self, limit: int | None = None) -> list[ModbusPacketRecord]:
        sql = "SELECT * FROM modbus_packets ORDER BY idx"
        if limit:
            sql += f" LIMIT {int(limit)}"
        out: list[ModbusPacketRecord] = []
        for row in self.conn.execute(sql):
            out.append(ModbusPacketRecord(
                index=row["idx"], timestamp=row["timestamp"], src=row["src"], dst=row["dst"], sport=row["sport"], dport=row["dport"],
                direction=row["direction"], transaction_id=row["transaction_id"], protocol_id=row["protocol_id"], length=row["length"],
                unit_id=row["unit_id"], function_code=row["function_code"], address=row["address"] or "", count_or_value=row["count_or_value"] or "",
                status=row["status"] or "OK", exception_code=row["exception_code"] or "", latency_ms=row["latency_ms"] or "", summary=row["summary"] or "",
            ))
        return out

    def save_can(self, source: str | Path, mapping: str | Path | None, records: Iterable[CanFrameRecord], stats: Iterable[CanIdStat], anomalies: Iterable[dict[str, Any]]) -> None:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM can_frames")
        cur.execute("DELETE FROM can_stats")
        cur.execute("DELETE FROM can_anomalies")
        rec_rows = [asdict(r) for r in records]
        stat_rows = [asdict(s) for s in stats]
        cur.executemany(
            """INSERT INTO can_frames VALUES(
            :index,:timestamp,:channel,:can_id,:dlc,:data,:direction,:frame_type,:message_name,:frequency_hz,:decoded,:semantic_decoded,:status,:raw)""",
            rec_rows,
        )
        cur.executemany(
            """INSERT INTO can_stats VALUES(:can_id,:message_name,:count,:first_ts,:last_ts,:avg_period_ms,:frequency_hz,:dlc_set)""",
            stat_rows,
        )
        cur.executemany(
            """INSERT INTO can_anomalies(type,can_id,idx,time,value,detail) VALUES(:type,:can_id,:index,:time,:value,:detail)""",
            [{"type": a.get("type", ""), "can_id": a.get("can_id", ""), "index": str(a.get("index", "")), "time": str(a.get("time", "")), "value": str(a.get("value", "")), "detail": a.get("detail", "")} for a in anomalies],
        )
        self.put_meta(kind="can", source=_file_fingerprint(source), mapping=_file_fingerprint(mapping) if mapping else None, created_at=time.time(), record_count=len(rec_rows))
        self.conn.commit()

    def load_can(self, limit: int | None = None) -> tuple[list[CanFrameRecord], list[CanIdStat], list[dict[str, Any]]]:
        sql = "SELECT * FROM can_frames ORDER BY idx"
        if limit:
            sql += f" LIMIT {int(limit)}"
        records: list[CanFrameRecord] = []
        for row in self.conn.execute(sql):
            records.append(CanFrameRecord(
                index=row["idx"], timestamp=row["timestamp"], channel=row["channel"] or "-", can_id=row["can_id"] or "", dlc=row["dlc"] or 0,
                data=row["data"] or "", direction=row["direction"] or "", frame_type=row["frame_type"] or "Data", message_name=row["message_name"] or "",
                frequency_hz=row["frequency_hz"] or "", decoded=row["decoded"] or "", semantic_decoded=row["semantic_decoded"] or "", status=row["status"] or "OK", raw=row["raw"] or "",
            ))
        stats: list[CanIdStat] = []
        for row in self.conn.execute("SELECT * FROM can_stats ORDER BY count DESC, can_id"):
            stats.append(CanIdStat(row["can_id"], row["message_name"] or "", row["count"], row["first_ts"], row["last_ts"], row["avg_period_ms"] or "", row["frequency_hz"] or "", row["dlc_set"] or ""))
        anomalies: list[dict[str, Any]] = []
        for row in self.conn.execute("SELECT * FROM can_anomalies ORDER BY id"):
            anomalies.append({"type": row["type"], "can_id": row["can_id"], "index": row["idx"], "time": row["time"], "value": row["value"], "detail": row["detail"]})
        return records, stats, anomalies

    def count_can_frames(self, text: str = "", can_id: str = "", time_min: float | None = None, time_max: float | None = None) -> int:
        sql = "SELECT COUNT(*) AS n FROM can_frames"
        where, params = self._can_where(text, can_id, time_min, time_max)
        if where:
            sql += " WHERE " + " AND ".join(where)
        row = self.conn.execute(sql, params).fetchone()
        return int(row["n"] if row else 0)

    def query_can_frames(self, limit: int = 2000, offset: int = 0, text: str = "", can_id: str = "", time_min: float | None = None, time_max: float | None = None, order_desc: bool = False) -> list[CanFrameRecord]:
        sql = "SELECT * FROM can_frames"
        where, params = self._can_where(text, can_id, time_min, time_max)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY timestamp " + ("DESC" if order_desc else "ASC") + ", idx " + ("DESC" if order_desc else "ASC")
        sql += " LIMIT ? OFFSET ?"
        params.extend([int(limit), int(offset)])
        return [CanFrameRecord(
            index=row["idx"], timestamp=row["timestamp"], channel=row["channel"] or "-", can_id=row["can_id"] or "", dlc=row["dlc"] or 0,
            data=row["data"] or "", direction=row["direction"] or "", frame_type=row["frame_type"] or "Data", message_name=row["message_name"] or "",
            frequency_hz=row["frequency_hz"] or "", decoded=row["decoded"] or "", semantic_decoded=row["semantic_decoded"] or "", status=row["status"] or "OK", raw=row["raw"] or "",
        ) for row in self.conn.execute(sql, params)]

    def _can_where(self, text: str = "", can_id: str = "", time_min: float | None = None, time_max: float | None = None) -> tuple[list[str], list[Any]]:
        where: list[str] = []
        params: list[Any] = []
        if can_id:
            where.append("LOWER(can_id)=LOWER(?)")
            params.append(can_id.strip())
        if time_min is not None:
            where.append("timestamp>=?")
            params.append(float(time_min))
        if time_max is not None:
            where.append("timestamp<=?")
            params.append(float(time_max))
        text = (text or "").strip().lower()
        if text:
            like = f"%{text}%"
            where.append("(LOWER(channel) LIKE ? OR LOWER(can_id) LIKE ? OR LOWER(message_name) LIKE ? OR LOWER(data) LIKE ? OR LOWER(direction) LIKE ? OR LOWER(frame_type) LIKE ? OR LOWER(status) LIKE ? OR LOWER(decoded) LIKE ? OR LOWER(semantic_decoded) LIKE ? OR LOWER(raw) LIKE ?)")
            params.extend([like]*10)
        return where, params

    def count_modbus_packets(self, text: str = "", address: str = "", time_min: float | None = None, time_max: float | None = None) -> int:
        sql = "SELECT COUNT(*) AS n FROM modbus_packets"
        where, params = self._modbus_where(text, address, time_min, time_max)
        if where:
            sql += " WHERE " + " AND ".join(where)
        row = self.conn.execute(sql, params).fetchone()
        return int(row["n"] if row else 0)

    def query_modbus_packets(self, limit: int = 2000, offset: int = 0, text: str = "", address: str = "", time_min: float | None = None, time_max: float | None = None, order_desc: bool = False) -> list[ModbusPacketRecord]:
        sql = "SELECT * FROM modbus_packets"
        where, params = self._modbus_where(text, address, time_min, time_max)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY timestamp " + ("DESC" if order_desc else "ASC") + ", idx " + ("DESC" if order_desc else "ASC")
        sql += " LIMIT ? OFFSET ?"
        params.extend([int(limit), int(offset)])
        out: list[ModbusPacketRecord] = []
        for row in self.conn.execute(sql, params):
            out.append(ModbusPacketRecord(
                index=row["idx"], timestamp=row["timestamp"], src=row["src"], dst=row["dst"], sport=row["sport"], dport=row["dport"],
                direction=row["direction"], transaction_id=row["transaction_id"], protocol_id=row["protocol_id"], length=row["length"],
                unit_id=row["unit_id"], function_code=row["function_code"], address=row["address"] or "", count_or_value=row["count_or_value"] or "",
                status=row["status"] or "OK", exception_code=row["exception_code"] or "", latency_ms=row["latency_ms"] or "", summary=row["summary"] or "",
            ))
        return out

    def _modbus_where(self, text: str = "", address: str = "", time_min: float | None = None, time_max: float | None = None) -> tuple[list[str], list[Any]]:
        where: list[str] = []
        params: list[Any] = []
        if address:
            where.append("LOWER(address)=LOWER(?)")
            params.append(address.strip())
        if time_min is not None:
            where.append("timestamp>=?")
            params.append(float(time_min))
        if time_max is not None:
            where.append("timestamp<=?")
            params.append(float(time_max))
        text = (text or "").strip().lower()
        if text:
            like = f"%{text}%"
            where.append("(LOWER(src) LIKE ? OR LOWER(dst) LIKE ? OR LOWER(direction) LIKE ? OR CAST(function_code AS TEXT) LIKE ? OR LOWER(address) LIKE ? OR LOWER(status) LIKE ? OR LOWER(summary) LIKE ? OR CAST(transaction_id AS TEXT) LIKE ? OR CAST(unit_id AS TEXT) LIKE ?)")
            params.extend([like]*9)
        return where, params


def cache_path_for(kind: str, source: str | Path, mapping: str | Path | None = None, profile_dir: str | Path | None = None) -> Path:
    key = _stable_key(kind, source, mapping or "")
    return default_cache_dir(profile_dir) / f"{kind}_{key}.sqlite"


def fingerprint(path: str | Path | None) -> Optional[dict[str, Any]]:
    if not path:
        return None
    return _file_fingerprint(path)
