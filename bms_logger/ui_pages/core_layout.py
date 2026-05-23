from __future__ import annotations

from pathlib import Path
import csv
from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QFont
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
    QStackedWidget,
)


class _NavTabsAdapter:
    """Small adapter so existing page builders can keep using tabs.addTab(widget, title)."""

    def __init__(self, nav_list: QListWidget, page_stack: QStackedWidget) -> None:
        self.nav_list = nav_list
        self.page_stack = page_stack

    def addTab(self, widget: QWidget, title: str) -> None:
        self.page_stack.addWidget(widget)
        self.nav_list.addItem(title)

def _build_menu(self) -> None:
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")

        load_action = QAction("Load devices", self)
        load_action.triggered.connect(self.load_devices)
        file_menu.addAction(load_action)

        save_action = QAction("Save devices", self)
        save_action.triggered.connect(self.save_devices)
        file_menu.addAction(save_action)

        file_menu.addSeparator()

        reload_pcs_action = QAction("Reload PCS config", self)
        reload_pcs_action.triggered.connect(self.reload_pcs_config)
        file_menu.addAction(reload_pcs_action)

        reload_alarm_action = QAction("Reload Alarm Map", self)
        reload_alarm_action.triggered.connect(self.reload_alarm_map)
        file_menu.addAction(reload_alarm_action)

        file_menu.addSeparator()

        save_site_action = QAction("Save Site Config", self)
        save_site_action.triggered.connect(self.save_site_config)
        file_menu.addAction(save_site_action)

        reload_site_action = QAction("Reload Site Config", self)
        reload_site_action.triggered.connect(self.load_site_config)
        file_menu.addAction(reload_site_action)

        file_menu.addSeparator()

        new_profile_action = QAction("New Profile", self)
        new_profile_action.triggered.connect(self.new_profile)
        file_menu.addAction(new_profile_action)

        load_profile_action = QAction("Load Profile", self)
        load_profile_action.triggered.connect(self.load_profile)
        file_menu.addAction(load_profile_action)

        save_profile_action = QAction("Save Profile", self)
        save_profile_action.triggered.connect(self.save_profile)
        file_menu.addAction(save_profile_action)

        export_profile_action = QAction("Export Profile Package", self)
        export_profile_action.triggered.connect(self.export_profile_package)
        file_menu.addAction(export_profile_action)

        import_profile_action = QAction("Import Profile Package", self)
        import_profile_action.triggered.connect(self.import_profile_package)
        file_menu.addAction(import_profile_action)

        file_menu.addSeparator()

        generate_debug_report_action = QAction("Generate Debug Report", self)
        generate_debug_report_action.triggered.connect(self.generate_debug_report)
        file_menu.addAction(generate_debug_report_action)

        export_debug_package_action = QAction("Export Debug Package", self)
        export_debug_package_action.triggered.connect(self.export_debug_package)
        file_menu.addAction(export_debug_package_action)


        tools_menu = menubar.addMenu("Tools")
        self_check_action = QAction("Run Startup Self Check", self)
        self_check_action.triggered.connect(self.run_startup_self_check)
        tools_menu.addAction(self_check_action)

        open_crash_logs_action = QAction("Open Crash Logs", self)
        open_crash_logs_action.triggered.connect(self.open_crash_log_folder)
        tools_menu.addAction(open_crash_logs_action)

        help_menu = menubar.addMenu("Help")
        about_action = QAction("About ESS-AIO", self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)

def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        self._build_global_status(root)

        body = QHBoxLayout()
        body.setSpacing(12)
        root.addLayout(body, 1)

        self.nav_list = QListWidget()
        self.nav_list.setMaximumWidth(190)
        self.nav_list.setMinimumWidth(160)
        body.addWidget(self.nav_list)

        self.page_stack = QStackedWidget()
        body.addWidget(self.page_stack, 1)

        self.nav_list.currentRowChanged.connect(self.page_stack.setCurrentIndex)
        tabs = _NavTabsAdapter(self.nav_list, self.page_stack)

        # Navigation order is grouped by workflow:
        # Overview -> Project/Devices -> configuration/templates -> data views -> control/scheduler -> analysis -> reports/system.
        self._build_overview_tab(tabs)

        self._build_site_tab(tabs)          # Project
        self._build_devices_tab(tabs)
        self._build_pcs_devices_tab(tabs)
        self._build_control_tab(tabs)
        self._build_register_debug_tab(tabs)
        self._build_details_tab(tabs)
        self._build_curves_tab(tabs)

        self._build_templates_tab(tabs)
        self._build_strategy_tab(tabs)

        self._build_driver_points_tab(tabs)

        self._build_alarms_tab(tabs)
        self._build_alarm_analysis_tab(tabs)
        self._build_replay_tab(tabs)

        self._build_scheduler_tab(tabs)
        self._build_diagnostics_tab(tabs)

        self._build_packet_analyzer_tab(tabs)
        self._build_timeline_tab(tabs)
        self._build_report_tab(tabs)

        self._build_settings_tab(tabs)
        self._build_logs_tab(tabs)
        self._build_release_tab(tabs)
        self.nav_list.setCurrentRow(0)

