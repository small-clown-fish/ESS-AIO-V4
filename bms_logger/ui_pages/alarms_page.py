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

def _build_alarms_tab(self, tabs: QTabWidget) -> None:
        alarm_tab = QScrollArea()
        alarm_tab.setWidgetResizable(True)

        alarm_content = QWidget()
        alarm_layout = QVBoxLayout(alarm_content)
        alarm_layout.setContentsMargins(14, 14, 14, 14)
        alarm_layout.setSpacing(12)
        alarm_tab.setWidget(alarm_content)

        alarm_top_row = QHBoxLayout()
        self.alarm_device_label = QLabel("Current device: -")
        alarm_top_row.addWidget(self.alarm_device_label)
        alarm_top_row.addSpacing(20)
        alarm_top_row.addWidget(QLabel("Select device:"))

        self.alarm_device_combo = QComboBox()
        self.alarm_device_combo.currentTextChanged.connect(self.on_alarm_device_changed)
        alarm_top_row.addWidget(self.alarm_device_combo)
        self.load_alarm_history_btn = QPushButton("Load Alarm CSV")
        self.load_alarm_history_btn.clicked.connect(self.handle_load_alarm_history_csv)
        alarm_top_row.addWidget(self.load_alarm_history_btn)
        alarm_top_row.addStretch()
        alarm_layout.addLayout(alarm_top_row)

        self.alarm_table = QTableWidget(32, 4)
        self.alarm_table.setHorizontalHeaderLabels(["Address", "Raw Value", "Hex", "Active Bits"])
        self.alarm_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.alarm_table.setMinimumHeight(420)
        self.alarm_table.setMaximumHeight(560)
        self.alarm_table.verticalHeader().setDefaultSectionSize(28)

        for i, addr in enumerate(range(0x0000, 0x0020)):
            self.alarm_table.setItem(i, 0, QTableWidgetItem(f"0x{addr:04x}"))
            self.alarm_table.setItem(i, 1, QTableWidgetItem("-"))
            self.alarm_table.setItem(i, 2, QTableWidgetItem("-"))
            self.alarm_table.setItem(i, 3, QTableWidgetItem("-"))

        alarm_layout.addWidget(self.alarm_table)
        self.alarm_history_text = QTextEdit()
        self.alarm_history_text.setReadOnly(True)
        self.alarm_history_text.setMinimumHeight(160)
        alarm_layout.addWidget(self.alarm_history_text)
        alarm_layout.addStretch()
        tabs.addTab(alarm_tab, "Alarms")

def _build_alarm_analysis_tab(self, tabs: QTabWidget) -> None:
        alarm_tab = QWidget()
        layout = QVBoxLayout(alarm_tab)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        top_group = QGroupBox("Alarm Analysis")
        top_row = QHBoxLayout(top_group)
        self.load_alarm_analysis_btn = QPushButton("Load Alarm CSV")
        self.load_alarm_analysis_btn.clicked.connect(self.handle_alarm_analysis_load_csv)
        self.refresh_alarm_analysis_btn = QPushButton("Analyze Current Alarms")
        self.refresh_alarm_analysis_btn.clicked.connect(self.handle_alarm_analysis_current)
        top_row.addWidget(QLabel("Analyze alarm CSV or current snapshots. Shows count, time range, and Top alarms."))
        top_row.addStretch()
        top_row.addWidget(self.load_alarm_analysis_btn)
        top_row.addWidget(self.refresh_alarm_analysis_btn)
        layout.addWidget(top_group)

        self.alarm_analysis_summary = QLabel("Summary: -")
        layout.addWidget(self.alarm_analysis_summary)

        self.alarm_analysis_table = QTableWidget(0, 3)
        self.alarm_analysis_table.setHorizontalHeaderLabels(["Alarm", "Count", "Example / Source"])
        self.alarm_analysis_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.alarm_analysis_table.verticalHeader().setDefaultSectionSize(30)
        layout.addWidget(self.alarm_analysis_table, 1)

        self.alarm_analysis_text = QTextEdit()
        self.alarm_analysis_text.setReadOnly(True)
        self.alarm_analysis_text.setMinimumHeight(150)
        layout.addWidget(self.alarm_analysis_text)

        tabs.addTab(alarm_tab, "Alarm Analysis")

