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

def _build_details_tab(self, tabs: QTabWidget) -> None:
        detail_tab = QScrollArea()
        detail_tab.setWidgetResizable(True)

        detail_content = QWidget()
        detail_layout = QVBoxLayout(detail_content)
        detail_layout.setContentsMargins(14, 14, 14, 14)
        detail_layout.setSpacing(12)
        detail_tab.setWidget(detail_content)

        detail_top_row = QHBoxLayout()
        self.detail_device_label = QLabel("Current device: -")
        detail_top_row.addWidget(self.detail_device_label)
        detail_top_row.addSpacing(20)
        detail_top_row.addWidget(QLabel("Select device:"))

        self.detail_device_combo = QComboBox()
        self.detail_device_combo.currentTextChanged.connect(self.on_detail_device_changed)
        detail_top_row.addWidget(self.detail_device_combo)
        detail_top_row.addStretch()
        detail_layout.addLayout(detail_top_row)

        detail_grid_wrap = QGroupBox("BMS Snapshot")
        detail_grid = QGridLayout(detail_grid_wrap)
        detail_grid.setContentsMargins(14, 12, 14, 12)
        detail_grid.setHorizontalSpacing(24)
        detail_grid.setVerticalSpacing(10)

        pairs_per_row = 3
        for i, (key, label_text) in enumerate(self.DETAIL_FIELDS):
            name_label = QLabel(label_text + ":")
            value_label = QLabel("-")
            value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.detail_value_labels[key] = value_label

            row = i // pairs_per_row
            col = (i % pairs_per_row) * 2
            detail_grid.addWidget(name_label, row, col)
            detail_grid.addWidget(value_label, row, col + 1)

        detail_layout.addWidget(detail_grid_wrap)
        detail_layout.addStretch()

        tabs.addTab(detail_tab, "Details")

