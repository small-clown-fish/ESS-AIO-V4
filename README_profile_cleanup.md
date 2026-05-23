# ESS-AIO v3.11 Profile Cleanup Notes

This build reorganizes protocol configuration into selectable profiles.

## BMS profiles

Bundled profiles:

```text
bms_profiles/
  catl_v17/
    bms_register_map.json
    alarm_map.json
    profile.json

  catl_v22/
    bms_register_map.json
    alarm_map.json
    profile.json
```

When adding a BMS in Devices, choose the BMS Profile dropdown:
- CATL V17 BMS
- CATL V22 TenerS/TenerX BMS

Each BMS device stores only its connection settings and selected profile.

## PCS profiles

PCS remains profile-driven:

```text
pcs_profiles/
  kehua_bcs1250.json
  sma_template.json
  sineng_template.json
```

When adding a PCS in Project -> PCS Devices, choose the PCS Profile dropdown.

## PCS output path

PCS Devices now has an Output dir field. PCS polling CSV files are written there.

## Packet Analyzer CAN plot

Packet Analyzer -> CAN keeps the CAN Signal Plot section.
After loading CAN + DBC, the first decoded numeric signal is auto-selected so a plot appears immediately.
You can still add up to 4 signals manually.

## Packaging

Windows PyInstaller workflow now includes:

```text
bms_profiles/
pcs_profiles/
bms_logger/protocols/
profiles/
```

so BMS/PCS profiles are available after packaging.
