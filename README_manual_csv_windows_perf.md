# Manual CSV Recording + Windows Performance Notes

## What changed

- Connecting/polling BMS no longer starts CSV writing automatically.
- Connecting/polling PCS no longer starts CSV writing automatically.
- BMS Devices page:
  - Start BMS CSV
  - Stop BMS CSV
- PCS Devices page:
  - Start PCS CSV
  - Stop PCS CSV
- CSV writes are buffered through the existing async recorder queue.
- CSV file flushing is reduced to about every 100 rows or on stop/close.
- Qt software rendering is enabled before PySide6 is imported to reduce Windows/HP graphics lag.

## Recommended workflow

1. Add/connect BMS or PCS.
2. Confirm live values update normally.
3. Click Start BMS CSV / Start PCS CSV only when you actually need recording.
4. Click Stop BMS CSV / Stop PCS CSV before long idle periods or before disconnecting devices.

## Windows notes

For best performance, avoid writing logs/csv/cache to OneDrive/Desktop/Downloads. Use a local folder such as:

```text
C:\Users\<user>\Documents\ESS-AIO\logs
```

