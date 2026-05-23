from __future__ import annotations

from pathlib import Path
import csv
from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QMessageBox,
    QSizePolicy,
)

def _build_control_tab(self, tabs: QTabWidget) -> None:
        control_tab = QScrollArea()
        control_tab.setWidgetResizable(True)

        control_content = QWidget()
        control_root = QVBoxLayout(control_content)
        control_root.setContentsMargins(14, 14, 14, 14)
        control_root.setSpacing(14)
        control_tab.setWidget(control_content)

        control_top_row = QHBoxLayout()
        self.control_device_label = QLabel("Current device: -")
        control_top_row.addWidget(self.control_device_label)
        control_top_row.addSpacing(20)
        control_top_row.addWidget(QLabel("Select device:"))

        self.control_device_combo = QComboBox()
        self.control_device_combo.currentTextChanged.connect(self.on_control_device_changed)
        control_top_row.addWidget(self.control_device_combo)
        control_top_row.addStretch()
        control_root.addLayout(control_top_row)

        control_inner_tabs = QTabWidget()
        control_inner_tabs.setObjectName("ControlInnerTabs")
        control_root.addWidget(control_inner_tabs)

        bms_control_page = QWidget()
        bms_layout = QVBoxLayout(bms_control_page)
        bms_layout.setContentsMargins(4, 8, 4, 4)
        bms_layout.setSpacing(12)
        self._build_bms_control_column(bms_layout)
        control_inner_tabs.addTab(bms_control_page, "BMS Control")

        self.pcs_control_tab_index = -1
        if getattr(self, "pcs_control_ui_enabled", True):
            pcs_control_page = QWidget()
            pcs_layout = QVBoxLayout(pcs_control_page)
            pcs_layout.setContentsMargins(4, 8, 4, 4)
            pcs_layout.setSpacing(12)
            self._build_pcs_control_column(pcs_layout)
            self.pcs_control_tab_index = control_inner_tabs.addTab(pcs_control_page, "PCS Control")
        else:
            info = QLabel("PCS Control is disabled for this release. Enable it in Settings if needed.")
            info.setObjectName("PageHint")
            control_root.addWidget(info)

        tabs.addTab(control_tab, "Control")

