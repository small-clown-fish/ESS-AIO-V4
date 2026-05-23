# ESS-AIO v3.18 Strategy/BMS Stability Fix

This patch is based directly on the user-uploaded `ESS-AIO_v3.18.zip`.

## Main changes

1. PCS heartbeat is disabled by default in fleet workers.
   - PCS workers are still started as persistent command queues for start/stop and active/reactive power commands.
   - `start_pcs_heartbeats(..., heartbeat_enabled=True)` can be used later after the PCS heartbeat point is fully verified.

2. Cluster Strategy no longer starts PCS heartbeat.
   - Strategy uses `start_pcs_command_workers()` only.
   - It still dispatches active power through the per-PCS queue.

3. Cluster Strategy now validates BMS data before starting.
   - It requires fresh snapshots from normal BMS polling.
   - It does not create/touch BMS Modbus connections.
   - If snapshots are missing or stale, it warns and refuses to start.

4. BMS 0x038B periodic write no longer force-starts BMS heartbeat.
   - It uses command-only BMS workers for the periodic 0x038B task.
   - This avoids adding another BMS heartbeat writer that can disturb normal BMS polling.

5. Fleet snapshot collection no longer holds the fleet manager lock while querying every worker.
   - This reduces UI blocking in `refresh_fleet_heartbeat_status()`.

6. Legacy single-BMS HeartbeatWorker now closes and reconnects after heartbeat exceptions.
   - Avoids repeatedly writing to stale sockets after BrokenPipe/connection failure.

## Files changed

- `bms_logger/fleet_manager.py`
- `bms_logger/ui_mixins/strategy_mixin.py`
- `bms_logger/worker.py`
