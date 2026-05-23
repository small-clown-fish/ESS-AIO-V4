# ESS-AIO v3.11 Unified README

This package includes:

- Multi BMS / Multi PCS support
- PCS Profiles (Kehua/SMA/Extensible)
- Cluster-based EMS workflow
- Dynamic BMS power clamp
- PCS live status + heartbeat
- SQLite packet cache
- CAN/Modbus diagnosis
- CSV logging
- Individual polling/connect control

## Main UI Areas

- Project: cluster / device management
- Control: BMS + PCS workflow
- Packet Analyzer: CAN / Modbus / Wireshark analysis
- Strategy: EMS policy logic
- Settings: application/system settings

## Notes

- PCS profiles are under `pcs_profiles/`
- CSV logs are generated automatically during polling
- Packet cache uses SQLite
- Recommended polling interval: 1s

## Common Workflow

1. Add BMS devices
2. Add PCS devices
3. Bind them into a cluster
4. Connect/poll devices
5. Start BMS heartbeat
6. Start workflow / dispatch power

## Consolidated READMEs

- README.md
- README_v3_driver_phase.md
- README_v3_data_model_phase.md
- README_v32_controller_phase.md
- README_v32_controller_phase3.md
- README_v32_phase4_action_result.md
- README_v32_phase5_app_facade.md
- README_v33_packet_analyzer_ESS_AIO.md
- README_RELEASE.md
- README_v362_dbc_stable_fix.md
- README_v37_unified_timeline.md
- README_v22_joint_analysis.md
- README_mbd4_18_packet_semantics.md
- README_packet_diagnosis.md
- README_mapping_under_0x0400_fix.md
- README_diagnosis_v2_span_highlight.md
- README_packet_analyzer_usability_v3.md
- README_sqlite_packet_cache.md
- README_packet_paging_sqlite_v4.md
- README_engineering_fault_templates.md
- README_kehua_pcs_control.md
- README_charge_discharge_workflow.md
- README_multi_pcs_device_ui.md
- README_pcs_profiles_flexible.md
- README_project_cluster_overview_tab.md
- README_project_cluster_overview_inline.md
- README_power_target_with_bms_clamp.md
- README_pcs_live_status_heartbeat.md
- README_cluster_power_allocator.md
- README_bms_pcs_individual_polling_csv.md
- README_pcs_status_table_connect.md
- README_pcs_ui_performance_fix.md
- README_ui_readability_polish.md
- README_pcs_table_readability_scroll_fix.md
- README_TEMPLATE_PACKAGES.md