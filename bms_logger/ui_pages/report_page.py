from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


def _build_report_tab(self, tabs: QTabWidget) -> None:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(12)

    control_group = QGroupBox("Debug Session")
    control_layout = QGridLayout(control_group)
    control_layout.setHorizontalSpacing(10)
    control_layout.setVerticalSpacing(8)

    self.report_session_name_edit = QLineEdit("Default Session")
    self.report_session_notes_edit = QTextEdit()
    self.report_session_notes_edit.setPlaceholderText("现场、客户、问题现象、测试目的、结论备注……")
    self.report_session_notes_edit.setMaximumHeight(90)

    self.start_session_btn = QPushButton("Start Session")
    self.start_session_btn.clicked.connect(self.start_debug_session)
    self.end_session_btn = QPushButton("End Session")
    self.end_session_btn.clicked.connect(self.end_debug_session)
    self.generate_report_btn = QPushButton("Generate HTML Report")
    self.generate_report_btn.clicked.connect(self.generate_debug_report)
    self.export_debug_package_btn = QPushButton("Export Debug Package")
    self.export_debug_package_btn.clicked.connect(self.export_debug_package)
    self.open_reports_folder_btn = QPushButton("Open Reports Folder")
    self.open_reports_folder_btn.clicked.connect(self.open_reports_folder)

    control_layout.addWidget(QLabel("Session Name"), 0, 0)
    control_layout.addWidget(self.report_session_name_edit, 0, 1, 1, 3)
    control_layout.addWidget(self.start_session_btn, 0, 4)
    control_layout.addWidget(self.end_session_btn, 0, 5)
    control_layout.addWidget(QLabel("Notes"), 1, 0)
    control_layout.addWidget(self.report_session_notes_edit, 1, 1, 1, 5)
    control_layout.addWidget(self.generate_report_btn, 2, 1)
    control_layout.addWidget(self.export_debug_package_btn, 2, 2)
    control_layout.addWidget(self.open_reports_folder_btn, 2, 3)

    layout.addWidget(control_group)

    summary_group = QGroupBox("Session Summary")
    summary_layout = QVBoxLayout(summary_group)
    self.report_session_table = QTableWidget(0, 2)
    self.report_session_table.setHorizontalHeaderLabels(["Field", "Value"])
    self.report_session_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    self.report_session_table.verticalHeader().setDefaultSectionSize(28)
    summary_layout.addWidget(self.report_session_table)
    self.report_path_label = QLabel("Report/package path: -")
    self.report_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    summary_layout.addWidget(self.report_path_label)
    layout.addWidget(summary_group)

    preview_group = QGroupBox("Report Preview")
    preview_layout = QVBoxLayout(preview_group)
    self.report_preview_text = QTextEdit()
    self.report_preview_text.setReadOnly(True)
    preview_layout.addWidget(self.report_preview_text)
    layout.addWidget(preview_group, 1)

    tabs.addTab(page, "Report")
