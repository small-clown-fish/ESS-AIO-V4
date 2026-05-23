from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QTabWidget,
    QComboBox,
    QSizePolicy,
    QDoubleSpinBox,
    QSpinBox,
    QCheckBox,
    QListWidget,
)


def _build_packet_analyzer_tab(self, tabs: QTabWidget) -> None:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(12)

    analyzer_tabs = QTabWidget()
    layout.addWidget(analyzer_tabs)

    self._build_modbus_packet_tab(analyzer_tabs)
    self._build_can_packet_tab(analyzer_tabs)
    self._build_joint_analysis_tab(analyzer_tabs)
    self._build_packet_diagnosis_tab(analyzer_tabs)

    tabs.addTab(page, "Packet Analyzer")


def _build_modbus_packet_tab(self, tabs: QTabWidget) -> None:
    page = QScrollArea()
    page.setWidgetResizable(True)
    page.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(10, 10, 10, 10)
    layout.setSpacing(10)
    page.setWidget(content)

    top_group = QGroupBox("Modbus TCP Capture")
    top = QHBoxLayout(top_group)

    self.packet_file_edit = QLineEdit()
    self.packet_file_edit.setPlaceholderText("Select .pcap or .pcapng file")
    self.packet_load_btn = QPushButton("Load Capture")
    self.packet_load_btn.clicked.connect(self.load_packet_capture)
    self.packet_clear_btn = QPushButton("Clear")
    self.packet_clear_btn.clicked.connect(self.clear_packet_capture)
    self.packet_export_btn = QPushButton("Export CSV")
    self.packet_export_btn.clicked.connect(self.export_packet_analysis_csv)
    self.packet_insight_btn = QPushButton("Analyze Issues")
    self.packet_insight_btn.clicked.connect(self.analyze_modbus_issues)
    self.packet_replay_btn = QPushButton("Send to Register Tool")
    self.packet_replay_btn.clicked.connect(self.send_selected_modbus_to_register_tool)
    self.packet_filter_edit = QLineEdit()
    self.packet_filter_edit.setPlaceholderText("Filter: IP / FC / address / status")
    self.packet_filter_edit.textChanged.connect(self.refresh_packet_table)

    top.addWidget(QLabel("Capture:"))
    top.addWidget(self.packet_file_edit, 2)
    top.addWidget(self.packet_load_btn)
    top.addWidget(self.packet_clear_btn)
    top.addWidget(self.packet_export_btn)
    top.addWidget(self.packet_insight_btn)
    top.addWidget(self.packet_replay_btn)
    top.addWidget(QLabel("Filter:"))
    top.addWidget(self.packet_filter_edit, 1)
    layout.addWidget(top_group)

    browse_group = QGroupBox("Browse / Filter Large Capture")
    browse = QHBoxLayout(browse_group)
    self.packet_addr_filter_edit = QLineEdit()
    self.packet_addr_filter_edit.setPlaceholderText("Address, e.g. 0x0020")
    self.packet_time_from_edit = QLineEdit()
    self.packet_time_from_edit.setPlaceholderText("From s")
    self.packet_time_to_edit = QLineEdit()
    self.packet_time_to_edit.setPlaceholderText("To s")
    self.packet_page_size_spin = QSpinBox()
    self.packet_page_size_spin.setRange(100, 50000)
    self.packet_page_size_spin.setSingleStep(500)
    self.packet_page_size_spin.setValue(2000)
    self.packet_page_spin = QSpinBox()
    self.packet_page_spin.setRange(1, 1)
    self.packet_page_spin.setValue(1)
    self.packet_desc_check = QCheckBox("Newest first")
    self.packet_apply_filter_btn = QPushButton("Apply")
    self.packet_apply_filter_btn.clicked.connect(self.apply_packet_table_filters)
    self.packet_prev_btn = QPushButton("<")
    self.packet_prev_btn.clicked.connect(self.packet_prev_page)
    self.packet_next_btn = QPushButton(">")
    self.packet_next_btn.clicked.connect(self.packet_next_page)
    self.packet_first_btn = QPushButton("<<")
    self.packet_first_btn.clicked.connect(self.packet_first_page)
    self.packet_last_btn = QPushButton(">>")
    self.packet_last_btn.clicked.connect(self.packet_last_page)
    self.packet_page_label = QLabel("Page 1 / 1")
    browse.addWidget(QLabel("Addr:"))
    browse.addWidget(self.packet_addr_filter_edit)
    browse.addWidget(QLabel("Time:"))
    browse.addWidget(self.packet_time_from_edit)
    browse.addWidget(QLabel("~"))
    browse.addWidget(self.packet_time_to_edit)
    browse.addWidget(QLabel("Rows/page:"))
    browse.addWidget(self.packet_page_size_spin)
    browse.addWidget(self.packet_desc_check)
    browse.addWidget(self.packet_apply_filter_btn)
    browse.addStretch(1)
    browse.addWidget(self.packet_first_btn)
    browse.addWidget(self.packet_prev_btn)
    browse.addWidget(self.packet_page_spin)
    browse.addWidget(self.packet_next_btn)
    browse.addWidget(self.packet_last_btn)
    browse.addWidget(self.packet_page_label)
    layout.addWidget(browse_group)

    self.packet_summary_label = QLabel("No Modbus capture loaded")
    layout.addWidget(self.packet_summary_label)

    self.packet_table = QTableWidget(0, 12)
    self.packet_table.setHorizontalHeaderLabels([
        "#", "Time", "Dir", "Src", "Dst", "TID", "Unit", "FC", "Addr", "Count/Value", "Status", "Latency(ms)",
    ])
    self.packet_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    self.packet_table.verticalHeader().setDefaultSectionSize(26)
    self.packet_table.setMinimumHeight(26 * 10 + 36)
    self.packet_table.itemSelectionChanged.connect(self.on_packet_row_selected)
    layout.addWidget(self.packet_table)

    issue_group = QGroupBox("Communication Issue Summary")
    issue_layout = QVBoxLayout(issue_group)
    self.packet_issue_table = QTableWidget(0, 6)
    self.packet_issue_table.setHorizontalHeaderLabels(["Type", "Key", "Count", "Worst/Avg", "Suggestion", "Severity"])
    self.packet_issue_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    self.packet_issue_table.verticalHeader().setDefaultSectionSize(26)
    self.packet_issue_table.setMinimumHeight(26 * 8 + 36)
    issue_layout.addWidget(self.packet_issue_table, 2)

    self.packet_diagnosis_text = QTextEdit()
    self.packet_diagnosis_text.setReadOnly(True)
    self.packet_diagnosis_text.setMinimumHeight(170)
    self.packet_diagnosis_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    self.packet_diagnosis_text.setPlaceholderText("Communication diagnosis conclusions will appear here after analysis.")
    issue_layout.addWidget(QLabel("Diagnosis Conclusion:"))
    issue_layout.addWidget(self.packet_diagnosis_text, 1)
    layout.addWidget(issue_group, 2)

    detail_group = QGroupBox("Packet Detail")
    detail_layout = QVBoxLayout(detail_group)
    self.packet_detail_text = QTextEdit()
    self.packet_detail_text.setReadOnly(True)
    self.packet_detail_text.setMinimumHeight(130)
    detail_layout.addWidget(self.packet_detail_text)
    layout.addWidget(detail_group)

    tabs.addTab(page, "Modbus TCP")


