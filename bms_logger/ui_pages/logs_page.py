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

def _build_logs_tab(self, tabs: QTabWidget) -> None:
        log_tab = QWidget()
        log_layout = QVBoxLayout(log_tab)
        log_layout.setContentsMargins(14, 14, 14, 14)
        log_layout.setSpacing(10)

        log_btn_row = QHBoxLayout()

        self.load_operation_log_btn = QPushButton("Load Operation Log")
        self.load_operation_log_btn.clicked.connect(self.handle_load_operation_log)

        self.clear_log_view_btn = QPushButton("Clear Log View")
        self.clear_log_view_btn.clicked.connect(self.handle_clear_log_view)

        log_btn_row.addWidget(self.load_operation_log_btn)
        log_btn_row.addWidget(self.clear_log_view_btn)
        log_btn_row.addStretch()

        log_layout.addLayout(log_btn_row)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)

        tabs.addTab(log_tab, "Logs")

