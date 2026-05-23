from __future__ import annotations

from PySide6.QtWidgets import (
    QGroupBox,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QTabWidget,
)


def _build_release_tab(self, tabs: QTabWidget) -> None:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(12)

    info_group = QGroupBox("ESS-AIO Release Information")
    info_layout = QVBoxLayout(info_group)
    self.release_info_table = QTableWidget(0, 2)
    self.release_info_table.setHorizontalHeaderLabels(["Field", "Value"])
    self.release_info_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    self.release_info_table.verticalHeader().setDefaultSectionSize(28)
    info_layout.addWidget(self.release_info_table)
    layout.addWidget(info_group)

    check_group = QGroupBox("Startup Self Check / Profile Migration")
    check_layout = QVBoxLayout(check_group)
    btn_row = QHBoxLayout()
    self.run_self_check_btn = QPushButton("Run Self Check")
    self.run_self_check_btn.clicked.connect(self.run_startup_self_check)
    self.open_crash_logs_btn = QPushButton("Open Crash Logs")
    self.open_crash_logs_btn.clicked.connect(self.open_crash_log_folder)
    self.about_essaio_btn = QPushButton("About ESS-AIO")
    self.about_essaio_btn.clicked.connect(self.show_about_dialog)
    btn_row.addWidget(self.run_self_check_btn)
    btn_row.addWidget(self.open_crash_logs_btn)
    btn_row.addWidget(self.about_essaio_btn)
    btn_row.addStretch()
    check_layout.addLayout(btn_row)
    self.release_check_text = QTextEdit()
    self.release_check_text.setReadOnly(True)
    check_layout.addWidget(self.release_check_text)
    layout.addWidget(check_group, 1)

    tabs.addTab(page, "Release")
