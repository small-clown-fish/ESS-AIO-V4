from __future__ import annotations

from typing import Any, Dict

from .base import DriverInfo
from ..modbus_client import BmsModbusClient
from ..pcs_client import PcsClient
from ..bms_profiles import load_bms_profile, default_bms_profile_dirs


INFO_BMS = DriverInfo(
    key="catl_v22_bms",
    name="CATL TenerS/TenerX V22 BMS",
    device_type="BMS",
    vendor="CATL",
    description="CATL V22 Modbus driver loaded from JSON point table; keeps legacy UI aliases.",
)

INFO_PCS = DriverInfo(
    key="generic_modbus_pcs",
    name="Generic Modbus PCS",
    device_type="PCS",
    vendor="Generic",
    description="Config-driven PCS Modbus driver using pcs_config.json points.",
)


def create_bms(config: Dict[str, Any]):
    profile = str(config.get("profile") or config.get("bms_profile") or "").strip()
    protocol = str(config.get("driver", "catl_v22_bms"))
    if not profile:
        profile = "catl_v17" if "v17" in protocol.lower() else "catl_v22"

    point_table_path = config.get("point_table_path")
    alarm_map_path = config.get("alarm_map_path")

    # Prefer BMS profile folders. Keep explicit point_table_path for compatibility.
    try:
        key, meta, _profile_dir = load_bms_profile(profile, default_bms_profile_dirs())
        profile = key
        point_table_path = point_table_path or meta.get("register_map_path")
        alarm_map_path = alarm_map_path or meta.get("alarm_map_path")
    except Exception:
        pass

    return BmsModbusClient(
        host=config["host"],
        port=int(config.get("port", 502)),
        unit_id=int(config.get("unit_id", 1)),
        timeout=float(config.get("timeout", 1.0)),
        protocol=protocol,
        point_table_path=point_table_path,
        profile=profile,
        alarm_map_path=alarm_map_path,
    )


def create_pcs(config: Dict[str, Any]):
    return PcsClient(config=config)