def _build_can_packet_tab(self, tabs: QTabWidget) -> None:
    page = QScrollArea()
    page.setWidgetResizable(True)
    page.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(10, 10, 10, 10)
    layout.setSpacing(10)
    page.setWidget(content)

    top_group = QGroupBox("CAN Log Analyzer")
    top = QHBoxLayout(top_group)

    self.can_file_edit = QLineEdit()
    self.can_file_edit.setPlaceholderText("Select CAN log: .asc / .log / .trc / .csv / .txt / SocketCAN .pcap")
    self.can_load_btn = QPushButton("Load CAN Log")
    self.can_load_btn.clicked.connect(self.load_can_log)
    self.can_clear_btn = QPushButton("Clear CAN")
    self.can_clear_btn.clicked.connect(self.clear_can_log)

    self.can_mapping_edit = QLineEdit()
    self.can_mapping_edit.setPlaceholderText("Optional DBC or JSON mapping")
    self.can_mapping_btn = QPushButton("DBC / Mapping")
    self.can_mapping_btn.clicked.connect(self.choose_can_mapping)
    self.can_mapping_clear_btn = QPushButton("Clear DBC")
    self.can_mapping_clear_btn.clicked.connect(self.clear_can_mapping)

    self.can_export_frames_btn = QPushButton("Export Frames")
    self.can_export_frames_btn.clicked.connect(self.export_can_frames_csv)
    self.can_export_stats_btn = QPushButton("Export Stats")
    self.can_export_stats_btn.clicked.connect(self.export_can_stats_csv)

    top.addWidget(QLabel("CAN:"))
    top.addWidget(self.can_file_edit, 2)
    top.addWidget(self.can_load_btn)
    top.addWidget(self.can_clear_btn)
    top.addWidget(QLabel("Map:"))
    top.addWidget(self.can_mapping_edit, 1)
    top.addWidget(self.can_mapping_btn)
    top.addWidget(self.can_mapping_clear_btn)
    top.addWidget(self.can_export_frames_btn)
    top.addWidget(self.can_export_stats_btn)
    layout.addWidget(top_group)

    filter_group = QGroupBox("Filter")
    filter_layout = QHBoxLayout(filter_group)
    self.can_filter_edit = QLineEdit()
    self.can_filter_edit.setPlaceholderText("Filter: CAN ID / channel / decoded / status")
    self.can_filter_edit.textChanged.connect(self.refresh_can_table)
    self.can_view_combo = QComboBox()
    self.can_view_combo.addItems(["Frames", "ID Statistics", "Anomalies"])
    self.can_view_combo.currentTextChanged.connect(self.refresh_can_table)
    filter_layout.addWidget(QLabel("View:"))
    filter_layout.addWidget(self.can_view_combo)
    filter_layout.addWidget(QLabel("Search:"))
    filter_layout.addWidget(self.can_filter_edit, 1)
    layout.addWidget(filter_group)

    can_browse_group = QGroupBox("Browse / Filter Large CAN Log")
    can_browse = QHBoxLayout(can_browse_group)
    self.can_id_filter_edit = QLineEdit()
    self.can_id_filter_edit.setPlaceholderText("CAN ID, e.g. 0x0B01FF43")
    self.can_time_from_edit = QLineEdit()
    self.can_time_from_edit.setPlaceholderText("From s")
    self.can_time_to_edit = QLineEdit()
    self.can_time_to_edit.setPlaceholderText("To s")
    self.can_page_size_spin = QSpinBox()
    self.can_page_size_spin.setRange(100, 50000)
    self.can_page_size_spin.setSingleStep(500)
    self.can_page_size_spin.setValue(2000)
    self.can_page_spin = QSpinBox()
    self.can_page_spin.setRange(1, 1)
    self.can_page_spin.setValue(1)
    self.can_desc_check = QCheckBox("Newest first")
    self.can_apply_filter_btn = QPushButton("Apply")
    self.can_apply_filter_btn.clicked.connect(self.apply_can_table_filters)
    self.can_first_btn = QPushButton("<<")
    self.can_first_btn.clicked.connect(self.can_first_page)
    self.can_prev_btn = QPushButton("<")
    self.can_prev_btn.clicked.connect(self.can_prev_page)
    self.can_next_btn = QPushButton(">")
    self.can_next_btn.clicked.connect(self.can_next_page)
    self.can_last_btn = QPushButton(">>")
    self.can_last_btn.clicked.connect(self.can_last_page)
    self.can_page_label = QLabel("Page 1 / 1")
    can_browse.addWidget(QLabel("ID:"))
    can_browse.addWidget(self.can_id_filter_edit)
    can_browse.addWidget(QLabel("Time:"))
    can_browse.addWidget(self.can_time_from_edit)
    can_browse.addWidget(QLabel("~"))
    can_browse.addWidget(self.can_time_to_edit)
    can_browse.addWidget(QLabel("Rows/page:"))
    can_browse.addWidget(self.can_page_size_spin)
    can_browse.addWidget(self.can_desc_check)
    can_browse.addWidget(self.can_apply_filter_btn)
    can_browse.addStretch(1)
    can_browse.addWidget(self.can_first_btn)
    can_browse.addWidget(self.can_prev_btn)
    can_browse.addWidget(self.can_page_spin)
    can_browse.addWidget(self.can_next_btn)
    can_browse.addWidget(self.can_last_btn)
    can_browse.addWidget(self.can_page_label)
    layout.addWidget(can_browse_group)

    self.can_summary_label = QLabel("No CAN log loaded")
    layout.addWidget(self.can_summary_label)

    self.can_frame_table = QTableWidget(0, 12)
    self.can_frame_table.setHorizontalHeaderLabels([
        "#", "Time", "Channel", "CAN ID", "Message", "DLC", "Data", "Dir", "Type", "Status", "Meaning", "Decoded",
    ])
    self.can_frame_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    self.can_frame_table.verticalHeader().setDefaultSectionSize(26)
    self.can_frame_table.setMinimumHeight(26 * 10 + 36)
    self.can_frame_table.itemSelectionChanged.connect(self.on_can_row_selected)
    layout.addWidget(self.can_frame_table)

    self.can_stats_table = QTableWidget(0, 8)
    self.can_stats_table.setHorizontalHeaderLabels([
        "CAN ID", "Message", "Count", "First", "Last", "Avg Period(ms)", "Freq(Hz)", "DLCs",
    ])
    self.can_stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    self.can_stats_table.verticalHeader().setDefaultSectionSize(26)
    self.can_stats_table.setMinimumHeight(26 * 10 + 36)
    self.can_stats_table.hide()
    layout.addWidget(self.can_stats_table)

    self.can_anomaly_table = QTableWidget(0, 6)
    self.can_anomaly_table.setHorizontalHeaderLabels([
        "Type", "CAN ID", "Index", "Time", "Value", "Detail",
    ])
    self.can_anomaly_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    self.can_anomaly_table.verticalHeader().setDefaultSectionSize(26)
    self.can_anomaly_table.setMinimumHeight(26 * 10 + 36)
    self.can_anomaly_table.hide()
    layout.addWidget(self.can_anomaly_table)

    plot_group = QGroupBox("CAN Signal Plot")
    plot_layout = QVBoxLayout(plot_group)
    plot_top = QHBoxLayout()
    self.packet_can_signal_combo = QComboBox()
    self.packet_can_signal_combo.setPlaceholderText("Decoded CAN signal")
    self.packet_can_add_signal_btn = QPushButton("Add Signal")
    self.packet_can_add_signal_btn.clicked.connect(self.add_packet_can_signal_from_combo)
    self.packet_can_clear_signal_btn = QPushButton("Clear Plot")
    self.packet_can_clear_signal_btn.clicked.connect(self.clear_packet_can_signals)
    self.packet_can_export_signal_btn = QPushButton("Export Signal CSV")
    self.packet_can_export_signal_btn.clicked.connect(self.export_packet_can_signals_csv)
    plot_top.addWidget(QLabel("Signal:"))
    plot_top.addWidget(self.packet_can_signal_combo, 1)
    plot_top.addWidget(self.packet_can_add_signal_btn)
    plot_top.addWidget(self.packet_can_clear_signal_btn)
    plot_top.addWidget(self.packet_can_export_signal_btn)
    plot_layout.addLayout(plot_top)

    self.packet_can_selected_signals_list = QListWidget()
    self.packet_can_selected_signals_list.setMaximumHeight(70)
    plot_layout.addWidget(self.packet_can_selected_signals_list)

    self.packet_can_signal_series = []
    self.packet_can_signal_chart = QChart()
    self.packet_can_signal_chart.setTitle("Decoded CAN Signals from Packet Analyzer")
    self.packet_can_signal_axis_x = QValueAxis()
    self.packet_can_signal_axis_x.setTitleText("Time (s)")
    self.packet_can_signal_axis_x.setRange(0, 1)
    self.packet_can_signal_axis_y = QValueAxis()
    self.packet_can_signal_axis_y.setTitleText("Value")
    self.packet_can_signal_axis_y.setRange(0, 1)
    self.packet_can_signal_chart.addAxis(self.packet_can_signal_axis_x, Qt.AlignBottom)
    self.packet_can_signal_chart.addAxis(self.packet_can_signal_axis_y, Qt.AlignLeft)
    for i in range(4):
        series = QLineSeries()
        series.setName(f"Signal {i + 1}")
        self.packet_can_signal_chart.addSeries(series)
        series.attachAxis(self.packet_can_signal_axis_x)
        series.attachAxis(self.packet_can_signal_axis_y)
        self.packet_can_signal_series.append(series)
    self.packet_can_signal_chart_view = QChartView(self.packet_can_signal_chart)
    self.packet_can_signal_chart_view.setMinimumHeight(240)
    self.packet_can_signal_chart_view.setMaximumHeight(360)
    plot_layout.addWidget(self.packet_can_signal_chart_view)
    layout.addWidget(plot_group)

    detail_group = QGroupBox("CAN Detail")
    detail_layout = QVBoxLayout(detail_group)
    self.can_detail_text = QTextEdit()
    self.can_detail_text.setReadOnly(True)
    self.can_detail_text.setMinimumHeight(120)
    detail_layout.addWidget(self.can_detail_text)
    layout.addWidget(detail_group)

    tabs.addTab(page, "CAN")



