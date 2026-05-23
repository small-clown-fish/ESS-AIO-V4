# v3.11 PCS Manual Connect + Windows Packaging Fix

## PCS startup / reconnect behavior
- Startup now supports a clean BMS-only state: no default PCS is created or bound to Cluster-1.
- `pcs_configs.json` default is `{}` and `site_config.json` default has empty `pcs_device` / `pcs_devices`.
- Adding or updating a PCS only saves the device configuration. It does not start polling or connect automatically.
- PCS connection is only started by the operator via `Connect selected PCS` or `Connect all PCS`.
- Background service checks now skip PCS power tracking and PCS fault protection when the cluster has no bound PCS, or the PCS is disabled/missing host. This prevents repeated connection attempts when testing BMS only.
- The last PCS device can now be removed; an empty PCS list is valid.

## Windows packaging hardening
- Runtime profiles are stored under the user data folder instead of the installation/current working directory:
  - Windows: `%APPDATA%/ESS-AIO/profiles`
  - macOS: `~/Library/Application Support/ESS-AIO/profiles`
  - Linux: `~/.local/share/ESS-AIO/profiles`
- Crash logs and audit/log folders are moved to user data paths to avoid write failures in packaged Windows builds.
- The GitHub Actions Windows build no longer bundles stale `profiles`, `pcs_config.json`, `runtime_config.json`, or `site_config.json` as active runtime data.
- Bundled sample/default profile data was cleaned so it no longer contains enabled unreachable PCS IPs.
- `__pycache__` folders and nested old zip artifacts are excluded from the delivered zip.
