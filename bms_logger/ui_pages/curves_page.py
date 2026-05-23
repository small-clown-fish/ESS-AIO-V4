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
    QListWidget,
)

def _build_curves_tab(self, tabs: QTabWidget) -> None:
        curve_tab = QScrollArea()
        curve_tab.setWidgetResizable(True)

        curve_content = QWidget()
        curve_layout = QVBoxLayout(curve_content)
        curve_layout.setContentsMargins(14, 14, 14, 14)
        curve_layout.setSpacing(12)
        curve_tab.setWidget(curve_content)

        top_curve_row = QHBoxLayout()
        self.curve_device_label = QLabel("Current device: -")
        top_curve_row.addWidget(self.curve_device_label)
        top_curve_row.addSpacing(20)
        top_curve_row.addWidget(QLabel("Select device:"))

        self.curve_device_combo = QComboBox()
        self.curve_device_combo.currentTextChanged.connect(self.on_curve_device_changed)
        top_curve_row.addWidget(self.curve_device_combo)

        self.load_history_csv_btn = QPushButton("Load History CSV")
        self.history_start_edit = QLineEdit()
        self.history_start_edit.setPlaceholderText("Start time: 2026-04-27 13:20:00")

        self.history_end_edit = QLineEdit()
        self.history_end_edit.setPlaceholderText("End time: 2026-04-27 13:30:00")

        self.clear_history_btn = QPushButton("Clear History")
        self.clear_history_btn.clicked.connect(self.handle_clear_history)


        self.apply_history_filter_btn = QPushButton("Apply Time Filter")
        self.apply_history_filter_btn.clicked.connect(self.apply_history_time_filter)

        self.load_history_csv_btn.clicked.connect(self.handle_load_history_csv)
        top_curve_row.addWidget(self.load_history_csv_btn)
        top_curve_row.addWidget(self.history_start_edit)
        top_curve_row.addWidget(self.history_end_edit)
        top_curve_row.addWidget(self.apply_history_filter_btn)
        top_curve_row.addWidget(self.clear_history_btn)
        top_curve_row.addStretch()

        curve_layout.addLayout(top_curve_row)
        self.history_info_label = QLabel("History: -")
        curve_layout.addWidget(self.history_info_label)

        dynamic_group = QGroupBox("Dynamic Point Curves")
        dynamic_layout = QVBoxLayout(dynamic_group)
        dynamic_top = QHBoxLayout()
        dynamic_top.addWidget(QLabel("Point:"))
        self.dynamic_point_combo = QComboBox()
        dynamic_top.addWidget(self.dynamic_point_combo, 1)
        self.add_dynamic_point_btn = QPushButton("Add Point")
        self.add_dynamic_point_btn.clicked.connect(self.add_dynamic_point_from_combo)
        self.clear_dynamic_points_btn = QPushButton("Clear Dynamic")
        self.clear_dynamic_points_btn.clicked.connect(self.clear_dynamic_points)
        dynamic_top.addWidget(self.add_dynamic_point_btn)
        dynamic_top.addWidget(self.clear_dynamic_points_btn)
        dynamic_layout.addLayout(dynamic_top)

        self.dynamic_selected_points_list = QListWidget()
        self.dynamic_selected_points_list.setMaximumHeight(78)
        dynamic_layout.addWidget(self.dynamic_selected_points_list)

        self.dynamic_point_series = []
        self.dynamic_point_chart = QChart()
        self.dynamic_point_chart.setTitle("Dynamic Driver Points")
        self.dynamic_axis_x = QValueAxis()
        self.dynamic_axis_x.setTitleText("Sample Index")
        self.dynamic_axis_x.setRange(0, 300)
        self.dynamic_axis_y = QValueAxis()
        self.dynamic_axis_y.setTitleText("Value")
        self.dynamic_axis_y.setRange(0, 1)
        self.dynamic_point_chart.addAxis(self.dynamic_axis_x, Qt.AlignBottom)
        self.dynamic_point_chart.addAxis(self.dynamic_axis_y, Qt.AlignLeft)
        for i in range(4):
            series = QLineSeries()
            series.setName(f"Point {i + 1}")
            self.dynamic_point_chart.addSeries(series)
            series.attachAxis(self.dynamic_axis_x)
            series.attachAxis(self.dynamic_axis_y)
            self.dynamic_point_series.append(series)
        self.dynamic_point_chart_view = QChartView(self.dynamic_point_chart)
        self.dynamic_point_chart_view.setMinimumHeight(220)
        self.dynamic_point_chart_view.setMaximumHeight(320)
        dynamic_layout.addWidget(self.dynamic_point_chart_view)
        curve_layout.addWidget(dynamic_group)

        # Curves page is now reserved for live Modbus/driver monitoring and history replay.
        # Imported CAN packet plots are shown in Packet Analyzer -> CAN.

        self.online_series = QLineSeries()
        self.online_series.setName("BMS Online")

        self.soc_series = QLineSeries()
        self.soc_series.setName("SOC")

        self.voltage_series = QLineSeries()
        self.voltage_series.setName("System Voltage")

        self.current_series = QLineSeries()
        self.current_series.setName("System Current")

        self.online_chart = self._create_chart("BMS Online (1=Online, 0=Offline/Stale)", self.online_series)
        self.soc_chart = self._create_chart("SOC (%)", self.soc_series)
        self.voltage_chart = self._create_chart("System Voltage (V)", self.voltage_series)
        self.current_chart = self._create_chart("System Current (A)", self.current_series)

        grid_wrap = QWidget()
        chart_grid = QGridLayout(grid_wrap)
        chart_grid.setContentsMargins(0, 0, 0, 0)
        chart_grid.setSpacing(12)

        soc_view = QChartView(self.soc_chart)
        voltage_view = QChartView(self.voltage_chart)
        current_view = QChartView(self.current_chart)
        online_view = QChartView(self.online_chart)

        for view in [soc_view, voltage_view, current_view, online_view]:
            view.setMinimumHeight(190)
            view.setMaximumHeight(260)

        chart_grid.addWidget(soc_view, 0, 0)
        chart_grid.addWidget(voltage_view, 0, 1)
        chart_grid.addWidget(current_view, 1, 0)
        chart_grid.addWidget(online_view, 1, 1)

        curve_layout.addWidget(grid_wrap)

        tabs.addTab(curve_tab, "Curves")

