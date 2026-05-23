from __future__ import annotations

from pathlib import Path
import csv
from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
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

def _build_devices_tab(self, tabs: QTabWidget) -> None:
        device_tab = QWidget()
        outer_layout = QVBoxLayout(device_tab)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        device_content = QWidget()
        device_layout = QVBoxLayout(device_content)
        device_layout.setContentsMargins(14, 14, 14, 14)
        device_layout.setSpacing(12)

        scroll_area.setWidget(device_content)
        outer_layout.addWidget(scroll_area)

        form_wrap = QGroupBox("Device Config")
        form = QGridLayout(form_wrap)

        self.name_edit = QLineEdit("BMS-1")
        self.host_edit = QLineEdit("127.0.0.1")

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(502)

        self.unit_spin = QSpinBox()
        self.unit_spin.setRange(0, 255)
        self.unit_spin.setValue(1)

        self.interval_spin = QDoubleSpinBox()
        self.interval_spin.setRange(0.2, 3600.0)
        self.interval_spin.setDecimals(1)
        self.interval_spin.setValue(2.0)
        self.interval_spin.setSuffix(" s")

        self.bms_fake_scenario_combo = QComboBox()
        self.bms_fake_scenario_combo.addItems(["normal", "high_voltage", "low_voltage", "offline", "fault", "alarm"])

        self.bms_profile_combo = QComboBox()
        self.bms_profile_combo.setMinimumWidth(220)
        self.bms_profile_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        if hasattr(self, "refresh_bms_profile_combo"):
            self.refresh_bms_profile_combo()

        self.output_dir_edit = QLineEdit(str(self.get_profile_path("output")))
        self.output_dir_btn = QPushButton("Browse...")
        self.output_dir_btn.clicked.connect(self.choose_output_dir)

        out_row = QWidget()
        out_layout = QHBoxLayout(out_row)
        out_layout.setContentsMargins(0, 0, 0, 0)
        out_layout.addWidget(self.output_dir_edit)
        out_layout.addWidget(self.output_dir_btn)

        fields = [
            ("Device name", self.name_edit),
            ("Host", self.host_edit),
            ("Port", self.port_spin),
            ("Unit ID", self.unit_spin),
            ("Sample interval", self.interval_spin),
            ("Fake scenario", self.bms_fake_scenario_combo),
            ("BMS Profile", self.bms_profile_combo),
            ("Output dir", out_row),
        ]

        for i, (title, widget) in enumerate(fields):
            row = i // 3
            col = (i % 3) * 2
            form.addWidget(QLabel(title), row, col)
            form.addWidget(widget, row, col + 1)

        device_layout.addWidget(form_wrap)

        btn_row = QHBoxLayout()
        self.add_device_btn = QPushButton("Add device")
        self.add_device_btn.clicked.connect(self.add_device)

        self.start_selected_btn = QPushButton("Start selected")
        self.start_selected_btn.clicked.connect(self.start_selected_device)

        self.stop_selected_btn = QPushButton("Stop selected")
        self.stop_selected_btn.clicked.connect(self.stop_selected_device)

        self.start_btn = QPushButton("Start all")
        self.start_btn.clicked.connect(self.start_all)

        self.stop_btn = QPushButton("Stop all")
        self.stop_btn.clicked.connect(self.stop_all)

        self.start_bms_csv_btn = QPushButton("Start BMS CSV")
        self.start_bms_csv_btn.setToolTip("Start CSV recording for selected BMS, or all BMS if no row is selected.")
        self.start_bms_csv_btn.clicked.connect(self.start_bms_csv_recording)

        self.stop_bms_csv_btn = QPushButton("Stop BMS CSV")
        self.stop_bms_csv_btn.setToolTip("Stop CSV recording for selected BMS, or all BMS if no row is selected.")
        self.stop_bms_csv_btn.clicked.connect(self.stop_bms_csv_recording)

        self.bms_csv_status_label = QLabel("BMS CSV: Recording OFF")
        self.bms_csv_status_label.setStyleSheet("color: #777; font-weight: 600;")

        self.remove_device_btn = QPushButton("Remove selected BMS")
        self.remove_device_btn.clicked.connect(self.remove_selected_device)

        btn_row.addWidget(self.add_device_btn)
        btn_row.addWidget(self.remove_device_btn)
        btn_row.addWidget(self.start_selected_btn)
        btn_row.addWidget(self.stop_selected_btn)
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.stop_btn)
        btn_row.addWidget(self.start_bms_csv_btn)
        btn_row.addWidget(self.stop_bms_csv_btn)
        btn_row.addWidget(self.bms_csv_status_label)
        btn_row.addStretch()
        device_layout.addLayout(btn_row)

        self.device_table = QTableWidget(0, 13)
        self.device_table.setHorizontalHeaderLabels(
            [
                "Name",
                "Host",
                "Port",
                "Unit ID",
                "Interval(s)",
                "BMS Status",
                "Racks",
                "SOC(%)",
                "Voltage(V)",
                "Current(A)",
                "Power(kW)",
                "Run State",
                "Online",
            ]
        )
        header = self.device_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        self.device_table.setMinimumHeight(260)
        self.device_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        self.device_table.cellClicked.connect(self.on_device_table_clicked)
        device_layout.addWidget(self.device_table)

        device_layout.addStretch(1)
        tabs.addTab(device_tab, "BMS Devices")