def _build_joint_analysis_tab(self, tabs: QTabWidget) -> None:
    page = QScrollArea()
    page.setWidgetResizable(True)
    page.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(10, 10, 10, 10)
    layout.setSpacing(10)
    page.setWidget(content)

    file_group = QGroupBox("CAN + Modbus Joint Analysis")
    file_layout = QVBoxLayout(file_group)

    row1 = QHBoxLayout()
    self.joint_asc_edit = QLineEdit()
    self.joint_asc_edit.setPlaceholderText("CAN ASC log, for example 26_0415_125444_1.ASC")
    self.joint_asc_btn = QPushButton("Select ASC")
    self.joint_asc_btn.clicked.connect(self.choose_joint_asc)
    row1.addWidget(QLabel("CAN ASC:"))
    row1.addWidget(self.joint_asc_edit, 1)
    row1.addWidget(self.joint_asc_btn)
    file_layout.addLayout(row1)

    row2 = QHBoxLayout()
    self.joint_modbus_edit = QLineEdit()
    self.joint_modbus_edit.setPlaceholderText("Wireshark Modbus capture: .pcapng / .pcap, or tshark CSV export")
    self.joint_modbus_btn = QPushButton("Select Modbus Capture")
    self.joint_modbus_btn.clicked.connect(self.choose_joint_modbus_csv)
    row2.addWidget(QLabel("Modbus Capture:"))
    row2.addWidget(self.joint_modbus_edit, 1)
    row2.addWidget(self.joint_modbus_btn)
    file_layout.addLayout(row2)

    row3 = QHBoxLayout()
    self.joint_dbc_edit = QLineEdit()
    self.joint_dbc_edit.setPlaceholderText("Default: bms_logger/protocols/ESS_PLT_MCAN_V3.28_20250611_Saveas.dbc")
    self.joint_dbc_btn = QPushButton("Select DBC")
    self.joint_dbc_btn.clicked.connect(self.choose_joint_dbc)
    row3.addWidget(QLabel("DBC:"))
    row3.addWidget(self.joint_dbc_edit, 1)
    row3.addWidget(self.joint_dbc_btn)
    file_layout.addLayout(row3)

    row4 = QHBoxLayout()
    self.joint_mapping_edit = QLineEdit()
    self.joint_mapping_edit.setPlaceholderText("Default: bms_logger/protocols/catl_v22_can_modbus_mapping.json")
    self.joint_mapping_btn = QPushButton("Select Mapping")
    self.joint_mapping_btn.clicked.connect(self.choose_joint_mapping)
    row4.addWidget(QLabel("Mapping:"))
    row4.addWidget(self.joint_mapping_edit, 1)
    row4.addWidget(self.joint_mapping_btn)
    file_layout.addLayout(row4)

    action_row = QHBoxLayout()
    self.joint_tolerance_spin = QDoubleSpinBox()
    self.joint_tolerance_spin.setDecimals(3)
    self.joint_tolerance_spin.setRange(0.001, 60.0)
    self.joint_tolerance_spin.setSingleStep(0.1)
    self.joint_tolerance_spin.setValue(0.5)
    self.joint_run_btn = QPushButton("Run Joint Analysis")
    self.joint_run_btn.clicked.connect(self.run_joint_analysis_ui)
    self.joint_export_btn = QPushButton("Export Result CSV")
    self.joint_export_btn.clicked.connect(self.export_joint_analysis_csv)
    action_row.addWidget(QLabel("Time tolerance (s):"))
    action_row.addWidget(self.joint_tolerance_spin)
    action_row.addStretch(1)
    action_row.addWidget(self.joint_run_btn)
    action_row.addWidget(self.joint_export_btn)
    file_layout.addLayout(action_row)

    layout.addWidget(file_group)

    self.joint_summary_label = QLabel("No joint analysis loaded")
    layout.addWidget(self.joint_summary_label)

    self.joint_table = QTableWidget(0, 10)
    self.joint_table.setHorizontalHeaderLabels([
        "CAN Time", "Modbus Time", "Δt(s)", "CAN ID", "Signal", "CAN Value",
        "Modbus Addr", "Modbus Raw", "Modbus Value", "Abs Diff",
    ])
    self.joint_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    self.joint_table.verticalHeader().setDefaultSectionSize(26)
    self.joint_table.setMinimumHeight(26 * 12 + 36)
    self.joint_table.itemSelectionChanged.connect(self.on_joint_row_selected)
    layout.addWidget(self.joint_table, 2)

    detail_group = QGroupBox("Joint Detail / Diagnosis")
    detail_layout = QVBoxLayout(detail_group)
    self.joint_detail_text = QTextEdit()
    self.joint_detail_text.setReadOnly(True)
    self.joint_detail_text.setMinimumHeight(160)
    self.joint_detail_text.setPlaceholderText("Select a row after running joint analysis.")
    detail_layout.addWidget(self.joint_detail_text)
    layout.addWidget(detail_group)

    tabs.addTab(page, "Joint Analysis")


