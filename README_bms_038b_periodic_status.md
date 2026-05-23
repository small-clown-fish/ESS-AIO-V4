# ESS-AIO v3.11 BMS heartbeat status + 038B periodic command update

This update adds BMS-side fleet heartbeat/status support and a minute-level periodic command for commissioning workflows.

## Added

- BMS Control page:
  - `Start All BMS HB`
  - `Stop All BMS HB`
  - `BMS Periodic Insulation Monitor Disable (038B)` panel
  - configurable interval in minutes, default 15 min
  - `Start 038B=2 Cycle`
  - `Stop 038B Cycle`

## Behavior

- All BMS heartbeat workers reuse the existing persistent fleet worker path.
- The top status bar heartbeat field now summarizes BMS/PCS heartbeat online counts.
- Periodic insulation-monitor disable reuses the same BMS persistent worker connection and writes:
  - register `0x038B`
  - value `2`
- The 038B write is scheduled at minute-level intervals and does not create a separate connection loop.

## Notes

- If BMS is offline, the worker stays in reconnect backoff and does not flood reconnect attempts.
- `0x038B=2` is first attempted shortly after enabling the cycle, then follows the configured interval.
