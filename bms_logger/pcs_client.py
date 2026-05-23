from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from pymodbus.client import ModbusTcpClient
import time


@dataclass
class PcsPoint:
    register_type: str
    address: int
    scale: float = 1.0
    offset: float = 0.0
    data_type: str = "UINT16"
    register_count: int = 1
    word_order: str = "big"  # big: high word first; little: low word first
    write_value: Optional[int] = None
    online_value: Optional[int] = None
    open_value: Optional[int] = None
    closed_value: Optional[int] = None
    enable_value: Optional[int] = None
    disable_value: Optional[int] = None
    write_function: str = "single"  # single/fc06 or multiple/fc16


class PcsClient:
    """
    配置驱动的 PCS Modbus TCP 客户端。

    兼容旧 pcs_config.json，同时支持科华 BCS1250K 点表常见字段：
    - UINT16 / INT16 / UINT32 / INT32
    - register_count 多寄存器读取
    - big/little word order
    - scale + offset

    注意：地址按配置文件中的 Modbus PDU 地址使用，不自动做 40001/30001 转换。
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}
        self.enabled = bool(self.config.get("enabled", False))
        self.host = str(self.config.get("host", ""))
        self.port = int(self.config.get("port", 502))
        self.unit_id = int(self.config.get("unit_id", 1))
        self.timeout = float(self.config.get("timeout", 3.0))
        self.points = self.config.get("points", {})

        self.client = ModbusTcpClient(
            host=self.host,
            port=self.port,
            timeout=self.timeout,
        )

    # ---------------------------
    # Basic
    # ---------------------------
    def is_configured(self) -> bool:
        return self.enabled and bool(self.host) and isinstance(self.points, dict)

    def connect(self) -> bool:
        if not self.is_configured():
            raise RuntimeError("PCS not configured")
        return bool(self.client.connect())

    def close(self) -> None:
        self.client.close()

    def _get_point(self, name: str) -> PcsPoint:
        if name not in self.points:
            raise RuntimeError(f"PCS point not configured: {name}")

        raw = self.points[name]
        return PcsPoint(
            register_type=str(raw.get("register_type", "holding")).lower(),
            address=int(raw["address"]),
            scale=float(raw.get("scale", 1.0)),
            offset=float(raw.get("offset", 0.0)),
            data_type=str(raw.get("data_type", "UINT16")).upper(),
            register_count=int(raw.get("register_count", raw.get("count", 1))),
            word_order=str(raw.get("word_order", "big")).lower(),
            write_value=raw.get("write_value"),
            online_value=raw.get("online_value"),
            open_value=raw.get("open_value"),
            closed_value=raw.get("closed_value"),
            enable_value=raw.get("enable_value"),
            disable_value=raw.get("disable_value"),
            write_function=str(raw.get("write_function", raw.get("write_mode", "single"))).lower(),
        )

    @staticmethod
    def _to_signed(value: int, bits: int) -> int:
        sign_bit = 1 << (bits - 1)
        mask = (1 << bits) - 1
        value &= mask
        return value - (1 << bits) if value & sign_bit else value

    def _decode_registers(self, registers: list[int], point: PcsPoint) -> int:
        dtype = point.data_type.upper()
        regs = [int(r) & 0xFFFF for r in registers]

        if dtype in {"ENUM", "BITFIELD16", "UINT16"}:
            return regs[0]
        if dtype == "INT16":
            return self._to_signed(regs[0], 16)

        if dtype in {"UINT32", "INT32", "DWORD"}:
            if len(regs) < 2:
                raise RuntimeError(f"PCS point at {point.address} requires 2 registers, got {len(regs)}")
            if point.word_order in {"little", "low_first", "lohi"}:
                lo, hi = regs[0], regs[1]
            else:
                hi, lo = regs[0], regs[1]
            value = (hi << 16) | lo
            return self._to_signed(value, 32) if dtype == "INT32" else value

        # 兜底：未知类型按第一个寄存器返回，避免影响旧配置。
        return regs[0]

    def _encode_registers(self, raw_value: int, point: PcsPoint) -> list[int]:
        dtype = point.data_type.upper()
        value = int(raw_value)
        if dtype in {"ENUM", "BITFIELD16", "UINT16", "INT16"}:
            return [value & 0xFFFF]
        if dtype in {"UINT32", "INT32", "DWORD"}:
            value &= 0xFFFFFFFF
            hi = (value >> 16) & 0xFFFF
            lo = value & 0xFFFF
            if point.word_order in {"little", "low_first", "lohi"}:
                return [lo, hi]
            return [hi, lo]
        return [value & 0xFFFF]

    def _read_registers_for_point(self, point_name: str) -> list[int]:
        point = self._get_point(point_name)
        count = max(1, int(point.register_count))

        if point.register_type == "holding":
            rr = self.client.read_holding_registers(
                address=point.address,
                count=count,
                device_id=self.unit_id,
            )
        elif point.register_type == "input":
            rr = self.client.read_input_registers(
                address=point.address,
                count=count,
                device_id=self.unit_id,
            )
        else:
            raise RuntimeError(f"Unsupported PCS register_type: {point.register_type}")

        if rr.isError():
            raise RuntimeError(f"PCS read failed: {point_name}")

        return [int(x) for x in rr.registers]

    def _read_register(self, point_name: str) -> int:
        point = self._get_point(point_name)
        registers = self._read_registers_for_point(point_name)
        return self._decode_registers(registers, point)

    def _write_register(self, point_name: str, value: Optional[int] = None) -> bool:
        point = self._get_point(point_name)

        if point.register_type != "holding":
            raise RuntimeError(f"PCS write requires holding register: {point_name}")

        write_value = point.write_value if value is None else value

        if value is not None:
            # 反向 scale：UI 输入物理值，写入 raw。
            if point.scale:
                write_value = (float(value) - point.offset) / point.scale
            else:
                write_value = value
        if write_value is None:
            raise RuntimeError(f"PCS write_value missing for: {point_name}")

        registers = self._encode_registers(int(round(float(write_value))), point)
        force_multiple = point.write_function in {"multiple", "fc16", "write_registers", "multi"}
        if len(registers) == 1 and not force_multiple:
            rr = self.client.write_register(
                address=point.address,
                value=registers[0],
                device_id=self.unit_id,
            )
        else:
            rr = self.client.write_registers(
                address=point.address,
                values=registers,
                device_id=self.unit_id,
            )
        return not rr.isError()

    def _apply_transform(self, raw_value: int, point_name: str) -> float:
        point = self._get_point(point_name)
        return raw_value * point.scale + point.offset

    # ---------------------------
    # Generic read/write APIs
    # ---------------------------
    def read_raw(self, point_name: str) -> int:
        return self._read_register(point_name)

    def read_registers(self, point_name: str) -> list[int]:
        return self._read_registers_for_point(point_name)

    def read_value(self, point_name: str) -> float:
        raw = self._read_register(point_name)
        return self._apply_transform(raw, point_name)

    def write_value(self, point_name: str, value: Optional[int] = None) -> bool:
        return self._write_register(point_name, value)

    # ---------------------------
    # Status APIs
    # ---------------------------
    def is_online(self) -> bool:
        raw = self._read_register("online_status")
        point = self._get_point("online_status")
        if point.online_value is None:
            raise RuntimeError("PCS online_status online_value not configured")
        return raw == int(point.online_value)

    def is_dc_breaker_open(self) -> bool:
        raw = self._read_register("dc_breaker_status")
        point = self._get_point("dc_breaker_status")
        if point.open_value is None:
            raise RuntimeError("PCS dc_breaker_status open_value not configured")
        return raw == int(point.open_value)

    def is_dc_breaker_closed(self) -> bool:
        raw = self._read_register("dc_breaker_status")
        point = self._get_point("dc_breaker_status")
        if point.closed_value is None:
            raise RuntimeError("PCS dc_breaker_status closed_value not configured")
        return raw == int(point.closed_value)

    def is_charge_enabled(self) -> bool:
        raw = self._read_register("charge_enable_status")
        point = self._get_point("charge_enable_status")
        if point.enable_value is None:
            raise RuntimeError("PCS charge_enable_status enable_value not configured")
        return raw == int(point.enable_value)

    def is_discharge_enabled(self) -> bool:
        raw = self._read_register("discharge_enable_status")
        point = self._get_point("discharge_enable_status")
        if point.enable_value is None:
            raise RuntimeError("PCS discharge_enable_status enable_value not configured")
        return raw == int(point.enable_value)

    def get_run_status(self) -> int:
        return self._read_register("run_status")

    def get_fault_status(self) -> int:
        return self._read_register("fault_status")

    def get_alarm_status(self) -> int:
        return self._read_register("alarm_status")

    def get_mode(self) -> int:
        return self._read_register("mode")

    def get_remote_local_status(self) -> int:
        return self._read_register("remote_local_status")

    # ---------------------------
    # Measurement APIs
    # ---------------------------
    def get_active_power(self) -> float:
        return self.read_value("active_power")

    def get_reactive_power(self) -> float:
        return self.read_value("reactive_power")

    def get_dc_voltage(self) -> float:
        return self.read_value("dc_voltage")

    def get_dc_current(self) -> float:
        return self.read_value("dc_current")

    def get_ac_voltage(self) -> float:
        return self.read_value("ac_voltage")

    def get_ac_current(self) -> float:
        return self.read_value("ac_current")

    def get_frequency(self) -> float:
        return self.read_value("frequency")

    def get_power_factor(self) -> float:
        return self.read_value("power_factor")

    # ---------------------------
    # Command APIs
    # ---------------------------
    def hv_on(self) -> bool:
        return self._write_register("hv_on_cmd")

    def hv_off(self) -> bool:
        return self._write_register("hv_off_cmd")

    def start(self) -> bool:
        return self._write_register("start_cmd")

    def stop(self) -> bool:
        return self._write_register("stop_cmd")

    def reset_fault(self) -> bool:
        return self._write_register("reset_fault_cmd")

    def close_dc_breaker(self) -> bool:
        return self._write_register("close_dc_breaker_cmd")

    def open_dc_breaker(self) -> bool:
        return self._write_register("open_dc_breaker_cmd")

    def enable_charge(self) -> bool:
        point = self._get_point("enable_charge_cmd")
        value = point.enable_value if point.enable_value is not None else point.write_value
        return self._write_register("enable_charge_cmd", value)

    def disable_charge(self) -> bool:
        point = self._get_point("disable_charge_cmd")
        value = point.disable_value if point.disable_value is not None else point.write_value
        return self._write_register("disable_charge_cmd", value)

    def enable_discharge(self) -> bool:
        point = self._get_point("enable_discharge_cmd")
        value = point.enable_value if point.enable_value is not None else point.write_value
        return self._write_register("enable_discharge_cmd", value)

    def disable_discharge(self) -> bool:
        point = self._get_point("disable_discharge_cmd")
        value = point.disable_value if point.disable_value is not None else point.write_value
        return self._write_register("disable_discharge_cmd", value)

    def set_active_power(self, value: int) -> bool:
        return self._write_register("set_active_power", value)

    def set_charge_power(self, value: int) -> bool:
        return self._write_register("set_charge_power", value)

    def set_discharge_power(self, value: int) -> bool:
        return self._write_register("set_discharge_power", value)

    def enable_reactive_power_remote(self) -> bool:
        """Enable remote reactive-power control before writing 7812.

        Kehua BCS1250K profile: 7909 = 1 enables remote reactive-power setpoint writes.
        """
        return self._write_register("reactive_power_remote_enable", 1)

    def set_reactive_power(self, value: int) -> bool:
        # 7909 is not heartbeat; it is the remote reactive-power enable bit.
        # Always enable it immediately before writing 7812 so single-device and
        # fleet control paths behave the same.
        self.enable_reactive_power_remote()
        return self._write_register("set_reactive_power", value)

    def set_power_factor(self, value: int) -> bool:
        return self._write_register("set_power_factor", value)

    def set_ramp_rate(self, value: int) -> bool:
        return self._write_register("set_ramp_rate", value)

    def send_heartbeat(self, value: int) -> bool:
        return self._write_register("heartbeat", value)

    def validate_config(self) -> list[str]:
        errors: list[str] = []

        if not self.enabled:
            errors.append("PCS config disabled: enabled=false")

        if not self.host:
            errors.append("PCS host is empty")

        required_points = [
            "dc_breaker_status",
            "active_power",
            "hv_on_cmd",
            "hv_off_cmd",
            "start_cmd",
            "stop_cmd",
            "reset_fault_cmd",
        ]

        for name in required_points:
            if name not in self.points:
                errors.append(f"Missing PCS point: {name}")
                continue

            point = self.points[name]
            if "address" not in point:
                errors.append(f"Missing address for PCS point: {name}")

            if name.endswith("_cmd") and "write_value" not in point:
                if "enable_value" not in point and "disable_value" not in point:
                    errors.append(f"Missing write_value for PCS command: {name}")

        return errors

    def wait_until_power_zero(self, timeout: float = 10.0, threshold: float = 0.1) -> bool:
        start = time.time()

        while time.time() - start < timeout:
            power = self.get_active_power()
            if abs(power) <= threshold:
                return True
            time.sleep(1.0)

        return False

    def stop_with_confirm(self, timeout: float = 10.0, threshold: float = 0.1) -> bool:
        if not self.stop():
            return False
        return self.wait_until_power_zero(timeout=timeout, threshold=threshold)

    def read_debug_status(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}

        debug_points = [
            "dc_breaker_status",
            "ac_breaker_status",
            "active_power",
            "reactive_power",
            "dc_voltage",
            "dc_current",
            "run_status",
            "fault_status",
            "alarm_status",
            "mode",
            "remote_local_status",
        ]

        for point_name in debug_points:
            try:
                if point_name in self.points:
                    raw = self.read_raw(point_name)
                    try:
                        value = self.read_value(point_name)
                    except Exception:
                        value = raw

                    result[point_name] = {
                        "raw": raw,
                        "value": value,
                    }
                else:
                    result[point_name] = {
                        "error": "not configured",
                    }

            except Exception as exc:
                result[point_name] = {
                    "error": str(exc),
                }

        return result

    def execute_command_with_debug(self, command_method_name: str) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "command": command_method_name,
            "success": False,
            "debug_status": {},
            "error": "",
        }

        method = getattr(self, command_method_name, None)
        if method is None:
            result["error"] = f"PCS command method not found: {command_method_name}"
            return result

        try:
            result["success"] = bool(method())
        except Exception as exc:
            result["error"] = f"PCS command exception: {exc}"
            return result

        try:
            result["debug_status"] = self.read_debug_status()
        except Exception as exc:
            result["debug_status"] = {
                "error": str(exc)
            }

        return result

    def precheck_control_ready(self, action: str = "generic") -> list[str]:
        errors: list[str] = []

        if not self.is_configured():
            errors.append("PCS not configured")
            return errors

        if "remote_local_status" in self.points:
            try:
                value = self.get_remote_local_status()
                raw_cfg = self.points.get("remote_local_status", {})
                remote_value = raw_cfg.get("remote_value", None)

                if remote_value is not None and int(value) != int(remote_value):
                    errors.append(
                        f"PCS not in remote mode: value={value}, expected={remote_value}"
                    )
            except Exception as exc:
                errors.append(f"PCS remote/local check failed: {exc}")

        if "fault_status" in self.points:
            try:
                fault = self.get_fault_status()
                if int(fault) != 0:
                    if action in ["start", "hv_on", "close_dc_breaker", "enable_charge", "enable_discharge"]:
                        errors.append(f"PCS fault active: fault_status={fault}")
            except Exception as exc:
                errors.append(f"PCS fault check failed: {exc}")

        if "alarm_status" in self.points:
            try:
                alarm = self.get_alarm_status()
                if int(alarm) != 0:
                    if action in ["start", "hv_on", "close_dc_breaker", "enable_charge", "enable_discharge"]:
                        errors.append(f"PCS alarm active: alarm_status={alarm}")
            except Exception as exc:
                errors.append(f"PCS alarm check failed: {exc}")

        return errors
