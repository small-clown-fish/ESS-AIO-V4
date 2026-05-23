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

def _build_scheduler_tab(self, tabs: QTabWidget) -> None:
        scheduler_tab = QWidget()
        layout = QVBoxLayout(scheduler_tab)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        info_group = QGroupBox("Scheduler / Task Manager")
        info_layout = QGridLayout(info_group)
        info_layout.setContentsMargins(14, 12, 14, 12)
        info_layout.setHorizontalSpacing(18)
        info_layout.setVerticalSpacing(8)

        self.scheduler_stagger_label = QLabel("Staggered start avoids all BMS devices connecting at once.")
        self.scheduler_ui_label = QLabel("UI refresh is throttled while data recording keeps full sample rate.")
        info_layout.addWidget(QLabel("Startup:"), 0, 0)
        info_layout.addWidget(self.scheduler_stagger_label, 0, 1)
        info_layout.addWidget(QLabel("UI:"), 1, 0)
        info_layout.addWidget(self.scheduler_ui_label, 1, 1)
        layout.addWidget(info_group)

        task_group = QGroupBox("BMS Sampling Tasks")
        task_layout = QVBoxLayout(task_group)

        self.task_status_table = QTableWidget(0, 7)
        self.task_status_table.setHorizontalHeaderLabels([
            "Device",
            "Status",
            "Reads",
            "Errors",
            "Latency(ms)",
            "Last Update",
            "Message",
        ])
        self.task_status_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.task_status_table.verticalHeader().setDefaultSectionSize(28)
        task_layout.addWidget(self.task_status_table)

        layout.addWidget(task_group)
        layout.addStretch()

        tabs.addTab(scheduler_tab, "Scheduler")

