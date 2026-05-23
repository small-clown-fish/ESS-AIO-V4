from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .can_dbc import Dbc
from .point_table import PointTable

@dataclass
class MappingRow:
    direction: str
    modbus_address: str
    modbus_key: str
    modbus_description: str
    modbus_scale: float
    modbus_offset: float
    can_id: str
    can_message: str
    can_signal: str
    can_scale: float
    can_offset: float
    confidence: str
    note: str = ""
    modbus_actual_span: str = ""
    modbus_access: str = ""
    modbus_section: str = ""



def _norm(s: str) -> str:
    s = re.sub(r"_\d+$", "", s.lower())
    s = s.replace("battery", "bat").replace("subsystem", "hvs").replace("voltage", "u")
    return re.sub(r"[^a-z0-9]+", "", s)

# Hand-curated high confidence aliases for CATL S2A summary signals -> V22 SBMU point table offsets.
SBMU_SIGNAL_TO_OFFSET = {
    "BAT_U_HVS": 0x0420,             # Battery Subsystem Voltage, dc outside voltage
    "BAT_U_TOT_HVS": 0x0438,         # Sum of cell voltage
    "S2A_I_HVS": 0x0422,
    "S2A_SOC": 0x0423,
    "S2A_SOH": 0x0424,
    "S2A_UCELL_MAX": 0x0425,
    "S2A_UCELL_MIN": 0x0426,
    "S2A_UCELL_AVE": 0x0427,
    "S2A_TCELL_MAX": 0x0428,
    "S2A_TCELL_MIN": 0x0429,
    "S2A_TCELL_AVE": 0x042A,
    "S2A_MAX_CHG_CUR": 0x042B,
    "S2A_MAX_DISCHG_CUR": 0x042C,
    "S2A_MAX_CHG_PWR": 0x042D,
    "S2A_MAX_DISCHG_PWR": 0x042E,
    "S2A_POWER": 0x042F,
    "S2A_UCELL_MAX_POS": 0x0430,
    "S2A_UCELL_MIN_POS": 0x0431,
    "S2A_TCELL_MAX_POS": 0x0432,
    "S2A_TCELL_MIN_POS": 0x0433,
}

# High-confidence aliases for CATL M2P/MBMU system summary signals -> V22 MBMU point table.
# These fill the 0x0000~0x03ff system area that the first generator missed.
MBMU_SIGNAL_TO_ADDRESS = {
    "M2P_MEASURE_VOL": 0x0020,
    "M2P_CURRENT": 0x0021,
    "M2P_DSOC": 0x0022,
    "M2P_SOH": 0x0023,
    "M2P_SYSMAXVOLT": 0x0024,
    "M2P_SYSMINVOLT": 0x0025,
    "M2P_SYSAVGVOLT": 0x0026,
    "M2P_SYSMAXTEMP": 0x0027,
    "M2P_SYSMINTEMP": 0x0028,
    "M2P_SYSAVGTEMP": 0x0029,
    "M2P_PERMITMAXCHARGE_I": 0x002A,
    "M2P_PERMITMAXDISCHARGE_I": 0x002B,
    "M2P_PERMITMAXPOWER_CHARGE": 0x002C,
    "M2P_PERMITMAXPOWER_DISCHARGE": 0x002D,
    "M2P_POWER": 0x002E,
    "M2P_SOE_CHARGE": 0x002F,
    "M2P_SOE_DISCHARGE": 0x0030,
    "M2P_SYSREMAINENGY_CHARGE": 0x0031,
    "M2P_SYSREMAINENGY_DISCHARGE": 0x0032,
    "M2P_PERMITMAXVOLT": 0x0033,
    "M2P_PERMITMINVOLT": 0x0034,
    "M2P_ISODETFUNCTIONSTATUS": 0x0035,
    "M2P_POSITIVERESISTANCE": 0x0036,
    "M2P_NEGATIVERESISTANCE": 0x0037,
    "M2P_EVN_T1": 0x0038,
    "M2P_EVN_T2": 0x0039,
}


