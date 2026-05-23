from pathlib import Path
import argparse, sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bms_logger.joint_analyzer import correlate, write_report

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Correlate CAN ASC with Wireshark Modbus CSV/PCAP/PCAPNG using CATL CAN<->Modbus mapping.")
    ap.add_argument("--asc", required=True)
    ap.add_argument("--modbus", required=True, help="Wireshark/tshark Modbus CSV, or raw .pcap/.pcapng capture")
    ap.add_argument("--dbc", default=str(ROOT / "bms_logger/protocols/ESS_PLT_MCAN_V3.28_20250611_Saveas.dbc"))
    ap.add_argument("--mapping", default=str(ROOT / "bms_logger/protocols/catl_v22_can_modbus_mapping.json"))
    ap.add_argument("--out", default="joint_analysis_report.csv")
    ap.add_argument("--tolerance", type=float, default=0.5)
    args = ap.parse_args()
    rows = correlate(args.asc, args.modbus, args.dbc, args.mapping, args.tolerance)
    write_report(rows, args.out)
    print(f"Wrote {args.out} with {len(rows)} correlated rows")