def _build_driver_points_tab(self, tabs: QTabWidget) -> None:
        points_tab = QWidget()
        points_layout = QVBoxLayout(points_tab)
        points_layout.setContentsMargins(14, 14, 14, 14)
        points_layout.setSpacing(12)

        top_row = QHBoxLayout()
        self.driver_points_device_label = QLabel("Current device: -")
        top_row.addWidget(self.driver_points_device_label)
        top_row.addSpacing(20)
        top_row.addWidget(QLabel("Select device:"))

        self.driver_points_device_combo = QComboBox()
        self.driver_points_device_combo.currentTextChanged.connect(self.on_driver_points_device_changed)
        top_row.addWidget(self.driver_points_device_combo)

        self.driver_points_filter_edit = QLineEdit()
        self.driver_points_filter_edit.setPlaceholderText("Filter points...")
        self.driver_points_filter_edit.textChanged.connect(self.refresh_current_driver_points)
        top_row.addWidget(self.driver_points_filter_edit)

        self.driver_points_category_combo = QComboBox()
        self.driver_points_category_combo.addItems(["All", "Favorites", "Alarm/Fault", "Numeric"])
        self.driver_points_category_combo.currentTextChanged.connect(self.refresh_current_driver_points)
        top_row.addWidget(self.driver_points_category_combo)

        self.favorite_point_btn = QPushButton("Toggle Favorite")
        self.favorite_point_btn.clicked.connect(self.toggle_selected_driver_point_favorite)
        self.add_point_to_curve_btn = QPushButton("Add to Curve")
        self.add_point_to_curve_btn.clicked.connect(self.add_selected_driver_point_to_curve)
        top_row.addWidget(self.favorite_point_btn)
        top_row.addWidget(self.add_point_to_curve_btn)
        top_row.addStretch()
        points_layout.addLayout(top_row)

        self.driver_points_table = QTableWidget(0, 7)
        self.driver_points_table.setHorizontalHeaderLabels(["★", "Point", "Value", "Unit", "Address", "Label", "Category"])
        self.driver_points_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.driver_points_table.verticalHeader().setDefaultSectionSize(28)
        self.driver_points_table.cellDoubleClicked.connect(lambda _r, _c: self.add_selected_driver_point_to_curve())
        points_layout.addWidget(self.driver_points_table)

        tabs.addTab(points_tab, "Driver Points")

