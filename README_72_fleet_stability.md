# ESS-AIO v3.11 72-device fleet stability update

This package adds a fleet-scale runtime path for the target scenario:

- 24 BMS heartbeat writers
- 48 PCS heartbeat writers
- PCS fleet start / stop / active-power broadcast
- BMS data recording remains handled by existing BMS polling + CSV logic

## Key changes

1. Added `bms_logger/fleet_manager.py`
   - One persistent worker per BMS/PCS device.
   - Keeps the Modbus connection open instead of connect/write/close every second.
   - Writes heartbeat on schedule.
   - Executes queued PCS commands without blocking the GUI.
   - Uses exponential reconnect backoff so unreachable IPs do not create a reconnect storm.

2. Added Control page fleet buttons
   - `Start 72 Heartbeats`
   - `Stop 72 Heartbeats`
   - `Fleet Status`
   - `Fleet Set Power`
   - `Fleet PCS Start`
   - `Fleet PCS Stop`

3. BMS/PCS control separation
   - Fleet PCS commands use the persistent PCS workers.
   - BMS data collection continues through the existing BMS polling workers and CSV logic.

## Operating recommendation

For site testing, use this order:

1. Configure all BMS devices.
2. Configure all PCS devices with `enabled=true`, `host`, and a valid `heartbeat` point.
3. Start BMS polling / CSV recording.
4. Click `Start 72 Heartbeats`.
5. Use `Fleet PCS Start`, `Fleet Set Power`, and `Fleet PCS Stop` for broadcast PCS control.
6. Use `Fleet Status` to check how many workers are online.

## Important safety note

This is a stability-oriented software structure update. Before real power operation, verify the PCS point table, power sign convention, command values, remote/local mode, and emergency stop behavior on a small number of PCS first.
