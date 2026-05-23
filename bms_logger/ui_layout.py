from __future__ import annotations

# v3.1 UI refactor:
# This file now only composes page-builder functions. Individual pages live under
# bms_logger/ui_pages/*.py so future UI changes stay isolated and maintainable.

from .ui_pages.core_layout import _build_menu as _build_menu_core_layout
from .ui_pages.core_layout import _build_ui as _build_ui_core_layout
from .ui_pages.core_layout import _build_global_status as _build_global_status_core_layout
from .ui_pages.core_layout import _apply_comfortable_style as _apply_comfortable_style_core_layout
from .ui_pages.core_layout import _create_chart as _create_chart_core_layout
from .ui_pages.overview_page import _build_overview_tab as _build_overview_tab_overview_page
from .ui_pages.devices_page import _build_devices_tab as _build_devices_tab_devices_page
from .ui_pages.devices_page import _build_pcs_devices_tab as _build_pcs_devices_tab_devices_page
from .ui_pages.curves_page import _build_curves_tab as _build_curves_tab_curves_page
from .ui_pages.curves_page import _build_driver_points_tab as _build_driver_points_tab_curves_page
from .ui_pages.details_page import _build_details_tab as _build_details_tab_details_page
from .ui_pages.alarms_page import _build_alarms_tab as _build_alarms_tab_alarms_page
from .ui_pages.alarms_page import _build_alarm_analysis_tab as _build_alarm_analysis_tab_alarms_page
from .ui_pages.control_page import _build_control_tab as _build_control_tab_control_page
from .ui_pages.control_page import _build_bms_control_column as _build_bms_control_column_control_page
from .ui_pages.control_page import _build_pcs_control_column as _build_pcs_control_column_control_page
from .ui_pages.diagnostics_page import _build_diagnostics_tab as _build_diagnostics_tab_diagnostics_page
from .ui_pages.diagnostics_page import _build_register_debug_tab as _build_register_debug_tab_diagnostics_page
from .ui_pages.replay_page import _build_replay_tab as _build_replay_tab_replay_page
from .ui_pages.scheduler_page import _build_scheduler_tab as _build_scheduler_tab_scheduler_page
from .ui_pages.settings_page import _build_settings_tab as _build_settings_tab_settings_page
from .ui_pages.logs_page import _build_logs_tab as _build_logs_tab_logs_page
from .ui_pages.site_page import _build_site_tab as _build_site_tab_site_page
from .ui_pages.site_page import add_cluster as add_cluster_site_page
from .ui_pages.templates_page import _build_templates_tab as _build_templates_tab_templates_page
from .ui_pages.strategy_page import _build_strategy_tab as _build_strategy_tab_strategy_page
from .ui_pages.packet_page import _build_packet_analyzer_tab as _build_packet_analyzer_tab_packet_page
from .ui_pages.packet_page import _build_modbus_packet_tab as _build_modbus_packet_tab_packet_page
from .ui_pages.packet_page import _build_can_packet_tab as _build_can_packet_tab_packet_page
from .ui_pages.packet_page import _build_joint_analysis_tab as _build_joint_analysis_tab_packet_page
from .ui_pages.packet_page import _build_packet_diagnosis_tab as _build_packet_diagnosis_tab_packet_page
from .ui_pages.timeline_page import _build_timeline_tab as _build_timeline_tab_timeline_page
from .ui_pages.report_page import _build_report_tab as _build_report_tab_report_page
from .ui_pages.release_page import _build_release_tab as _build_release_tab_release_page

class UiLayoutMixin:
    _build_menu = _build_menu_core_layout
    _build_ui = _build_ui_core_layout
    _build_global_status = _build_global_status_core_layout
    _apply_comfortable_style = _apply_comfortable_style_core_layout
    _create_chart = _create_chart_core_layout
    _build_overview_tab = _build_overview_tab_overview_page
    _build_devices_tab = _build_devices_tab_devices_page
    _build_pcs_devices_tab = _build_pcs_devices_tab_devices_page
    _build_curves_tab = _build_curves_tab_curves_page
    _build_driver_points_tab = _build_driver_points_tab_curves_page
    _build_details_tab = _build_details_tab_details_page
    _build_alarms_tab = _build_alarms_tab_alarms_page
    _build_alarm_analysis_tab = _build_alarm_analysis_tab_alarms_page
    _build_control_tab = _build_control_tab_control_page
    _build_bms_control_column = _build_bms_control_column_control_page
    _build_pcs_control_column = _build_pcs_control_column_control_page
    _build_diagnostics_tab = _build_diagnostics_tab_diagnostics_page
    _build_register_debug_tab = _build_register_debug_tab_diagnostics_page
    _build_replay_tab = _build_replay_tab_replay_page
    _build_scheduler_tab = _build_scheduler_tab_scheduler_page
    _build_settings_tab = _build_settings_tab_settings_page
    _build_logs_tab = _build_logs_tab_logs_page
    _build_site_tab = _build_site_tab_site_page
    add_cluster = add_cluster_site_page
    _build_templates_tab = _build_templates_tab_templates_page
    _build_strategy_tab = _build_strategy_tab_strategy_page
    _build_packet_analyzer_tab = _build_packet_analyzer_tab_packet_page
    _build_modbus_packet_tab = _build_modbus_packet_tab_packet_page
    _build_can_packet_tab = _build_can_packet_tab_packet_page
    _build_joint_analysis_tab = _build_joint_analysis_tab_packet_page
    _build_packet_diagnosis_tab = _build_packet_diagnosis_tab_packet_page
    _build_timeline_tab = _build_timeline_tab_timeline_page
    _build_report_tab = _build_report_tab_report_page
    _build_release_tab = _build_release_tab_release_page