def _build_bms_control_column(self, parent: QVBoxLayout) -> None:
        status_wrap = QGroupBox("BMS / Workflow Status")
        status_layout = QFormLayout(status_wrap)
        self.control_state_label = QLabel("Idle")
        self.heartbeat_state_label = QLabel("Stopped")
        self.last_control_result_label = QLabel("-")
        self.last_ems_cmd_result_label = QLabel("-")
        self.pcs_config_state_label = QLabel("Loaded" if self.pcs_config.get("enabled", False) else "Disabled / Missing")

        status_layout.addRow("Control State", self.control_state_label)
        status_layout.addRow("Heartbeat State", self.heartbeat_state_label)
        status_layout.addRow("Last Result", self.last_control_result_label)
        status_layout.addRow("Last EMS Cmd Result", self.last_ems_cmd_result_label)
        status_layout.addRow("PCS Config", self.pcs_config_state_label)
        parent.addWidget(status_wrap)

        bms_basic_group = QGroupBox("BMS Heartbeat / Basic Control")
        bms_basic_layout = QHBoxLayout(bms_basic_group)
        self.start_heartbeat_btn = QPushButton("Start Heartbeat")
        self.stop_heartbeat_btn = QPushButton("Stop Heartbeat")
        self.clear_fault_btn = QPushButton("Clear Fault")
        self.bms_debug_status_btn = QPushButton("Read BMS Debug")
        self.bms_debug_status_btn.clicked.connect(self.handle_read_bms_debug_status)
        self.bms_version_btn = QPushButton("Read BMS Version")
        self.bms_version_btn.clicked.connect(self.handle_read_bms_version)
        self.start_all_bms_hb_btn = QPushButton("Start All BMS HB")
        self.stop_all_bms_hb_btn = QPushButton("Stop All BMS HB")

        self.start_heartbeat_btn.clicked.connect(self.handle_start_heartbeat)
        self.stop_heartbeat_btn.clicked.connect(self.handle_stop_heartbeat)
        self.clear_fault_btn.clicked.connect(self.handle_clear_fault)
        self.start_all_bms_hb_btn.clicked.connect(self.handle_start_all_bms_heartbeats)
        self.stop_all_bms_hb_btn.clicked.connect(self.handle_stop_all_bms_heartbeats)

        bms_basic_layout.addWidget(self.start_heartbeat_btn)
        bms_basic_layout.addWidget(self.stop_heartbeat_btn)
        bms_basic_layout.addWidget(self.clear_fault_btn)
        bms_basic_layout.addWidget(self.bms_debug_status_btn)
        bms_basic_layout.addWidget(self.bms_version_btn)
        bms_basic_layout.addWidget(self.start_all_bms_hb_btn)
        bms_basic_layout.addWidget(self.stop_all_bms_hb_btn)
        bms_basic_layout.addStretch()
        parent.addWidget(bms_basic_group)

        insulation_group = QGroupBox("BMS Periodic Insulation Monitor Disable (038B)")
        insulation_layout = QHBoxLayout(insulation_group)
        self.bms_insulation_interval_spin = QSpinBox()
        self.bms_insulation_interval_spin.setRange(1, 1440)
        self.bms_insulation_interval_spin.setValue(15)
        self.bms_insulation_interval_spin.setSuffix(" min")
        self.start_bms_insulation_timer_btn = QPushButton("Start 038B=2 Cycle")
        self.stop_bms_insulation_timer_btn = QPushButton("Stop 038B Cycle")
        self.bms_insulation_state_label = QLabel("038B cycle: stopped")
        self.start_bms_insulation_timer_btn.clicked.connect(self.handle_start_bms_insulation_disable_cycle)
        self.stop_bms_insulation_timer_btn.clicked.connect(self.handle_stop_bms_insulation_disable_cycle)
        insulation_layout.addWidget(QLabel("Interval"))
        insulation_layout.addWidget(self.bms_insulation_interval_spin)
        insulation_layout.addWidget(self.start_bms_insulation_timer_btn)
        insulation_layout.addWidget(self.stop_bms_insulation_timer_btn)
        insulation_layout.addWidget(self.bms_insulation_state_label)
        insulation_layout.addStretch()
        parent.addWidget(insulation_group)

        ems_cmd_group = QGroupBox("BMS Manual EMS Cmd (0381)")
        ems_cmd_layout = QHBoxLayout(ems_cmd_group)
        self.ems_stay_btn = QPushButton("Write Stay (1)")
        self.ems_power_on_btn = QPushButton("Write Power On (2)")
        self.ems_power_off_btn = QPushButton("Write Power Off (3)")

        self.ems_stay_btn.clicked.connect(self.handle_ems_cmd_stay)
        self.ems_power_on_btn.clicked.connect(self.handle_ems_cmd_power_on)
        self.ems_power_off_btn.clicked.connect(self.handle_ems_cmd_power_off)

        ems_cmd_layout.addWidget(self.ems_stay_btn)
        ems_cmd_layout.addWidget(self.ems_power_on_btn)
        ems_cmd_layout.addWidget(self.ems_power_off_btn)
        ems_cmd_layout.addStretch()
        parent.addWidget(ems_cmd_group)

        hv_group = QGroupBox("HV Workflow")
        hv_layout = QHBoxLayout(hv_group)
        self.hv_on_btn = QPushButton("HV On Workflow")
        self.hv_off_btn = QPushButton("HV Off Workflow")
        self.hv_cancel_btn = QPushButton("Cancel HV Workflow")
        self.ignore_pcs_checks_checkbox = QCheckBox("Ignore PCS checks")
        self.ignore_pcs_checks_checkbox.setToolTip(
            "Skip all PCS-side prechecks/actions in HV ON/OFF. "
            "Use only when the operator has manually confirmed PCS conditions."
        )

        self.hv_on_btn.clicked.connect(self.handle_hv_on)
        self.hv_off_btn.clicked.connect(self.handle_hv_off)
        self.hv_cancel_btn.clicked.connect(self.handle_cancel_hv_workflow)

        hv_layout.addWidget(self.hv_on_btn)
        hv_layout.addWidget(self.hv_off_btn)
        hv_layout.addWidget(self.hv_cancel_btn)
        hv_layout.addWidget(self.ignore_pcs_checks_checkbox)
        hv_layout.addStretch()
        parent.addWidget(hv_group)

        log_group = QGroupBox("Control Log")
        log_layout = QVBoxLayout(log_group)
        self.control_log_text = QTextEdit()
        self.control_log_text.setReadOnly(True)
        self.control_log_text.setMinimumHeight(220)
        self.control_log_text.setMaximumHeight(320)
        log_layout.addWidget(self.control_log_text)
        parent.addWidget(log_group)
        parent.addStretch()

