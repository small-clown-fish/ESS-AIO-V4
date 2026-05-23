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

def _build_replay_tab(self, tabs: QTabWidget) -> None:
        replay_tab = QWidget()
        layout = QVBoxLayout(replay_tab)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        top_group = QGroupBox("Data Replay")
        grid = QGridLayout(top_group)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        self.replay_device_name_edit = QLineEdit("Replay-BMS")
        self.replay_interval_spin = QSpinBox()
        self.replay_interval_spin.setRange(100, 10000)
        self.replay_interval_spin.setValue(1000)
        self.replay_interval_spin.setSuffix(" ms")
        self.load_replay_csv_btn = QPushButton("Load Main CSV")
        self.load_replay_csv_btn.clicked.connect(self.handle_replay_load_csv)
        self.replay_next_btn = QPushButton("Replay Next Row")
        self.replay_next_btn.clicked.connect(self.handle_replay_next_row)
        self.replay_start_btn = QPushButton("Start Replay")
        self.replay_start_btn.clicked.connect(self.handle_replay_start)
        self.replay_stop_btn = QPushButton("Stop Replay")
        self.replay_stop_btn.clicked.connect(self.handle_replay_stop)

        grid.addWidget(QLabel("Replay Device"), 0, 0)
        grid.addWidget(self.replay_device_name_edit, 0, 1)
        grid.addWidget(QLabel("Interval"), 0, 2)
        grid.addWidget(self.replay_interval_spin, 0, 3)
        grid.addWidget(self.load_replay_csv_btn, 0, 4)
        grid.addWidget(self.replay_next_btn, 1, 0)
        grid.addWidget(self.replay_start_btn, 1, 1)
        grid.addWidget(self.replay_stop_btn, 1, 2)
        layout.addWidget(top_group)

        self.replay_info_label = QLabel("Replay: no CSV loaded")
        layout.addWidget(self.replay_info_label)

        self.replay_table = QTableWidget(0, 6)
        self.replay_table.setHorizontalHeaderLabels(["Index", "Timestamp", "SOC", "Voltage", "Current", "Power"])
        self.replay_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.replay_table.verticalHeader().setDefaultSectionSize(30)
        layout.addWidget(self.replay_table, 1)

        tabs.addTab(replay_tab, "Replay")

