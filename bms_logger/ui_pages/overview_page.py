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

def _build_overview_tab(self, tabs: QTabWidget) -> None:
        overview_tab = QWidget()
        overview_layout = QVBoxLayout(overview_tab)
        overview_layout.setContentsMargins(14, 14, 14, 14)
        overview_layout.setSpacing(12)

        summary_group = QGroupBox("System Overview")
        summary_layout = QGridLayout(summary_group)
        summary_layout.setContentsMargins(14, 12, 14, 12)
        summary_layout.setHorizontalSpacing(24)
        summary_layout.setVerticalSpacing(10)

        self.overview_total_devices_label = QLabel("0")
        self.overview_running_devices_label = QLabel("0")
        self.overview_online_devices_label = QLabel("0")
        self.overview_sampling_label = QLabel("Stopped")
        self.overview_heartbeat_label = QLabel("Stopped")
        self.overview_hv_label = QLabel("Idle")
        self.overview_cutoff_label = QLabel("Normal")
        self.overview_last_error_label = QLabel("-")

        items = [
            ("Total Devices:", self.overview_total_devices_label),
            ("Running Devices:", self.overview_running_devices_label),
            ("Online Devices:", self.overview_online_devices_label),
            ("Sampling:", self.overview_sampling_label),
            ("Heartbeat:", self.overview_heartbeat_label),
            ("HV Workflow:", self.overview_hv_label),
            ("Cutoff:", self.overview_cutoff_label),
            ("Last Error:", self.overview_last_error_label),
        ]

        for i, (title, label) in enumerate(items):
            row = i // 2
            col = (i % 2) * 2
            summary_layout.addWidget(QLabel(title), row, col)
            summary_layout.addWidget(label, row, col + 1)

        overview_layout.addWidget(summary_group)

        quick_group = QGroupBox("Quick Actions")
        quick_layout = QHBoxLayout(quick_group)

        self.overview_start_all_btn = QPushButton("Start All")
        self.overview_start_all_btn.clicked.connect(self.start_all)

        self.overview_stop_all_btn = QPushButton("Stop All")
        self.overview_stop_all_btn.clicked.connect(self.stop_all)

        self.overview_clear_log_btn = QPushButton("Clear Log View")
        self.overview_clear_log_btn.clicked.connect(self.handle_clear_log_view)

        self.overview_open_output_btn = QPushButton("Open Output Folder")
        self.overview_open_output_btn.clicked.connect(self.handle_open_output_folder)

        quick_layout.addWidget(self.overview_start_all_btn)
        quick_layout.addWidget(self.overview_stop_all_btn)
        quick_layout.addWidget(self.overview_clear_log_btn)
        quick_layout.addWidget(self.overview_open_output_btn)
        quick_layout.addStretch()

        overview_layout.addWidget(quick_group)

        device_group = QGroupBox("Device Status")
        device_layout = QVBoxLayout(device_group)

        self.overview_device_table = QTableWidget(0, 7)
        self.overview_device_table.setHorizontalHeaderLabels(
            [
                "Device",
                "Online",
                "Run State",
                "SOC(%)",
                "Voltage(V)",
                "Current(A)",
                "Power(kW)",
            ]
        )
        self.overview_device_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.overview_device_table.verticalHeader().setDefaultSectionSize(28)

        device_layout.addWidget(self.overview_device_table)
        overview_layout.addWidget(device_group)
        cluster_group = QGroupBox("Cluster Status")
        cluster_layout = QVBoxLayout(cluster_group)

        self.overview_cluster_table = QTableWidget(0, 7)
        self.overview_cluster_table.setHorizontalHeaderLabels(
            [
                "Cluster",
                "BMS Count",
                "PCS",
                "Max Cell V(mV)",
                "Min Cell V(mV)",
                "Derating",
                "Cutoff",
            ]
        )
        self.overview_cluster_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.overview_cluster_table.verticalHeader().setDefaultSectionSize(28)

        cluster_layout.addWidget(self.overview_cluster_table)
        overview_layout.addWidget(cluster_group)

        overview_layout.addStretch()

        tabs.addTab(overview_tab, "Overview")