def _build_pcs_control_column(self, parent: QVBoxLayout) -> None:
        pcs_select_group = QGroupBox("PCS Selection")
        pcs_select_layout = QHBoxLayout(pcs_select_group)
        self.control_pcs_combo = QComboBox()
        self.control_pcs_combo.setMinimumWidth(260)
        self.control_pcs_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.control_pcs_combo.currentTextChanged.connect(self.on_control_pcs_changed)
        self.refresh_control_pcs_combo_btn = QPushButton("Refresh PCS List")
        self.refresh_control_pcs_combo_btn.clicked.connect(self.refresh_pcs_view)
        pcs_select_layout.addWidget(QLabel("PCS:"))
        pcs_select_layout.addWidget(self.control_pcs_combo)
        pcs_select_layout.addWidget(self.refresh_control_pcs_combo_btn)
        pcs_select_layout.addStretch()
        parent.addWidget(pcs_select_group)

        pcs_status_group = QGroupBox("PCS Status")
        pcs_status_layout = QGridLayout(pcs_status_group)

        pcs_status_fields = [
            ("online", "PCS Online"),
            ("run_status", "Run Status"),
            ("fault_status", "Fault Status"),
            ("alarm_status", "Alarm Status"),
            ("dc_breaker", "DC Breaker"),
            ("active_power", "Active Power"),
            ("mode", "Mode"),
            ("remote_local", "Remote/Local"),
        ]

        for i, (key, title) in enumerate(pcs_status_fields):
            name_label = QLabel(title + ":")
            value_label = QLabel("-")
            value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.pcs_status_labels[key] = value_label

            row = i // 2
            col = (i % 2) * 2
            pcs_status_layout.addWidget(name_label, row, col)
            pcs_status_layout.addWidget(value_label, row, col + 1)

        refresh_row = QHBoxLayout()
        self.refresh_pcs_status_btn = QPushButton("Refresh PCS Status")
        self.test_pcs_config_btn = QPushButton("Test PCS Config")
        self.test_pcs_config_btn.clicked.connect(self.handle_test_pcs_config)
        self.refresh_pcs_status_btn.clicked.connect(self.handle_refresh_pcs_status)
        refresh_row.addWidget(self.refresh_pcs_status_btn)
        refresh_row.addWidget(self.test_pcs_config_btn)
        refresh_row.addStretch()
        pcs_status_layout.addLayout(refresh_row, 4, 0, 1, 4)
        parent.addWidget(pcs_status_group)

        pcs_live_group = QGroupBox("PCS Live Registers")
        pcs_live_layout = QVBoxLayout(pcs_live_group)
        self.pcs_live_table = QTableWidget(0, 7)
        self.pcs_live_table.setHorizontalHeaderLabels(["Point", "Address", "Name", "Raw", "Value", "Unit", "Meaning/Error"])
        live_header = self.pcs_live_table.horizontalHeader()
        live_header.setSectionResizeMode(QHeaderView.Interactive)
        live_header.setStretchLastSection(True)
        self.pcs_live_table.setWordWrap(False)
        self.pcs_live_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.pcs_live_table.setMinimumHeight(300)
        self.pcs_live_table.setAlternatingRowColors(True)
        for i, width in enumerate([150, 90, 230, 90, 110, 70, 260]):
            self.pcs_live_table.setColumnWidth(i, width)
        pcs_live_layout.addWidget(self.pcs_live_table)

        pcs_live_btn_row = QHBoxLayout()
        self.refresh_pcs_live_btn = QPushButton("Refresh PCS Live Registers")
        self.refresh_pcs_live_btn.clicked.connect(self.handle_refresh_pcs_live_status)
        self.pcs_live_auto_check = QCheckBox("Auto refresh")
        self.pcs_live_auto_check.toggled.connect(self.handle_toggle_pcs_live_auto_refresh)
        self.pcs_live_interval_spin = QDoubleSpinBox()
        self.pcs_live_interval_spin.setRange(0.5, 60.0)
        self.pcs_live_interval_spin.setDecimals(1)
        self.pcs_live_interval_spin.setValue(2.0)
        self.pcs_live_interval_spin.setSuffix(" s")
        self.pcs_hb_start_btn = QPushButton("Start PCS Heartbeat")
        self.pcs_hb_stop_btn = QPushButton("Stop PCS Heartbeat")
        self.fleet_hb_start_btn = QPushButton("Start 72 Heartbeats")
        self.fleet_hb_stop_btn = QPushButton("Stop 72 Heartbeats")
        self.fleet_status_btn = QPushButton("Fleet Status")
        self.pcs_hb_start_btn.clicked.connect(self.handle_start_pcs_heartbeat)
        self.pcs_hb_stop_btn.clicked.connect(self.handle_stop_pcs_heartbeat)
        self.fleet_hb_start_btn.clicked.connect(self.handle_start_fleet_heartbeats)
        self.fleet_hb_stop_btn.clicked.connect(self.handle_stop_fleet_heartbeats)
        self.fleet_status_btn.clicked.connect(self.handle_fleet_status_summary)
        self.pcs_hb_state_label = QLabel("PCS HB: stopped")
        pcs_live_btn_row.addWidget(self.refresh_pcs_live_btn)
        pcs_live_btn_row.addWidget(self.pcs_live_auto_check)
        pcs_live_btn_row.addWidget(QLabel("Interval"))
        pcs_live_btn_row.addWidget(self.pcs_live_interval_spin)
        pcs_live_btn_row.addWidget(self.pcs_hb_start_btn)
        pcs_live_btn_row.addWidget(self.pcs_hb_stop_btn)
        pcs_live_btn_row.addWidget(self.fleet_hb_start_btn)
        pcs_live_btn_row.addWidget(self.fleet_hb_stop_btn)
        pcs_live_btn_row.addWidget(self.fleet_status_btn)
        pcs_live_btn_row.addWidget(self.pcs_hb_state_label)
        pcs_live_btn_row.addStretch()
        pcs_live_layout.addLayout(pcs_live_btn_row)

        self.pcs_live_timer = QTimer(self)
        self.pcs_live_timer.timeout.connect(self.handle_refresh_pcs_live_status)
        self.pcs_heartbeat_timer = QTimer(self)
        self.pcs_heartbeat_timer.timeout.connect(self.handle_pcs_heartbeat_tick)
        self.pcs_heartbeat_value = 0
        parent.addWidget(pcs_live_group)


        pcs_manual_group = QGroupBox("PCS Manual Control")
        pcs_manual_layout = QVBoxLayout(pcs_manual_group)

        pcs_btn_row1 = QHBoxLayout()
        self.pcs_start_btn = QPushButton("PCS Start")
        self.pcs_stop_btn = QPushButton("PCS Stop")

        self.pcs_reset_fault_btn = QPushButton("PCS Reset Fault")
        self.pcs_debug_status_btn = QPushButton("Read PCS Debug")
        self.pcs_debug_status_btn.clicked.connect(self.handle_read_pcs_debug_status)

        self.pcs_start_btn.clicked.connect(self.handle_pcs_start)
        self.pcs_stop_btn.clicked.connect(self.handle_pcs_stop)
        self.pcs_reset_fault_btn.clicked.connect(self.handle_pcs_reset_fault)

        pcs_btn_row1.addWidget(self.pcs_start_btn)
        pcs_btn_row1.addWidget(self.pcs_stop_btn)
        pcs_btn_row1.addWidget(self.pcs_reset_fault_btn)
        pcs_btn_row1.addWidget(self.pcs_debug_status_btn)
        pcs_btn_row1.addStretch()
        pcs_manual_layout.addLayout(pcs_btn_row1)

        pcs_btn_row2 = QHBoxLayout()
        self.pcs_hv_on_btn = QPushButton("PCS HV On")
        self.pcs_hv_off_btn = QPushButton("PCS HV Off")
        self.pcs_close_dc_breaker_btn = QPushButton("Close DC Breaker")
        self.pcs_open_dc_breaker_btn = QPushButton("Open DC Breaker")

        self.pcs_hv_on_btn.clicked.connect(self.handle_pcs_hv_on)
        self.pcs_hv_off_btn.clicked.connect(self.handle_pcs_hv_off)
        self.pcs_close_dc_breaker_btn.clicked.connect(self.handle_pcs_close_dc_breaker)
        self.pcs_open_dc_breaker_btn.clicked.connect(self.handle_pcs_open_dc_breaker)

        pcs_btn_row2.addWidget(self.pcs_hv_on_btn)
        pcs_btn_row2.addWidget(self.pcs_hv_off_btn)
        pcs_btn_row2.addWidget(self.pcs_close_dc_breaker_btn)
        pcs_btn_row2.addWidget(self.pcs_open_dc_breaker_btn)
        pcs_btn_row2.addStretch()
        pcs_manual_layout.addLayout(pcs_btn_row2)

        pcs_btn_row3 = QHBoxLayout()
        self.pcs_stop_debug_btn = QPushButton("Stop Debug")
        self.pcs_start_debug_btn = QPushButton("Start Debug")
        self.pcs_hv_on_debug_btn = QPushButton("HV On Debug")
        self.pcs_hv_off_debug_btn = QPushButton("HV Off Debug")

        self.pcs_stop_debug_btn.clicked.connect(self.handle_pcs_stop_debug)
        self.pcs_start_debug_btn.clicked.connect(self.handle_pcs_start_debug)
        self.pcs_hv_on_debug_btn.clicked.connect(self.handle_pcs_hv_on_debug)
        self.pcs_hv_off_debug_btn.clicked.connect(self.handle_pcs_hv_off_debug)

        pcs_btn_row3.addWidget(self.pcs_stop_debug_btn)
        pcs_btn_row3.addWidget(self.pcs_start_debug_btn)
        pcs_btn_row3.addWidget(self.pcs_hv_on_debug_btn)
        pcs_btn_row3.addWidget(self.pcs_hv_off_debug_btn)
        pcs_btn_row3.addStretch()
        pcs_manual_layout.addLayout(pcs_btn_row3)

        self.pcs_active_power_spin = QDoubleSpinBox()
        self.pcs_active_power_spin.setRange(-100000.0, 100000.0)
        self.pcs_active_power_spin.setDecimals(1)
        self.pcs_active_power_spin.setValue(0.0)
        self.pcs_active_power_spin.setSuffix(" kW")

        self.pcs_reactive_power_spin = QDoubleSpinBox()
        self.pcs_reactive_power_spin.setRange(-100000.0, 100000.0)
        self.pcs_reactive_power_spin.setDecimals(1)
        self.pcs_reactive_power_spin.setValue(0.0)
        self.pcs_reactive_power_spin.setSuffix(" kvar")

        self.pcs_set_active_power_btn = QPushButton("Set Active Power")
        self.fleet_set_active_power_btn = QPushButton("Fleet Set Active")
        self.pcs_set_reactive_power_btn = QPushButton("Set Reactive Power")
        self.fleet_set_reactive_power_btn = QPushButton("Fleet Set Reactive")
        self.fleet_pcs_start_btn = QPushButton("Fleet PCS Start")
        self.fleet_pcs_stop_btn = QPushButton("Fleet PCS Stop")
        self.pcs_set_active_power_btn.clicked.connect(self.handle_set_pcs_active_power)
        self.fleet_set_active_power_btn.clicked.connect(self.handle_fleet_set_active_power)
        self.pcs_set_reactive_power_btn.clicked.connect(self.handle_set_pcs_reactive_power)
        self.fleet_set_reactive_power_btn.clicked.connect(self.handle_fleet_set_reactive_power)
        self.fleet_pcs_start_btn.clicked.connect(self.handle_fleet_pcs_start)
        self.fleet_pcs_stop_btn.clicked.connect(self.handle_fleet_pcs_stop)

        pcs_power_row = QHBoxLayout()
        pcs_power_row.addWidget(QLabel("Active Power"))
        pcs_power_row.addWidget(self.pcs_active_power_spin)
        pcs_power_row.addWidget(self.pcs_set_active_power_btn)
        pcs_power_row.addWidget(self.fleet_set_active_power_btn)
        pcs_power_row.addStretch()

        pcs_reactive_row = QHBoxLayout()
        pcs_reactive_row.addWidget(QLabel("Reactive Power"))
        pcs_reactive_row.addWidget(self.pcs_reactive_power_spin)
        pcs_reactive_row.addWidget(self.pcs_set_reactive_power_btn)
        pcs_reactive_row.addWidget(self.fleet_set_reactive_power_btn)
        pcs_reactive_row.addWidget(self.fleet_pcs_start_btn)
        pcs_reactive_row.addWidget(self.fleet_pcs_stop_btn)
        pcs_reactive_row.addStretch()

        pcs_manual_layout.addLayout(pcs_power_row)
        pcs_manual_layout.addLayout(pcs_reactive_row)

        parent.addWidget(pcs_manual_group)

        workflow_group = QGroupBox("BMS + PCS Charge/Discharge Workflow")
        workflow_layout = QVBoxLayout(workflow_group)

        workflow_grid = QGridLayout()
        self.cd_mode_combo = QComboBox()
        self.cd_mode_combo.setMinimumWidth(220)
        self.cd_mode_combo.addItems(["discharge", "charge", "signed"])
        self.cd_power_spin = QDoubleSpinBox()
        self.cd_power_spin.setRange(-100000.0, 100000.0)
        self.cd_power_spin.setDecimals(1)
        self.cd_power_spin.setValue(50.0)
        self.cd_power_spin.setSuffix(" kW")
        self.cd_ramp_step_spin = QDoubleSpinBox()
        self.cd_ramp_step_spin.setRange(1.0, 100000.0)
        self.cd_ramp_step_spin.setDecimals(1)
        self.cd_ramp_step_spin.setValue(20.0)
        self.cd_ramp_step_spin.setSuffix(" kW/step")
        self.cd_ramp_interval_spin = QDoubleSpinBox()
        self.cd_ramp_interval_spin.setRange(0.2, 60.0)
        self.cd_ramp_interval_spin.setDecimals(1)
        self.cd_ramp_interval_spin.setValue(2.0)
        self.cd_ramp_interval_spin.setSuffix(" s")
        self.cd_positive_meaning_combo = QComboBox()
        self.cd_positive_meaning_combo.addItems(["+ = discharge", "+ = charge"])

        self.cd_use_bms_clamp_check = QCheckBox("Use BMS Limit Clamp")
        self.cd_use_bms_clamp_check.setChecked(True)
        self.cd_power_limit_mode_combo = QComboBox()
        self.cd_power_limit_mode_combo.addItems([
            "User Target with BMS Clamp",
            "Follow BMS Max Limit",
        ])
        self.cd_clamp_margin_spin = QDoubleSpinBox()
        self.cd_clamp_margin_spin.setRange(0.10, 1.00)
        self.cd_clamp_margin_spin.setDecimals(2)
        self.cd_clamp_margin_spin.setSingleStep(0.05)
        self.cd_clamp_margin_spin.setValue(1.00)

        self.cd_auto_bms_hv_check = QCheckBox("Auto BMS HV On")
        self.cd_auto_bms_hv_check.setChecked(True)
        self.cd_auto_pcs_start_check = QCheckBox("Auto PCS Start")
        self.cd_auto_pcs_start_check.setChecked(True)
        self.cd_auto_pcs_stop_check = QCheckBox("PCS Stop on Stop")
        self.cd_auto_pcs_stop_check.setChecked(True)
        self.cd_auto_bms_hv_off_check = QCheckBox("BMS HV Off on Stop")
        self.cd_auto_bms_hv_off_check.setChecked(False)
        self.cd_require_remote_check = QCheckBox("Require PCS Remote")
        self.cd_require_remote_check.setChecked(True)
        self.cd_require_dc_closed_check = QCheckBox("Require DC Breaker Closed")
        self.cd_require_dc_closed_check.setChecked(False)

        workflow_grid.addWidget(QLabel("Mode"), 0, 0)
        workflow_grid.addWidget(self.cd_mode_combo, 0, 1)
        workflow_grid.addWidget(QLabel("Target Power"), 0, 2)
        workflow_grid.addWidget(self.cd_power_spin, 0, 3)
        workflow_grid.addWidget(QLabel("Ramp Step"), 1, 0)
        workflow_grid.addWidget(self.cd_ramp_step_spin, 1, 1)
        workflow_grid.addWidget(QLabel("Ramp Interval"), 1, 2)
        workflow_grid.addWidget(self.cd_ramp_interval_spin, 1, 3)
        workflow_grid.addWidget(QLabel("PCS Sign"), 2, 0)
        workflow_grid.addWidget(self.cd_positive_meaning_combo, 2, 1)
        workflow_grid.addWidget(self.cd_use_bms_clamp_check, 2, 2)
        workflow_grid.addWidget(QLabel("Clamp Mode"), 3, 0)
        workflow_grid.addWidget(self.cd_power_limit_mode_combo, 3, 1)
        workflow_grid.addWidget(QLabel("Clamp Margin"), 3, 2)
        workflow_grid.addWidget(self.cd_clamp_margin_spin, 3, 3)
        workflow_grid.addWidget(self.cd_auto_bms_hv_check, 4, 0)
        workflow_grid.addWidget(self.cd_auto_pcs_start_check, 4, 1)
        workflow_grid.addWidget(self.cd_auto_pcs_stop_check, 4, 2)
        workflow_grid.addWidget(self.cd_auto_bms_hv_off_check, 4, 3)
        workflow_grid.addWidget(self.cd_require_remote_check, 5, 0)
        workflow_grid.addWidget(self.cd_require_dc_closed_check, 5, 1)
        workflow_layout.addLayout(workflow_grid)

        workflow_btn_row = QHBoxLayout()
        self.cd_start_btn = QPushButton("Start Workflow")
        self.cd_stop_btn = QPushButton("Stop Workflow")
        self.cd_cancel_btn = QPushButton("Cancel Workflow")
        self.cd_start_btn.clicked.connect(self.handle_cd_start_workflow)
        self.cd_stop_btn.clicked.connect(self.handle_cd_stop_workflow)
        self.cd_cancel_btn.clicked.connect(self.handle_cd_cancel_workflow)
        workflow_btn_row.addWidget(self.cd_start_btn)
        workflow_btn_row.addWidget(self.cd_stop_btn)
        workflow_btn_row.addWidget(self.cd_cancel_btn)
        workflow_btn_row.addStretch()
        workflow_layout.addLayout(workflow_btn_row)
        self.cd_status_label = QLabel("Idle")
        workflow_layout.addWidget(self.cd_status_label)
        workflow_layout.addWidget(QLabel("Note: Default clamp mode uses your target power and only reduces it if BMS allowed current/power is lower."))
        workflow_layout.addWidget(QLabel("Example: target=50kW, BMS allows=260kW -> PCS setpoint=50kW; target=500kW -> setpoint=260kW."))
        parent.addWidget(workflow_group)

        cluster_group = QGroupBox("Cluster Dispatch (1 BMS + N PCS)")
        cluster_layout = QVBoxLayout(cluster_group)
        cluster_grid = QGridLayout()
        self.cluster_dispatch_combo = QComboBox()
        self.cluster_dispatch_combo.setMinimumWidth(240)
        self.cluster_dispatch_mode_combo = QComboBox()
        self.cluster_dispatch_mode_combo.addItems(["equal_split", "capacity_weighted"])
        self.cluster_dispatch_fault_combo = QComboBox()
        self.cluster_dispatch_fault_combo.addItems(["stop_all", "redistribute"])
        self.cluster_dispatch_power_spin = QDoubleSpinBox()
        self.cluster_dispatch_power_spin.setRange(-100000.0, 100000.0)
        self.cluster_dispatch_power_spin.setDecimals(1)
        self.cluster_dispatch_power_spin.setValue(50.0)
        self.cluster_dispatch_power_spin.setSuffix(" kW")
        self.cluster_dispatch_use_clamp_check = QCheckBox("Use BMS Total Limit Clamp")
        self.cluster_dispatch_use_clamp_check.setChecked(True)
        self.cluster_dispatch_margin_spin = QDoubleSpinBox()
        self.cluster_dispatch_margin_spin.setRange(0.10, 1.00)
        self.cluster_dispatch_margin_spin.setDecimals(2)
        self.cluster_dispatch_margin_spin.setSingleStep(0.05)
        self.cluster_dispatch_margin_spin.setValue(1.00)

        cluster_grid.addWidget(QLabel("Cluster"), 0, 0)
        cluster_grid.addWidget(self.cluster_dispatch_combo, 0, 1)
        cluster_grid.addWidget(QLabel("Target Total Power"), 0, 2)
        cluster_grid.addWidget(self.cluster_dispatch_power_spin, 0, 3)
        cluster_grid.addWidget(QLabel("Allocation"), 1, 0)
        cluster_grid.addWidget(self.cluster_dispatch_mode_combo, 1, 1)
        cluster_grid.addWidget(QLabel("Fault Strategy"), 1, 2)
        cluster_grid.addWidget(self.cluster_dispatch_fault_combo, 1, 3)
        cluster_grid.addWidget(self.cluster_dispatch_use_clamp_check, 2, 0, 1, 2)
        cluster_grid.addWidget(QLabel("Clamp Margin"), 2, 2)
        cluster_grid.addWidget(self.cluster_dispatch_margin_spin, 2, 3)
        cluster_layout.addLayout(cluster_grid)

        cluster_btn_row = QHBoxLayout()
        self.cluster_dispatch_apply_btn = QPushButton("Apply Cluster Power Once")
        self.cluster_dispatch_stop_btn = QPushButton("Stop All PCS in Cluster")
        self.cluster_dispatch_apply_btn.clicked.connect(self.handle_cluster_dispatch_once)
        self.cluster_dispatch_stop_btn.clicked.connect(self.handle_cluster_stop_all)
        cluster_btn_row.addWidget(self.cluster_dispatch_apply_btn)
        cluster_btn_row.addWidget(self.cluster_dispatch_stop_btn)
        cluster_btn_row.addStretch()
        cluster_layout.addLayout(cluster_btn_row)
        self.cluster_dispatch_status_label = QLabel("Cluster dispatch idle")
        cluster_layout.addWidget(self.cluster_dispatch_status_label)
        parent.addWidget(cluster_group)
        parent.addStretch()