def _build_global_status(self, root: QVBoxLayout) -> None:
        status_bar_wrap = QGroupBox("Status")
        status_bar_layout = QGridLayout(status_bar_wrap)
        status_bar_layout.setContentsMargins(14, 10, 14, 10)
        status_bar_layout.setHorizontalSpacing(24)
        status_bar_layout.setVerticalSpacing(8)

        self.status_selected_device_label = QLabel("-")
        self.status_sampling_label = QLabel("Stopped")
        self.status_heartbeat_label = QLabel("Stopped")
        self.status_hv_label = QLabel("Idle")
        self.status_pcs_label = QLabel("Loaded" if self.pcs_config.get("enabled", False) else "Disabled / Missing")
        self.status_last_error_label = QLabel("-")
        self.status_cutoff_label = QLabel("Normal")

        self.status_last_error_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        pairs = [
            ("Selected:", self.status_selected_device_label),
            ("Sampling:", self.status_sampling_label),
            ("Heartbeat:", self.status_heartbeat_label),
            ("HV:", self.status_hv_label),
            ("PCS:", self.status_pcs_label),
            ("Cutoff:", self.status_cutoff_label),
            ("Last Error:", self.status_last_error_label),
        ]

        for i, (title, label) in enumerate(pairs):
            row = i // 4
            col = (i % 4) * 2
            status_bar_layout.addWidget(QLabel(title), row, col)
            status_bar_layout.addWidget(label, row, col + 1)

        root.addWidget(status_bar_wrap)

def _apply_comfortable_style(self) -> None:
        self.setFont(QFont("Microsoft YaHei UI", 11))
        self.setStyleSheet("""
        QMainWindow, QWidget {
            background: #0f172a;
            color: #dbeafe;
            font-size: 11pt;
        }
        QListWidget {
            background: #111827;
            border: 1px solid #1e293b;
            border-radius: 10px;
            padding: 6px;
            outline: none;
        }
        QListWidget::item {
            min-height: 34px;
            padding: 8px 10px;
            border-radius: 8px;
            color: #cbd5e1;
        }
        QListWidget::item:selected {
            background: #0e7490;
            color: #ffffff;
        }
        QGroupBox {
            background: #111827;
            border: 1px solid #334155;
            border-radius: 12px;
            margin-top: 12px;
            padding: 10px;
            font-weight: 700;
            color: #93c5fd;
            font-size: 11pt;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 6px;
            color: #22d3ee;
        }
        QPushButton {
            background: #1e293b;
            color: #e0f2fe;
            border: 1px solid #0891b2;
            border-radius: 8px;
            min-height: 32px;
            padding: 5px 12px;
        }
        QPushButton:hover {
            background: #155e75;
            border-color: #22d3ee;
        }
        QPushButton:pressed {
            background: #0e7490;
        }
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
            background: #020617;
            color: #e5e7eb;
            border: 1px solid #334155;
            border-radius: 7px;
            min-height: 30px;
            padding: 3px 7px;
        }
        QTableWidget {
            background: #020617;
            alternate-background-color: #0b1220;
            gridline-color: #1e293b;
            border: 1px solid #334155;
            border-radius: 8px;
            color: #e5e7eb;
        }
        QHeaderView::section {
            background: #1e293b;
            color: #93c5fd;
            border: 1px solid #334155;
            padding: 6px;
            font-weight: 700;
        }
        QTextEdit {
            background: #020617;
            color: #dbeafe;
            border: 1px solid #334155;
            border-radius: 8px;
            min-height: 120px;
        }
        QScrollArea {
            border: none;
        }
        QLabel {
            color: #dbeafe;
        }
        QLabel#PageTitle {
            color: #bfdbfe;
            font-size: 15pt;
            font-weight: 700;
        }
        QLabel#PageHint {
            color: #93a4bb;
            font-size: 10pt;
        }
        """)

        for table_name in ["device_table", "alarm_table", "overview_device_table", "overview_cluster_table", "site_cluster_table", "pcs_device_table", "point_template_table"]:
            table = getattr(self, table_name, None)
            if table is not None:
                table.setAlternatingRowColors(True)
                table.verticalHeader().setDefaultSectionSize(32)

        for group in self.findChildren(QGroupBox):
            layout = group.layout()
            if layout is not None:
                layout.setContentsMargins(14, 14, 14, 14)
                layout.setSpacing(10)

def _create_chart(self, title: str, series: QLineSeries) -> QChart:
        chart = QChart()
        chart.setTitle(title)
        title_font = chart.titleFont()
        title_font.setPointSize(11)
        chart.setTitleFont(title_font)
        chart.addSeries(series)

        axis_x = QValueAxis()
        axis_x.setTitleText("Sample Index")
        axis_x.setRange(0, 300)

        axis_y = QValueAxis()
        axis_y.setTitleText(title)

        chart.addAxis(axis_x, Qt.AlignBottom)
        chart.addAxis(axis_y, Qt.AlignLeft)

        series.attachAxis(axis_x)
        series.attachAxis(axis_y)

        return chart

