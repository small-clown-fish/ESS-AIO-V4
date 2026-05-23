from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bms_logger.protocol_mapping import build_mapping

if __name__ == "__main__":
    dbc = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "bms_logger" / "protocols" / "ESS_PLT_MCAN_V3.28_20250611_Saveas.dbc"
    pt = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "bms_logger" / "protocols" / "catl_teners_tenerx_0_5p_v22_point_table.json"
    out = Path(sys.argv[3]) if len(sys.argv) > 3 else ROOT / "bms_logger" / "protocols" / "catl_v22_can_modbus_mapping.json"
    result = build_mapping(dbc, pt, out)
    print(f"Wrote {out} with {result['metadata']['row_count']} mapping rows")
