# v3.11 Alarm Map Fix

Fixes:
- Replaced legacy wrapped-PDF alarm map that caused alarm names to be shifted.
- Uses the clean CATL v22 alarm map as default/catl_v17 fallback in this package.
- Startup migration backs up and corrects empty or legacy-bad profile alarm_map.json in user data.
- Alarm analysis now uses each BMS device profile parser instead of the global parser.
- Alarm parsing accepts integer values and hex strings such as 0x0004.
- Keeps previous PCS no-auto-connect behavior.
