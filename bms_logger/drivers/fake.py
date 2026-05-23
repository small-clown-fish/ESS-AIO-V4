from __future__ import annotations

from typing import Any, Dict

from .base import DriverInfo
from ..fake_bms_client import FakeBmsClient
from ..fake_pcs_client import FakePcsClient


INFO_BMS = DriverInfo(
    key="fake_bms",
    name="Fake BMS Simulator",
    device_type="BMS",
    vendor="Simulator",
    description="Local fake BMS driver for offline testing and strategy validation.",
)

INFO_PCS = DriverInfo(
    key="fake_pcs",
    name="Fake PCS Simulator",
    device_type="PCS",
    vendor="Simulator",
    description="Local fake PCS driver for offline testing and control-loop validation.",
)


def create_bms(config: Dict[str, Any]):
    return FakeBmsClient(config)


def create_pcs(config: Dict[str, Any]):
    return FakePcsClient(config)