def _strip_suffix(sig_name: str) -> str:
    return re.sub(r"_\d{2}$", "", sig_name)


def _sbmu_index_from_name(name: str) -> Optional[int]:
    m = re.search(r"__(\d{2})$", name)
    if m:
        return int(m.group(1))
    m = re.search(r"_(\d{2})$", name)
    if m:
        return int(m.group(1))
    return None


def build_mapping(dbc_path: str | Path, point_table_path: str | Path, output_path: str | Path) -> Dict[str, Any]:
    dbc = Dbc(dbc_path)
    pt = PointTable(point_table_path)
    rows: List[MappingRow] = []
    for msg in dbc.messages.values():
        idx = _sbmu_index_from_name(msg.name)
        for sig in msg.signals:
            base = _strip_suffix(sig.name)
            base_upper = base.upper()

            # MBMU/system area: 0x0000~0x03ff. Do this before SBMU logic because
            # M2P messages also carry __nn suffixes that are not Modbus SBMU block indices.
            addr = MBMU_SIGNAL_TO_ADDRESS.get(base_upper)
            if addr is not None:
                p = pt.get_by_address(addr)
                rows.append(MappingRow(
                    direction="CAN_TO_MODBUS",
                    modbus_address=f"0x{addr:04x}",
                    modbus_key=p.key if p else f"register_0x{addr:04x}",
                    modbus_description=p.description if p else "",
                    modbus_scale=p.scale if p else 1.0,
                    modbus_offset=p.offset if p else 0.0,
                    can_id=f"0x{msg.frame_id:08X}",
                    can_message=msg.name,
                    can_signal=sig.name,
                    can_scale=sig.factor,
                    can_offset=sig.offset,
                    confidence="high" if p else "needs_point_table_check",
                    note="Generated from CATL V22 M2P/MBMU system summary alias table.",
                    modbus_actual_span=str((p.raw or {}).get("actual_span", "")) if p else "",
                    modbus_access=p.access if p else "",
                    modbus_section=p.section if p else "",
                ))
                continue

            # SBMU/rack area: 0x0400 and above.
            sbmu = idx
            if not sbmu:
                continue
            offset = SBMU_SIGNAL_TO_OFFSET.get(base)
            if offset is None:
                continue
            # V22 SBMU01 points are 0x0400 based; actual SBMUn address = offset + (n-1)*0x400
            addr = offset + (sbmu - 1) * 0x400
            p = pt.get_by_address(addr) or pt.get_by_address(offset)
            rows.append(MappingRow(
                direction="CAN_TO_MODBUS",
                modbus_address=f"0x{addr:04x}",
                modbus_key=p.key if p else f"register_0x{addr:04x}",
                modbus_description=p.description if p else "",
                modbus_scale=p.scale if p else 1.0,
                modbus_offset=p.offset if p else 0.0,
                can_id=f"0x{msg.frame_id:08X}",
                can_message=msg.name,
                can_signal=sig.name,
                can_scale=sig.factor,
                can_offset=sig.offset,
                confidence="high" if p else "needs_point_table_check",
                note="Generated from CATL V22 DBC signal suffix and V22 SBMUn 0x400 block rule.",
                modbus_actual_span=str((p.raw or {}).get("actual_span", "")) if p else "",
                modbus_access=p.access if p else "",
                modbus_section=p.section if p else "",
            ))
    result = {
        "metadata": {
            "dbc": str(dbc_path),
            "point_table": str(point_table_path),
            "mapping_rule": "MBMU M2P aliases use V22 0x0000~0x03ff system addresses; SBMU actual address = SBMU01 offset + (SBMU index - 1) * 0x400",
            "row_count": len(rows),
        },
        "mappings": [asdict(r) for r in rows],
    }
    with Path(output_path).open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    return result


def load_mapping(path: str | Path) -> List[Dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f).get("mappings", [])
