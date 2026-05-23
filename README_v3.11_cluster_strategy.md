# ESS-AIO v3.11 Cluster Strategy Update

This build adds a cluster-level charge/discharge strategy runtime.

## Main changes

- Added `bms_logger/cluster_strategy_runtime.py`.
- Strategy runs per cluster, not whole-site.
- A cluster can bind N BMS and M PCS.
- Cluster allowed power is calculated from all BMS in that cluster.
- For every BMS, allowed power is:
  - `min(BMS allowed power, allowed current * system voltage / 1000)`.
- If the target does not exceed the allowed value, the target is kept.
- If the target exceeds the allowed value, PCS power is clamped.
- If BMS has no valid response within the configured response timeout, cluster PCS power is set to 0 by default.
- Charge cutoff: max cell voltage above threshold sets cluster PCS active power to 0.
- Discharge cutoff: min cell voltage below threshold sets cluster PCS active power to 0.
- Cluster PCS allocation supports:
  - equal split
  - capacity weighted
- PCS commands reuse the persistent PCS fleet worker and queue; no one-shot connect/write/close loop is used.

## UI

Open the Strategy page and use `Cluster Charge / Discharge Strategy`:

- Cluster
- Mode: charge / discharge / signed
- PCS sign: `+ = discharge` or `+ = charge`
- Target kW
- Ramp step kW
- Ramp interval seconds
- BMS response timeout seconds
- Charge stop max cell voltage mV
- Discharge stop min cell voltage mV
- Allocation mode
- Timeout action

Before starting the cluster strategy, normal BMS polling should be running so `latest_snapshots` contains fresh BMS data.
