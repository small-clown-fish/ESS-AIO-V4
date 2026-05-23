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

def _build_site_tab(self, tabs: QTabWidget) -> None:
        site_tab = QWidget()
        outer_layout = QVBoxLayout(site_tab)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        site_content = QWidget()
        site_layout = QVBoxLayout(site_content)
        site_layout.setContentsMargins(14, 14, 14, 14)
        site_layout.setSpacing(12)

        scroll_area.setWidget(site_content)
        outer_layout.addWidget(scroll_area)

        header_group = QGroupBox("Project Structure")
        header_layout = QGridLayout(header_group)
        header_layout.setHorizontalSpacing(12)
        header_layout.setVerticalSpacing(8)

        self.site_name_label = QLabel(f"Site: {self.site.name}")
        self.site_name_edit = QLineEdit(self.site.name)
        self.apply_site_name_btn = QPushButton("Apply Site")
        self.apply_site_name_btn.clicked.connect(self.apply_site_name)

        self.active_cluster_combo = QComboBox()
        self.active_cluster_combo.currentTextChanged.connect(self.on_active_cluster_changed)
        self.refresh_site_view_btn = QPushButton("Refresh")
        self.refresh_site_view_btn.clicked.connect(self.refresh_site_view)
        self.save_site_btn = QPushButton("Save Site")
        self.save_site_btn.clicked.connect(self.save_site_config)
        self.import_site_btn = QPushButton("Import Site")
        self.import_site_btn.clicked.connect(self.import_site_config_json)
        self.export_site_btn = QPushButton("Export Site")
        self.export_site_btn.clicked.connect(self.export_site_config_json)

        header_layout.addWidget(self.site_name_label, 0, 0)
        header_layout.addWidget(QLabel("Site Name"), 0, 1)
        header_layout.addWidget(self.site_name_edit, 0, 2)
        header_layout.addWidget(self.apply_site_name_btn, 0, 3)
        header_layout.addWidget(QLabel("Active Cluster"), 0, 4)
        header_layout.addWidget(self.active_cluster_combo, 0, 5)
        header_layout.addWidget(self.refresh_site_view_btn, 0, 6)
        header_layout.addWidget(self.save_site_btn, 1, 3)
        header_layout.addWidget(self.import_site_btn, 1, 4)
        header_layout.addWidget(self.export_site_btn, 1, 5)
        site_layout.addWidget(header_group)

        cluster_group = QGroupBox("Cluster Binding")
        cluster_layout = QGridLayout(cluster_group)
        cluster_layout.setHorizontalSpacing(12)
        cluster_layout.setVerticalSpacing(8)

        self.cluster_name_edit = QLineEdit("Cluster-1")
        self.apply_cluster_name_btn = QPushButton("Rename Cluster")
        self.apply_cluster_name_btn.clicked.connect(self.apply_cluster_name)

        self.new_cluster_name_edit = QLineEdit()
        self.new_cluster_name_edit.setPlaceholderText("New cluster name")
        self.add_cluster_btn = QPushButton("Add Cluster")
        self.add_cluster_btn.clicked.connect(self.add_cluster)
        self.delete_cluster_btn = QPushButton("Delete Selected Cluster")
        self.delete_cluster_btn.clicked.connect(self.delete_selected_cluster)

        self.cluster_binding_target_combo = QComboBox()
        self.cluster_pcs_combo = QComboBox()
        self.apply_cluster_pcs_btn = QPushButton("Add PCS to Cluster")
        self.apply_cluster_pcs_btn.clicked.connect(self.apply_cluster_pcs_binding)
        self.remove_cluster_pcs_btn = QPushButton("Remove PCS from Cluster")
        self.remove_cluster_pcs_btn.clicked.connect(self.remove_cluster_pcs_binding)

        self.move_bms_name_edit = QLineEdit()
        self.move_bms_name_edit.setPlaceholderText("BMS name")
        self.move_bms_target_cluster_combo = QComboBox()
        self.move_bms_btn = QPushButton("Move BMS")
        self.move_bms_btn.clicked.connect(self.move_bms_to_cluster)

        cluster_layout.addWidget(QLabel("Cluster Name"), 0, 0)
        cluster_layout.addWidget(self.cluster_name_edit, 0, 1)
        cluster_layout.addWidget(self.apply_cluster_name_btn, 0, 2)
        cluster_layout.addWidget(QLabel("New Cluster"), 0, 3)
        cluster_layout.addWidget(self.new_cluster_name_edit, 0, 4)
        cluster_layout.addWidget(self.add_cluster_btn, 0, 5)
        cluster_layout.addWidget(self.delete_cluster_btn, 0, 6)

        cluster_layout.addWidget(QLabel("PCS Binding Cluster"), 1, 0)
        cluster_layout.addWidget(self.cluster_binding_target_combo, 1, 1)
        cluster_layout.addWidget(QLabel("PCS"), 1, 2)
        cluster_layout.addWidget(self.cluster_pcs_combo, 1, 3)
        cluster_layout.addWidget(self.apply_cluster_pcs_btn, 1, 4)
        cluster_layout.addWidget(self.remove_cluster_pcs_btn, 1, 5)

        cluster_layout.addWidget(QLabel("Move BMS"), 2, 0)
        cluster_layout.addWidget(self.move_bms_name_edit, 2, 1)
        cluster_layout.addWidget(QLabel("To"), 2, 2)
        cluster_layout.addWidget(self.move_bms_target_cluster_combo, 2, 3)
        cluster_layout.addWidget(self.move_bms_btn, 2, 4)
        site_layout.addWidget(cluster_group)

        site_group = QGroupBox("Cluster Overview")
        group_layout = QVBoxLayout(site_group)
        self.site_cluster_table = QTableWidget(0, 4)
        self.site_cluster_table.setHorizontalHeaderLabels(["Cluster", "BMS Devices", "PCS Devices", "BMS Count"])
        cluster_header = self.site_cluster_table.horizontalHeader()
        cluster_header.setSectionResizeMode(QHeaderView.Interactive)
        cluster_header.setStretchLastSection(False)
        self.site_cluster_table.setWordWrap(False)
        self.site_cluster_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.site_cluster_table.setHorizontalScrollMode(QTableWidget.ScrollPerPixel)
        self.site_cluster_table.setAlternatingRowColors(True)
        self.site_cluster_table.verticalHeader().setDefaultSectionSize(30)
        for i, width in enumerate([160, 260, 300, 100]):
            self.site_cluster_table.setColumnWidth(i, width)
        # Show roughly 5-10 rows by default; scroll the page if the content exceeds the window.
        self.site_cluster_table.setMinimumHeight(260)
        self.site_cluster_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        group_layout.addWidget(self.site_cluster_table)
        site_group.setMinimumHeight(320)
        site_layout.addWidget(site_group)
        site_layout.addStretch(1)
        tabs.addTab(site_tab, "Project")

def add_cluster(self) -> None:
        if not hasattr(self, "new_cluster_name_edit"):
            return

        name = self.new_cluster_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Warning", "Cluster name cannot be empty.")
            return

        if any(cluster.name == name for cluster in self.site.clusters):
            QMessageBox.warning(self, "Warning", f"Cluster '{name}' already exists.")
            return

        from ..models import Cluster

        cluster = Cluster(name=name)
        self.site.clusters.append(cluster)

        self.log(f"[INFO] Added cluster: {name}")

        self.new_cluster_name_edit.clear()
        self.save_site_config()
        self.refresh_site_view()
        self.refresh_overview()

