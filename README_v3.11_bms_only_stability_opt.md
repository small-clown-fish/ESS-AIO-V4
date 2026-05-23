# ESS-AIO v3.11 BMS-only stability optimization

This build is optimized for the current use case: BMS data recording first, PCS control/polling isolated unless manually connected.

## Key changes

1. BMS connect/start no longer triggers PCS network access through service logic.
   - Cutoff/derating can still detect BMS-side threshold events.
   - PCS commands are skipped unless a PCS has been manually connected and has an active PCS worker.

2. BMS worker reconnect is now controlled by backoff.
   - Initial connection failure no longer exits immediately.
   - Retry interval backs off from 2s up to 30s.
   - Three consecutive read failures close the stale socket and reconnect with backoff.
   - Stop is interruptible and closes the socket cleanly.

3. BMS Modbus timeout default reduced to 1s.
   - This prevents unreachable BMS devices from blocking worker threads for too long.

4. CSV writing is protected from UI/disk blocking.
   - CSV/alarm CSV are still async through recorder proxy.
   - If a CSV is locked by Excel or OS scanning, recorder pauses writes for 10s and retries later instead of blocking sampling/UI.
   - Flush remains buffered every 100 rows.

5. UI error/log refresh is throttled.
   - Repeated timeout/connect errors no longer flood QTextEdit or redraw curves on every failed poll.
   - Normal snapshots still update buffers at full sampling rate, while heavy UI refresh remains limited by ui_refresh_interval.

## Suggested test

- Configure 1 unreachable BMS and 1 reachable BMS.
- Start all BMS.
- Verify the reachable BMS continues recording and UI remains responsive.
- Open one generated CSV in Excel during recording and verify the application does not freeze.
- Configure PCS devices but do not press PCS Connect; start BMS and confirm there are no PCS connection attempts.
