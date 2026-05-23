from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QTabWidget,
)


def _build_timeline_tab(self, tabs: QTabWidget) -> None:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(12)

    top_group = QGroupBox("Event Timeline")
    top = QHBoxLayout(top_group)

    self.timeline_refresh_btn = QPushButton("Refresh Timeline")
    self.timeline_refresh_btn.clicked.connect(self.refresh_event_timeline)
    self.timeline_export_btn = QPushButton("Export CSV")
    self.timeline_export_btn.clicked.connect(self.export_event_timeline_csv)

    self.timeline_filter_combo = QComboBox()
    self.timeline_filter_combo.addItems(["All", "Critical/Error", "Warning", "Control", "Modbus", "CAN", "Cutoff/Derating", "Signal Compare"])
    self.timeline_filter_combo.currentTextChanged.connect(self.refresh_event_timeline_table)

    self.timeline_search_edit = QLineEdit()
    self.timeline_search_edit.setPlaceholderText("Search event / source / detail")
    self.timeline_search_edit.textChanged.connect(self.refresh_event_timeline_table)

    top.addWidget(self.timeline_refresh_btn)
    top.addWidget(self.timeline_export_btn)
    top.addWidget(QLabel("View:"))
    top.addWidget(self.timeline_filter_combo)
    top.addWidget(QLabel("Search:"))
    top.addWidget(self.timeline_search_edit, 1)
    layout.addWidget(top_group)

    self.timeline_summary_label = QLabel("No timeline built")
    layout.addWidget(self.timeline_summary_label)

    self.timeline_table = QTableWidget(0, 8)
    self.timeline_table.setHorizontalHeaderLabels([
        "Time", "Severity", "Category", "Source", "Title", "Detail", "Suggestion", "Order",
    ])
    self.timeline_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    self.timeline_table.verticalHeader().setDefaultSectionSize(28)
    self.timeline_table.itemSelectionChanged.connect(self.on_timeline_row_selected)
    layout.addWidget(self.timeline_table, 2)

    hint_group = QGroupBox("Root Cause Hints")
    hint_layout = QVBoxLayout(hint_group)
    self.timeline_hint_text = QTextEdit()
    self.timeline_hint_text.setReadOnly(True)
    self.timeline_hint_text.setMinimumHeight(120)
    hint_layout.addWidget(self.timeline_hint_text)
    layout.addWidget(hint_group)

    tabs.addTab(page, "Event Timeline")
