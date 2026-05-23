from __future__ import annotations

from typing import Any, Dict, List

from .base import DriverInfo
from . import catl, fake

BMS_DRIVERS: Dict[str, DriverInfo] = {
    catl.INFO_BMS.key: catl.INFO_BMS,
    "catl_v17_bms": DriverInfo(key="catl_v17_bms", name="CATL EnerC/EnerX V17 BMS", device_type="BMS", vendor="CATL", description="Legacy V17 JSON point table driver."),
    fake.INFO_BMS.key: fake.INFO_BMS,
}

PCS_DRIVERS: Dict[str, DriverInfo] = {
    catl.INFO_PCS.key: catl.INFO_PCS,
    fake.INFO_PCS.key: fake.INFO_PCS,
}

DEFAULT_BMS_DRIVER = catl.INFO_BMS.key
DEFAULT_PCS_DRIVER = catl.INFO_PCS.key
FAKE_BMS_DRIVER = fake.INFO_BMS.key
FAKE_PCS_DRIVER = fake.INFO_PCS.key


def list_bms_drivers() -> List[DriverInfo]:
    return list(BMS_DRIVERS.values())


def list_pcs_drivers() -> List[DriverInfo]:
    return list(PCS_DRIVERS.values())


def create_bms_driver(config: Dict[str, Any], fake_mode: bool = False):
    key = FAKE_BMS_DRIVER if fake_mode else str(config.get("driver", DEFAULT_BMS_DRIVER))
    if key == fake.INFO_BMS.key:
        return fake.create_bms(config)
    if key in {catl.INFO_BMS.key, "catl_v17_bms"}:
        return catl.create_bms(config)
    raise RuntimeError(f"Unknown BMS driver: {key}")


def create_pcs_driver(config: Dict[str, Any], fake_mode: bool = False):
    key = FAKE_PCS_DRIVER if fake_mode else str(config.get("driver", DEFAULT_PCS_DRIVER))
    if key == fake.INFO_PCS.key:
        return fake.create_pcs(config)
    if key == catl.INFO_PCS.key:
        return catl.create_pcs(config)
    raise RuntimeError(f"Unknown PCS driver: {key}")
