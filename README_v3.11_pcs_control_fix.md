# v3.11 PCS control fix

Changes in this package:

- PCS heartbeat point changed from `7838` to `7909` for Kehua BCS1250K profile.
- PCS heartbeat write now supports forced FC16 (`write_registers`) through `write_function: "multiple"` for devices that reject FC06 single-register writes.
- Active power setpoint remains `7811`; data type set to `INT16`, access `RW`, unit `kW`.
- Reactive power setpoint added at `7812`; data type `INT16`, access `RW`, unit `kvar`.
- PCS Control UI now has separate Active Power and Reactive Power rows.
- Added single PCS and fleet-level reactive power commands.

Important: If your site point table uses a different heartbeat address, edit `pcs_config.json -> points -> heartbeat -> address`.
