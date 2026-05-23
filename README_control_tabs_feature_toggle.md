# Control Page Split + PCS Control Feature Toggle

## Changes

The `Control` page now has internal tabs:

- `BMS Control`
- `PCS Control`

`BMS Control` contains BMS heartbeat, clear fault, EMS command, and HV workflow controls.

`PCS Control` contains PCS selection, live registers, PCS heartbeat, PCS manual control, charge/discharge workflow, and cluster dispatch.

## Disable PCS Control for release builds

Go to:

```text
Settings -> Runtime -> PCS Control UI
```

Set it to:

```text
Disabled
```

Then click:

```text
Apply Runtime Params
```

The setting is saved to `runtime_config.json` as:

```json
"pcs_control_ui_enabled": false
```

After restart, the PCS Control tab will be hidden.

## Notes

This only hides the PCS control UI. PCS devices/profiles can still exist in the project for future releases.