def _build_pcs_devices_tab(self, tabs: QTabWidget) -> None:
        pcs_tab = QWidget()
        outer_layout = QVBoxLayout(pcs_tab)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        pcs_content = QWidget()
        pcs_content_layout = QVBoxLayout(pcs_content)
        pcs_content_layout.setContentsMargins(14, 14, 14, 14)
        pcs_content_layout.setSpacing(12)

        scroll_area.setWidget(pcs_content)
        outer_layout.addWidget(scroll_area)

        pcs_group = QGroupBox("PCS Device Config")
        pcs_layout = QVBoxLayout(pcs_group)

        pcs_form = QGridLayout()
        pcs_form.setHorizontalSpacing(8)
        pcs_form.setVerticalSpacing(8)
        self.pcs_name_edit = QLineEdit("PCS-1")
        self.pcs_name_edit.setMinimumWidth(150)
        self.pcs_host_edit = QLineEdit("")
        self.pcs_host_edit.setMinimumWidth(145)
        self.pcs_port_spin = QSpinBox()
        self.pcs_port_spin.setRange(1, 65535)
        self.pcs_port_spin.setValue(502)
        self.pcs_unit_spin = QSpinBox()
        self.pcs_unit_spin.setRange(0, 255)
        self.pcs_unit_spin.setValue(1)
        self.pcs_enabled_combo = QComboBox()
        self.pcs_enabled_combo.addItems(["Enabled", "Disabled"])
        self.pcs_enabled_combo.setMinimumWidth(110)
        self.pcs_fake_scenario_combo = QComboBox()
        self.pcs_fake_scenario_combo.addItems(["normal", "offline", "fault", "breaker_open", "deviation", "alarm"])
        self.pcs_fake_scenario_combo.setMinimumWidth(130)
        self.pcs_profile_combo = QComboBox()
        self.pcs_profile_combo.setMinimumWidth(280)
        self.pcs_profile_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        if hasattr(self, "refresh_pcs_profile_combo"):
            self.refresh_pcs_profile_combo()
        self.pcs_output_dir_edit = QLineEdit(str(self.get_profile_path("output") / "pcs"))
        self.pcs_output_dir_edit.setMinimumWidth(220)
        self.pcs_output_dir_btn = QPushButton("Browse...")
        self.pcs_output_dir_btn.clicked.connect(self.choose_pcs_output_dir)
        self.add_pcs_btn = QPushButton("Add / Update PCS")
        self.add_pcs_btn.clicked.connect(self.add_or_update_pcs)
        self.remove_pcs_btn = QPushButton("Remove PCS")
        self.remove_pcs_btn.clicked.connect(self.remove_selected_pcs)
        self.set_current_pcs_btn = QPushButton("Set Current PCS")
        self.set_current_pcs_btn.clicked.connect(self.set_selected_pcs_as_current)
        self.load_pcs_config_btn = QPushButton("Import PCS Profile...")
        self.load_pcs_config_btn.clicked.connect(self.load_pcs_config_from_file)
        self.save_pcs_configs_btn = QPushButton("Save PCS List")
        self.save_pcs_configs_btn.clicked.connect(self.save_pcs_config)
        self.start_selected_pcs_poll_btn = QPushButton("Connect selected PCS")
        self.start_selected_pcs_poll_btn.clicked.connect(self.start_selected_pcs_polling)
        self.stop_selected_pcs_poll_btn = QPushButton("Disconnect selected PCS")
        self.stop_selected_pcs_poll_btn.clicked.connect(self.stop_selected_pcs_polling)
        self.start_all_pcs_poll_btn = QPushButton("Connect all PCS")
        self.start_all_pcs_poll_btn.clicked.connect(self.start_all_pcs_polling)
        self.stop_all_pcs_poll_btn = QPushButton("Disconnect all PCS")
        self.stop_all_pcs_poll_btn.clicked.connect(self.stop_all_pcs_polling)

        self.start_pcs_csv_btn = QPushButton("Start PCS CSV")
        self.start_pcs_csv_btn.setToolTip("Start CSV recording for selected PCS, or all PCS if no row is selected.")
        self.start_pcs_csv_btn.clicked.connect(self.start_pcs_csv_recording)

        self.stop_pcs_csv_btn = QPushButton("Stop PCS CSV")
        self.stop_pcs_csv_btn.setToolTip("Stop CSV recording for selected PCS, or all PCS if no row is selected.")
        self.stop_pcs_csv_btn.clicked.connect(self.stop_pcs_csv_recording)

        self.pcs_csv_status_label = QLabel("PCS CSV: Recording OFF")
        self.pcs_csv_status_label.setStyleSheet("color: #777; font-weight: 600;")

        for col, (label, widget) in enumerate([
            ("Name", self.pcs_name_edit),
            ("Host", self.pcs_host_edit),
            ("Port", self.pcs_port_spin),
            ("Unit", self.pcs_unit_spin),
            ("State", self.pcs_enabled_combo),
            ("Fake", self.pcs_fake_scenario_combo),
            ("Profile", self.pcs_profile_combo),
        ]):
            pcs_form.addWidget(QLabel(label), 0, col * 2)
            pcs_form.addWidget(widget, 0, col * 2 + 1)
        pcs_form.addWidget(QLabel("Output dir"), 1, 0)
        pcs_form.addWidget(self.pcs_output_dir_edit, 1, 1, 1, 5)
        pcs_form.addWidget(self.pcs_output_dir_btn, 1, 6, 1, 2)

        pcs_form.addWidget(self.add_pcs_btn, 2, 0, 1, 2)
        pcs_form.addWidget(self.remove_pcs_btn, 2, 2, 1, 2)
        pcs_form.addWidget(self.set_current_pcs_btn, 2, 4, 1, 2)
        pcs_form.addWidget(self.load_pcs_config_btn, 2, 6, 1, 2)
        pcs_form.addWidget(self.save_pcs_configs_btn, 2, 8, 1, 2)
        pcs_form.addWidget(self.start_selected_pcs_poll_btn, 3, 0, 1, 2)
        pcs_form.addWidget(self.stop_selected_pcs_poll_btn, 3, 2, 1, 2)
        pcs_form.addWidget(self.start_all_pcs_poll_btn, 3, 4, 1, 2)
        pcs_form.addWidget(self.stop_all_pcs_poll_btn, 3, 6, 1, 2)
        pcs_form.addWidget(self.start_pcs_csv_btn, 3, 8, 1, 2)
        pcs_form.addWidget(self.stop_pcs_csv_btn, 3, 10, 1, 2)
        pcs_form.addWidget(self.pcs_csv_status_label, 4, 0, 1, 12)
        pcs_layout.addLayout(pcs_form)

        self.pcs_device_table = QTableWidget(0, 19)
        self.pcs_device_table.setHorizontalHeaderLabels([
            "Name", "Profile", "Host", "Port", "Unit", "Enabled", "Connection", "Online",
            "Run Status", "Remote", "AC SW", "DC SW", "Set kW", "Charge kW", "Discharge kW",
            "DC V", "DC A", "Alarm/Fault", "Last Update"
        ])
        pcs_header = self.pcs_device_table.horizontalHeader()
        pcs_header.setSectionResizeMode(QHeaderView.Interactive)
        pcs_header.setStretchLastSection(False)
        self.pcs_device_table.setWordWrap(False)
        self.pcs_device_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.pcs_device_table.setHorizontalScrollMode(QTableWidget.ScrollPerPixel)
        self.pcs_device_table.setAlternatingRowColors(True)
        self.pcs_device_table.verticalHeader().setDefaultSectionSize(30)
        # Wider default columns so PCS status text is readable.
        pcs_widths = [150, 170, 150, 70, 70, 90, 130, 90, 150, 110, 100, 100, 105, 120, 135, 100, 100, 150, 190]
        for i, width in enumerate(pcs_widths):
            self.pcs_device_table.setColumnWidth(i, width)
        # Show roughly 5-10 rows by default; the Devices page is scrollable.
        self.pcs_device_table.setMinimumHeight(260)
        self.pcs_device_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        self.pcs_device_table.cellClicked.connect(self.on_pcs_table_clicked)
        pcs_layout.addWidget(self.pcs_device_table)
        pcs_group.setMinimumHeight(360)
        pcs_content_layout.addWidget(pcs_group)


        pcs_content_layout.addStretch(1)
        tabs.addTab(pcs_tab, "PCS Devices")

