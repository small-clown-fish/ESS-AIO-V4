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

def _build_strategy_tab(self, tabs: QTabWidget) -> None:
        # Keep the Strategy page inside its own scroll area.
        # The cluster strategy controls + JSON editor can exceed the window height,
        # so the tab itself must only contain the QScrollArea and all real content
        # must be added to the scroll area's inner widget.
        strategy_tab = QWidget()
        tab_layout = QVBoxLayout(strategy_tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        content_widget = QWidget()
        content_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        scroll.setWidget(content_widget)
        tab_layout.addWidget(scroll)

        top_group = QGroupBox("Strategy Engine")
        top_layout = QVBoxLayout(top_group)
        self.strategy_status_label = QLabel("Strategy: -")
        self.strategy_status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        top_layout.addWidget(self.strategy_status_label)

        btn_row = QHBoxLayout()
        self.load_strategy_btn = QPushButton("Reload Strategy")
        self.load_strategy_btn.clicked.connect(self.reload_strategy_config)
        self.save_strategy_btn = QPushButton("Save Strategy")
        self.save_strategy_btn.clicked.connect(self.save_strategy_from_editor)
        self.import_strategy_btn = QPushButton("Import Strategy JSON")
        self.import_strategy_btn.clicked.connect(self.import_strategy_json)
        self.export_strategy_btn = QPushButton("Export Strategy JSON")
        self.export_strategy_btn.clicked.connect(self.export_strategy_json)
        self.reset_strategy_btn = QPushButton("Reset Default")
        self.reset_strategy_btn.clicked.connect(self.reset_default_strategy)

        for btn in [
            self.load_strategy_btn,
            self.save_strategy_btn,
            self.import_strategy_btn,
            self.export_strategy_btn,
            self.reset_strategy_btn,
        ]:
            btn_row.addWidget(btn)
        btn_row.addStretch()
        top_layout.addLayout(btn_row)
        layout.addWidget(top_group)


        cluster_group = QGroupBox("Cluster Charge / Discharge Strategy")
        cluster_layout = QGridLayout(cluster_group)
        self.cluster_strategy_combo = QComboBox()
        self.cluster_strategy_combo.currentTextChanged.connect(self.apply_selected_cluster_strategy_to_ui)
        self.cluster_strategy_mode_combo = QComboBox()
        self.cluster_strategy_mode_combo.addItems(["discharge", "charge", "signed"])
        self.cluster_strategy_positive_combo = QComboBox()
        self.cluster_strategy_positive_combo.addItems(["+ = discharge", "+ = charge"])

        self.cluster_strategy_target_spin = QDoubleSpinBox()
        self.cluster_strategy_target_spin.setRange(-100000.0, 100000.0)
        self.cluster_strategy_target_spin.setDecimals(1)
        self.cluster_strategy_target_spin.setSuffix(" kW")
        self.cluster_strategy_target_spin.setValue(0.0)

        self.cluster_strategy_ramp_step_spin = QDoubleSpinBox()
        self.cluster_strategy_ramp_step_spin.setRange(0.1, 100000.0)
        self.cluster_strategy_ramp_step_spin.setDecimals(1)
        self.cluster_strategy_ramp_step_spin.setSuffix(" kW")
        self.cluster_strategy_ramp_step_spin.setValue(50.0)

        self.cluster_strategy_ramp_interval_spin = QDoubleSpinBox()
        self.cluster_strategy_ramp_interval_spin.setRange(0.2, 3600.0)
        self.cluster_strategy_ramp_interval_spin.setDecimals(1)
        self.cluster_strategy_ramp_interval_spin.setSuffix(" s")
        self.cluster_strategy_ramp_interval_spin.setValue(5.0)

        self.cluster_strategy_timeout_spin = QDoubleSpinBox()
        self.cluster_strategy_timeout_spin.setRange(0.5, 120.0)
        self.cluster_strategy_timeout_spin.setDecimals(1)
        self.cluster_strategy_timeout_spin.setSuffix(" s")
        self.cluster_strategy_timeout_spin.setValue(5.0)

        self.cluster_strategy_charge_cutoff_spin = QDoubleSpinBox()
        self.cluster_strategy_charge_cutoff_spin.setRange(1000.0, 5000.0)
        self.cluster_strategy_charge_cutoff_spin.setDecimals(0)
        self.cluster_strategy_charge_cutoff_spin.setSuffix(" mV")
        self.cluster_strategy_charge_cutoff_spin.setValue(3550.0)

        self.cluster_strategy_discharge_cutoff_spin = QDoubleSpinBox()
        self.cluster_strategy_discharge_cutoff_spin.setRange(1000.0, 5000.0)
        self.cluster_strategy_discharge_cutoff_spin.setDecimals(0)
        self.cluster_strategy_discharge_cutoff_spin.setSuffix(" mV")
        self.cluster_strategy_discharge_cutoff_spin.setValue(2800.0)

        self.cluster_strategy_allocation_combo = QComboBox()
        self.cluster_strategy_allocation_combo.addItems(["equal_split", "capacity_weighted"])
        self.cluster_strategy_timeout_action_combo = QComboBox()
        self.cluster_strategy_timeout_action_combo.addItems(["immediate_zero", "ramp_zero"])

        self.cluster_strategy_start_btn = QPushButton("Start Cluster Strategy")
        self.cluster_strategy_start_btn.clicked.connect(self.start_cluster_strategy)
        self.cluster_strategy_stop_btn = QPushButton("Stop Cluster Strategy")
        self.cluster_strategy_stop_btn.clicked.connect(self.stop_cluster_strategy)
        self.cluster_strategy_refresh_btn = QPushButton("Refresh Clusters")
        self.cluster_strategy_refresh_btn.clicked.connect(self.refresh_cluster_strategy_controls)
        self.cluster_strategy_status_text = QTextEdit()
        self.cluster_strategy_status_text.setReadOnly(True)
        self.cluster_strategy_status_text.setMinimumHeight(110)

        cluster_layout.addWidget(QLabel("Cluster"), 0, 0)
        cluster_layout.addWidget(self.cluster_strategy_combo, 0, 1)
        cluster_layout.addWidget(QLabel("Mode"), 0, 2)
        cluster_layout.addWidget(self.cluster_strategy_mode_combo, 0, 3)
        cluster_layout.addWidget(QLabel("PCS sign"), 0, 4)
        cluster_layout.addWidget(self.cluster_strategy_positive_combo, 0, 5)
        cluster_layout.addWidget(QLabel("Target"), 1, 0)
        cluster_layout.addWidget(self.cluster_strategy_target_spin, 1, 1)
        cluster_layout.addWidget(QLabel("Ramp step"), 1, 2)
        cluster_layout.addWidget(self.cluster_strategy_ramp_step_spin, 1, 3)
        cluster_layout.addWidget(QLabel("Ramp interval"), 1, 4)
        cluster_layout.addWidget(self.cluster_strategy_ramp_interval_spin, 1, 5)
        cluster_layout.addWidget(QLabel("BMS timeout"), 2, 0)
        cluster_layout.addWidget(self.cluster_strategy_timeout_spin, 2, 1)
        cluster_layout.addWidget(QLabel("Charge stop max cell"), 2, 2)
        cluster_layout.addWidget(self.cluster_strategy_charge_cutoff_spin, 2, 3)
        cluster_layout.addWidget(QLabel("Discharge stop min cell"), 2, 4)
        cluster_layout.addWidget(self.cluster_strategy_discharge_cutoff_spin, 2, 5)
        cluster_layout.addWidget(QLabel("Allocation"), 3, 0)
        cluster_layout.addWidget(self.cluster_strategy_allocation_combo, 3, 1)
        cluster_layout.addWidget(QLabel("Timeout action"), 3, 2)
        cluster_layout.addWidget(self.cluster_strategy_timeout_action_combo, 3, 3)
        btns = QHBoxLayout()
        btns.addWidget(self.cluster_strategy_refresh_btn)
        btns.addWidget(self.cluster_strategy_start_btn)
        btns.addWidget(self.cluster_strategy_stop_btn)
        btns.addStretch()
        cluster_layout.addLayout(btns, 4, 0, 1, 6)
        cluster_layout.addWidget(self.cluster_strategy_status_text, 5, 0, 1, 6)
        layout.addWidget(cluster_group)

        editor_group = QGroupBox("Active Strategy JSON")
        editor_layout = QVBoxLayout(editor_group)
        self.strategy_editor = QTextEdit()
        self.strategy_editor.setMinimumHeight(260)
        self.strategy_editor.setPlaceholderText("strategy.json")
        editor_layout.addWidget(self.strategy_editor)
        layout.addWidget(editor_group, 1)

        test_group = QGroupBox("Fake Scenario Test")
        test_layout = QGridLayout(test_group)
        self.strategy_test_combo = QComboBox()
        self.apply_strategy_test_btn = QPushButton("Apply Fake Scenario")
        self.apply_strategy_test_btn.clicked.connect(self.apply_selected_strategy_fake_test)
        self.run_strategy_fake_btn = QPushButton("Apply + Start All")
        self.run_strategy_fake_btn.clicked.connect(self.run_selected_strategy_fake_test)
        self.clear_strategy_fake_btn = QPushButton("Reset Fake Scenarios")
        self.clear_strategy_fake_btn.clicked.connect(self.reset_fake_scenarios)
        self.strategy_test_result_text = QTextEdit()
        self.strategy_test_result_text.setReadOnly(True)
        self.strategy_test_result_text.setMinimumHeight(120)

        test_layout.addWidget(QLabel("Test Scenario"), 0, 0)
        test_layout.addWidget(self.strategy_test_combo, 0, 1)
        test_layout.addWidget(self.apply_strategy_test_btn, 0, 2)
        test_layout.addWidget(self.run_strategy_fake_btn, 0, 3)
        test_layout.addWidget(self.clear_strategy_fake_btn, 0, 4)
        test_layout.addWidget(self.strategy_test_result_text, 1, 0, 1, 5)
        layout.addWidget(test_group)
        layout.addStretch(1)

        tabs.addTab(strategy_tab, "Strategy")
        if hasattr(self, "refresh_cluster_strategy_controls"):
            self.refresh_cluster_strategy_controls()

