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

def _build_diagnostics_tab(self, tabs: QTabWidget) -> None:
        diag_tab = QWidget()
        layout = QVBoxLayout(diag_tab)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        header = QGroupBox("Quick Diagnosis")
        header_layout = QHBoxLayout(header)
        self.run_diagnosis_btn = QPushButton("Run Diagnosis")
        self.run_diagnosis_btn.clicked.connect(self.run_quick_diagnosis)
        self.export_diagnosis_btn = QPushButton("Export Diagnosis Text")
        self.export_diagnosis_btn.clicked.connect(self.export_quick_diagnosis)
        header_layout.addWidget(QLabel("One-click health snapshot for BMS, PCS, Cluster, alarms, and protection states."))
        header_layout.addStretch()
        header_layout.addWidget(self.run_diagnosis_btn)
        header_layout.addWidget(self.export_diagnosis_btn)
        layout.addWidget(header)

        self.diagnosis_summary_table = QTableWidget(0, 4)
        self.diagnosis_summary_table.setHorizontalHeaderLabels(["Category", "Item", "Status", "Detail"])
        self.diagnosis_summary_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.diagnosis_summary_table.verticalHeader().setDefaultSectionSize(30)
        layout.addWidget(self.diagnosis_summary_table, 1)

        self.diagnosis_text = QTextEdit()
        self.diagnosis_text.setReadOnly(True)
        self.diagnosis_text.setMinimumHeight(170)
        layout.addWidget(self.diagnosis_text)

        tabs.addTab(diag_tab, "Diagnosis")

def _build_register_debug_tab(self, tabs: QTabWidget) -> None:
        reg_tab = QWidget()
        layout = QVBoxLayout(reg_tab)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        config_group = QGroupBox("Register Debug Tool")
        grid = QGridLayout(config_group)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        self.reg_target_type_combo = QComboBox()
        self.reg_target_type_combo.addItems(["BMS", "PCS"])
        self.reg_target_type_combo.currentTextChanged.connect(self.refresh_register_debug_targets)
        self.reg_target_combo = QComboBox()
        self.reg_table_combo = QComboBox()
        self.reg_table_combo.addItems(["holding", "input"])
        self.reg_address_edit = QLineEdit("0x0302")
        self.reg_count_spin = QSpinBox()
        self.reg_count_spin.setRange(1, 125)
        self.reg_count_spin.setValue(1)
        self.reg_value_spin = QSpinBox()
        self.reg_value_spin.setRange(0, 65535)
        self.reg_value_spin.setValue(0)

        self.reg_read_btn = QPushButton("Read Registers")
        self.reg_read_btn.clicked.connect(self.handle_register_debug_read)
        self.reg_write_btn = QPushButton("Write Single")
        self.reg_write_btn.clicked.connect(self.handle_register_debug_write)
        self.reg_refresh_targets_btn = QPushButton("Refresh Targets")
        self.reg_refresh_targets_btn.clicked.connect(self.refresh_register_debug_targets)

        fields = [
            ("Target Type", self.reg_target_type_combo),
            ("Target", self.reg_target_combo),
            ("Table", self.reg_table_combo),
            ("Address", self.reg_address_edit),
            ("Count", self.reg_count_spin),
            ("Write Value", self.reg_value_spin),
        ]
        for i, (label, widget) in enumerate(fields):
            grid.addWidget(QLabel(label), i // 3, (i % 3) * 2)
            grid.addWidget(widget, i // 3, (i % 3) * 2 + 1)
        grid.addWidget(self.reg_read_btn, 2, 0, 1, 2)
        grid.addWidget(self.reg_write_btn, 2, 2, 1, 2)
        grid.addWidget(self.reg_refresh_targets_btn, 2, 4, 1, 2)
        layout.addWidget(config_group)

        self.register_debug_table = QTableWidget(0, 4)
        self.register_debug_table.setHorizontalHeaderLabels(["Address", "Dec", "Hex", "ASCII"])
        self.register_debug_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.register_debug_table.verticalHeader().setDefaultSectionSize(30)
        layout.addWidget(self.register_debug_table, 1)

        self.register_debug_log = QTextEdit()
        self.register_debug_log.setReadOnly(True)
        self.register_debug_log.setMinimumHeight(140)
        layout.addWidget(self.register_debug_log)

        tabs.addTab(reg_tab, "Register Debug")

