from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from pymodbus.client import ModbusTcpClient

from .point_table import PointTable, resolve_point_table_path


@dataclass
class RegisterDef:
    name: str
    address: int
    scale: float = 1.0
    offset: float = 0.0


class BmsModbusClient:
    """
    BMS Modbus TCP client.

    当前默认读取：
    - 0x0301 : BMS power on
    - 0x0302 : BMS status
    - 0x0305 : Number of Racks
    - 0x0020 ~ 0x002e : 系统核心数据块

    当前支持控制：
    - 0x0380 : EMS heartbeat
    - 0x0381 : EMS cmd
    - 0x038c : Fault Clear cmd
    """

    CORE_REGS: Dict[str, RegisterDef] = {
        "bms_power_on": RegisterDef("BMS power on", 0x0301),
        "bms_status": RegisterDef("BMS status", 0x0302),
        "number_of_racks": RegisterDef("Number of Racks", 0x0305),

        "system_voltage": RegisterDef("System voltage", 0x0020, 0.1, 0.0),
        "system_current": RegisterDef("System current", 0x0021, 1.0, -20000.0),
        "soc": RegisterDef("SOC", 0x0022, 0.1, 0.0),
        "soh": RegisterDef("SOH", 0x0023, 0.1, 0.0),
        "max_cell_voltage": RegisterDef("Max cell voltage", 0x0024, 1.0, 0.0),
        "min_cell_voltage": RegisterDef("Min cell voltage", 0x0025, 1.0, 0.0),
        "avg_cell_voltage": RegisterDef("Avg. cell voltage", 0x0026, 1.0, 0.0),
        "max_cell_temperature": RegisterDef("Max cell temperature", 0x0027, 1.0, -50.0),
        "min_cell_temperature": RegisterDef("Min cell temperature", 0x0028, 1.0, -50.0),
        "avg_cell_temperature": RegisterDef("Avg. cell temperature", 0x0029, 1.0, -50.0),
        "max_charge_current_allowed": RegisterDef("Max charge current allowed", 0x002A, 1.0, -20000.0),
        "max_discharge_current_allowed": RegisterDef("Max discharge current allowed", 0x002B, 1.0, -20000.0),
        "max_charge_power_allowed": RegisterDef("Max charge power allowed", 0x002C, 1.0, -20000.0),
        "max_discharge_power_allowed": RegisterDef("Max discharge power allowed", 0x002D, 1.0, -20000.0),
        "system_power": RegisterDef("System power", 0x002E, 1.0, -20000.0),
    }

    REG_EMS_HEARTBEAT = 0x0380
    REG_EMS_CMD = 0x0381
    REG_INSULATION_MONITOR_CMD = 0x038B
    REG_FAULT_CLEAR_CMD = 0x038C

    EMS_CMD_STAY = 1
    EMS_CMD_POWER_ON = 2
    EMS_CMD_POWER_OFF = 3

    INSULATION_MONITOR_DISABLE_VALUE = 2

    FAULT_CLEAR_VALUE = 1
    FAULT_CLEAR_RESET_VALUE = 0

    def __init__(
        self,
        host: str,
        port: int = 502,
        unit_id: int = 1,
        timeout: float = 1.0,
        protocol: str = "catl_v22_bms",
        point_table_path: str | None = None,
        profile: str | None = None,
        alarm_map_path: str | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout
        self.protocol = protocol
        self.profile = profile or ("catl_v17" if "v17" in str(protocol).lower() else "catl_v22")
        self.alarm_map_path = alarm_map_path
        self.point_table = PointTable(resolve_point_table_path(protocol, point_table_path, self.profile))
        self.client = ModbusTcpClient(
            host=self.host,
            port=self.port,
            timeout=self.timeout,
        )
        self.driver_key = protocol

    def connect(self) -> bool:
        return bool(self.client.connect())

    def close(self) -> None:
        self.client.close()

    def _read_holding_block(self, address: int, count: int) -> Optional[list[int]]:
        rr = self.client.read_holding_registers(
            address=address,
            count=count,
            device_id=self.unit_id,
        )
        if rr.isError():
            return None
        return rr.registers

    def _read_single_register(self, address: int) -> Optional[int]:
        regs = self._read_holding_block(address, 1)
        if regs is None:
            return None
        return regs[0]

    def write_single_register(self, address: int, value: int) -> bool:
        rr = self.client.write_register(
            address=address,
            value=value,
            device_id=self.unit_id,
        )
        return not rr.isError()

    @staticmethod
    def _apply_transform(raw_value: int, scale: float, offset: float) -> float:
        return raw_value * scale + offset

    def _point_value(self, key: str, raw: int) -> float | int:
        p = self.point_table.get(key)
        if p is None:
            return raw
        value = self._apply_transform(raw, p.scale, p.offset)
        return int(value) if float(value).is_integer() else value

    def read_telemetry_snapshot(self) -> Optional[Dict[str, Any]]:
        # Address ranges are taken from the selected point table. For V22 this keeps
        # the old UI keys stable while allowing the underlying point table to move forward.
        ranges = [
            (0x0000, 0x20, "alarm"),
            (0x0020, 0x50, "summary"),
            (0x0300, 0x10, "status"),
        ]
        raw_by_addr: Dict[int, int] = {}
        for start_addr, count, _name in ranges:
            regs = self._read_holding_block(start_addr, count)
            if regs is None:
                return None
            for i, raw in enumerate(regs):
                raw_by_addr[start_addr + i] = raw

        snapshot: Dict[str, Any] = {}
        for addr in range(0x0000, 0x0020):
            snapshot[f"alarm_0x{addr:04x}"] = raw_by_addr.get(addr)

        # Stable keys used by the current UI/recorder. Values are decoded through the selected point table.
        stable_addr_keys = {
            0x0300: "bms_heartbeat",
            0x0301: "bms_power_on",
            0x0302: "bms_status",
            0x0305: "number_of_racks",
            0x0020: "system_voltage",
            0x0021: "system_current",
            0x0022: "soc",
            0x0023: "soh",
            0x0024: "max_cell_voltage",
            0x0025: "min_cell_voltage",
            0x0026: "avg_cell_voltage",
            0x0027: "max_cell_temperature",
            0x0028: "min_cell_temperature",
            0x0029: "avg_cell_temperature",
            0x002A: "max_charge_current_allowed",
            0x002B: "max_discharge_current_allowed",
            0x002C: "max_charge_power_allowed",
            0x002D: "max_discharge_power_allowed",
            0x002E: "system_power",
        }
        for addr, key in stable_addr_keys.items():
            if addr not in raw_by_addr:
                continue
            p = self.point_table.get_by_address(addr)
            if p is None:
                snapshot[key] = raw_by_addr[addr]
            else:
                value = self._apply_transform(raw_by_addr[addr], p.scale, p.offset)
                snapshot[key] = int(value) if float(value).is_integer() else value

        # Also expose protocol-native keys for newly added V22 points.
        for addr, raw in raw_by_addr.items():
            p = self.point_table.get_by_address(addr)
            if p is None:
                continue
            value = self._apply_transform(raw, p.scale, p.offset)
            snapshot.setdefault(p.key, int(value) if float(value).is_integer() else value)

        return snapshot


    def read_sbmu_summary(self, sbmu_index: int) -> Optional[Dict[str, Any]]:
        """Read one SBMU summary block using the selected point table.

        V22 uses the standard CATL block rule:
        SBMU01 = 0x0400~0x07ff, SBMU02 = 0x0800~0x0bff, SBMUn = n*0x400~n*0x400+0x03ff.
        The summary subrange starts at base+0x20.
        """
        if sbmu_index < 1:
            raise ValueError("sbmu_index must be >= 1")
        base = sbmu_index * 0x400
        start = base + 0x20
        count = 0x60
        regs = self._read_holding_block(start, count)
        if regs is None:
            return None
        result: Dict[str, Any] = {"sbmu_index": sbmu_index, "base_address": f"0x{base:04x}"}
        for i, raw in enumerate(regs):
            addr = start + i
            point = self.point_table.get_by_address(addr) or self.point_table.get_by_address(0x0400 + (addr - base))
            if point is None:
                continue
            value = self._apply_transform(raw, point.scale, point.offset)
            result[point.key] = int(value) if float(value).is_integer() else value
        return result

    def read_bms_power_on(self) -> Optional[int]:
        return self._read_single_register(0x0301)

    def read_bms_status(self) -> Optional[int]:
        return self._read_single_register(0x0302)

    def clear_fault(self) -> bool:
        pulse_seconds = 1.5
        ok1 = self.write_single_register(self.REG_FAULT_CLEAR_CMD, self.FAULT_CLEAR_VALUE)
        if not ok1:
            return False

        time.sleep(pulse_seconds)

        ok2 = self.write_single_register(self.REG_FAULT_CLEAR_CMD, self.FAULT_CLEAR_RESET_VALUE)
        return ok2

    def write_heartbeat(self, value: int) -> bool:
        value = int(value) % 256
        return self.write_single_register(self.REG_EMS_HEARTBEAT, value)

    def write_insulation_monitor_disable(self) -> bool:
        """Write 0x038B = 2 to keep insulation monitoring disabled.

        Some site procedures require this command to be refreshed periodically
        during commissioning. The caller should schedule it at minute-level
        intervals, not every second.
        """
        return self.write_single_register(self.REG_INSULATION_MONITOR_CMD, self.INSULATION_MONITOR_DISABLE_VALUE)

    def write_ems_cmd(self, value: int) -> bool:
        if value not in (
            self.EMS_CMD_STAY,
            self.EMS_CMD_POWER_ON,
            self.EMS_CMD_POWER_OFF,
        ):
            raise ValueError(f"Unsupported EMS cmd value: {value}")
        return self.write_single_register(self.REG_EMS_CMD, value)

    def write_ems_cmd_stay(self) -> bool:
        return self.write_ems_cmd(self.EMS_CMD_STAY)

    def write_ems_cmd_power_on(self) -> bool:
        return self.write_ems_cmd(self.EMS_CMD_POWER_ON)

    def write_ems_cmd_power_off(self) -> bool:
        return self.write_ems_cmd(self.EMS_CMD_POWER_OFF)


    def _read_ascii_registers(self, address: int, count: int) -> str:
        regs = self._read_holding_block(address, count)
        if regs is None:
            raise RuntimeError(f"BMS ASCII read failed: address=0x{address:04x}")

        data = bytearray()
        for reg in regs:
            data.append((int(reg) >> 8) & 0xFF)
            data.append(int(reg) & 0xFF)

        return data.decode("ascii", errors="ignore").replace("\x00", "").strip()

    def get_point_catalog(self) -> Dict[str, Dict[str, Any]]:
        catalog = self.point_table.catalog()
        # Keep legacy aliases so existing UI columns and CSV headers remain stable.
        alias_by_addr = {
            0x0300: "bms_heartbeat", 0x0301: "bms_power_on", 0x0302: "bms_status", 0x0305: "number_of_racks",
            0x0020: "system_voltage", 0x0021: "system_current", 0x0022: "soc", 0x0023: "soh",
            0x0024: "max_cell_voltage", 0x0025: "min_cell_voltage", 0x0026: "avg_cell_voltage",
            0x0027: "max_cell_temperature", 0x0028: "min_cell_temperature", 0x0029: "avg_cell_temperature",
            0x002A: "max_charge_current_allowed", 0x002B: "max_discharge_current_allowed",
            0x002C: "max_charge_power_allowed", 0x002D: "max_discharge_power_allowed", 0x002E: "system_power",
        }
        for addr, key in alias_by_addr.items():
            p = self.point_table.get_by_address(addr)
            if p:
                catalog[key] = {"label": p.description, "address": f"0x{addr:04x}", "scale": p.scale, "offset": p.offset, "unit": self._guess_unit(key), "section": p.section}
        for addr in range(0x0000, 0x0020):
            key = f"alarm_0x{addr:04x}"
            catalog.setdefault(key, {"label": key, "address": f"0x{addr:04x}", "unit": "bitfield"})
        return catalog

    @staticmethod
    def _guess_unit(key: str) -> str:
        if "voltage" in key:
            return "mV" if "cell" in key else "V"
        if "current" in key:
            return "A"
        if "power" in key:
            return "kW"
        if key in {"soc", "soh"} or "soe" in key:
            return "%"
        if "temperature" in key:
            return "°C"
        return ""

    def read_software_version(self) -> Dict[str, Any]:
        # CATL V17 point table: 0x0100-0x0107 MBMU Software,
        # 0x0108-0x010f MBMU Hardware, 0x0110-0x0117 ETH Software,
        # 0x0118-0x011f ETH Hardware. Each block is 16 bytes / 8 registers, ASCII.
        return {
            "MBMU Software": self._read_ascii_registers(0x0100, 8),
            "MBMU Hardware": self._read_ascii_registers(0x0108, 8),
            "ETH Software": self._read_ascii_registers(0x0110, 8),
            "ETH Hardware": self._read_ascii_registers(0x0118, 8),
        }

    def read_debug_status(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}

        single_regs = {
            "bms_heartbeat_0x0300": 0x0300,
            "bms_power_on_0x0301": 0x0301,
            "bms_status_0x0302": 0x0302,
            "number_of_racks_0x0305": 0x0305,
        }

        for name, addr in single_regs.items():
            try:
                value = self._read_single_register(addr)
                result[name] = value
            except Exception as exc:
                result[name] = f"ERROR: {exc}"

        try:
            core_block = self._read_holding_block(0x0020, 0x002E - 0x0020 + 1)
            if core_block is None:
                result["core_0x0020_0x002e"] = "ERROR: read failed"
            else:
                result["core_0x0020_0x002e"] = core_block
        except Exception as exc:
            result["core_0x0020_0x002e"] = f"ERROR: {exc}"

        try:
            alarm_block = self._read_holding_block(0x0000, 0x001F - 0x0000 + 1)
            if alarm_block is None:
                result["alarm_0x0000_0x001f"] = "ERROR: read failed"
            else:
                result["alarm_0x0000_0x001f"] = alarm_block
        except Exception as exc:
            result["alarm_0x0000_0x001f"] = f"ERROR: {exc}"

        return result