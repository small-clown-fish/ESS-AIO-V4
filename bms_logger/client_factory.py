from __future__ import annotations

from typing import Any, Dict

from .drivers import create_bms_driver, create_pcs_driver


def create_bms_client(device_config: Dict[str, Any], fake_mode: bool = False):
    """Create a BMS client through the v3 driver registry.

    Compatibility note: callers still receive an object with the same methods as
    the old BmsModbusClient / FakeBmsClient, so the existing UI and workers do
    not need to know which driver is active.
    """
    return create_bms_driver(device_config, fake_mode=fake_mode)


def create_pcs_client(config: Dict[str, Any], fake_mode: bool = False):
    """Create a PCS client through the v3 driver registry."""
    return create_pcs_driver(config, fake_mode=fake_mode)