def _build_packet_diagnosis_tab(self, tabs: QTabWidget) -> None:
    page = QScrollArea()
    page.setWidgetResizable(True)
    page.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(10, 10, 10, 10)
    layout.setSpacing(10)
    page.setWidget(content)

    action_group = QGroupBox("Packet Health Check / Fault Diagnosis")
    action_layout = QVBoxLayout(action_group)
    action_row = QHBoxLayout()
    self.packet_diagnosis_scope_combo = QComboBox()
    self.packet_diagnosis_scope_combo.addItems(["Auto", "CAN only", "Modbus only", "Cross / Joint"])
    self.packet_diagnosis_run_btn = QPushButton("Run Diagnosis")
    self.packet_diagnosis_run_btn.clicked.connect(self.run_packet_diagnosis)
    self.packet_diagnosis_clear_btn = QPushButton("Clear All Evidence")
    self.packet_diagnosis_clear_btn.clicked.connect(self.clear_packet_all_evidence)
    self.packet_diagnosis_export_csv_btn = QPushButton("Export CSV")
    self.packet_diagnosis_export_csv_btn.clicked.connect(self.export_packet_diagnosis_csv)
    self.packet_diagnosis_export_md_btn = QPushButton("Export Markdown")
    self.packet_diagnosis_export_md_btn.clicked.connect(self.export_packet_diagnosis_markdown)
    action_row.addWidget(QLabel("Scope:"))
    action_row.addWidget(self.packet_diagnosis_scope_combo)
    action_row.addWidget(QLabel("Evidence:"))
    action_row.addWidget(QLabel("Loaded Modbus capture + CAN log + optional joint analysis"), 1)
    action_row.addStretch(1)
    action_row.addWidget(self.packet_diagnosis_run_btn)
    action_row.addWidget(self.packet_diagnosis_clear_btn)
    action_row.addWidget(self.packet_diagnosis_export_csv_btn)
    action_row.addWidget(self.packet_diagnosis_export_md_btn)
    action_layout.addLayout(action_row)

    self.packet_diagnosis_summary = QTextEdit()
    self.packet_diagnosis_summary.setReadOnly(True)
    self.packet_diagnosis_summary.setMinimumHeight(130)
    self.packet_diagnosis_summary.setPlaceholderText(
        "Run Diagnosis after loading CAN / Modbus / Joint Analysis evidence.\n"
        "The tool will mark communication, protocol, mapping and battery-logic issues."
    )
    action_layout.addWidget(self.packet_diagnosis_summary)
    layout.addWidget(action_group)

    self.packet_diagnosis_table = QTableWidget(0, 8)
    self.packet_diagnosis_table.setHorizontalHeaderLabels([
        "Severity", "Layer", "Time", "Object", "Rule", "Description", "Evidence", "Suggested Action",
    ])
    self.packet_diagnosis_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    self.packet_diagnosis_table.verticalHeader().setDefaultSectionSize(28)
    self.packet_diagnosis_table.setMinimumHeight(26 * 15 + 36)
    self.packet_diagnosis_table.itemSelectionChanged.connect(self.on_packet_diagnosis_row_selected)
    layout.addWidget(self.packet_diagnosis_table, 2)

    detail_group = QGroupBox("Diagnosis Detail")
    detail_layout = QVBoxLayout(detail_group)
    self.packet_diagnosis_detail = QTextEdit()
    self.packet_diagnosis_detail.setReadOnly(True)
    self.packet_diagnosis_detail.setMinimumHeight(160)
    self.packet_diagnosis_detail.setPlaceholderText("Select an issue to see evidence and suggested troubleshooting steps.")
    detail_layout.addWidget(self.packet_diagnosis_detail)
    layout.addWidget(detail_group)

    tabs.addTab(page, "Diagnosis")
