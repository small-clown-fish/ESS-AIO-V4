from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class _TemplateDropLabel(QLabel):
    def __init__(self, owner) -> None:
        super().__init__("Drop .ess-template.zip / .zip here or use Import Template Package")
        self.owner = owner
        self.setAlignment(Qt.AlignCenter)
        self.setAcceptDrops(True)
        self.setMinimumHeight(42)
        self.setStyleSheet("border: 1px dashed #64748b; border-radius: 8px; padding: 8px; color: #bfdbfe;")

    def dragEnterEvent(self, event):  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):  # type: ignore[override]
        urls = event.mimeData().urls()
        if not urls:
            return
        path = urls[0].toLocalFile()
        if path:
            self.owner.import_template_package(path)


def _build_templates_tab(self, tabs: QTabWidget) -> None:
    template_tab = QWidget()
    layout = QVBoxLayout(template_tab)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(12)

    package_group = QGroupBox("ESS-AIO Template Packages")
    package_layout = QVBoxLayout(package_group)
    package_layout.setSpacing(8)

    self.template_drop_label = _TemplateDropLabel(self)
    package_layout.addWidget(self.template_drop_label)

    package_btn_row = QHBoxLayout()
    self.import_template_package_btn = QPushButton("Import Template Package")
    self.import_template_package_btn.clicked.connect(self.import_template_package)
    self.validate_template_package_btn = QPushButton("Validate")
    self.validate_template_package_btn.clicked.connect(self.validate_selected_template_package)
    self.apply_template_package_btn = QPushButton("Apply to Current Profile")
    self.apply_template_package_btn.clicked.connect(self.apply_selected_template_package)
    self.export_template_package_btn = QPushButton("Export Template Package")
    self.export_template_package_btn.clicked.connect(self.export_selected_template_package)
    self.refresh_template_package_btn = QPushButton("Refresh")
    self.refresh_template_package_btn.clicked.connect(self.refresh_template_package_view)

    for btn in [
        self.import_template_package_btn,
        self.validate_template_package_btn,
        self.apply_template_package_btn,
        self.export_template_package_btn,
        self.refresh_template_package_btn,
    ]:
        package_btn_row.addWidget(btn)
    package_btn_row.addStretch()
    package_layout.addLayout(package_btn_row)

    self.template_package_table = QTableWidget(0, 5)
    self.template_package_table.setHorizontalHeaderLabels(["Folder", "Name", "Version", "Type", "Description"])
    self.template_package_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    self.template_package_table.verticalHeader().setDefaultSectionSize(28)
    self.template_package_table.itemSelectionChanged.connect(self.on_template_package_selected)
    package_layout.addWidget(self.template_package_table, 1)

    self.template_preview_text = QTextEdit()
    self.template_preview_text.setReadOnly(True)
    self.template_preview_text.setMinimumHeight(120)
    package_layout.addWidget(self.template_preview_text)

    layout.addWidget(package_group, 2)

    info_group = QGroupBox("Point Table Template Management")
    info_layout = QVBoxLayout(info_group)
    self.template_info_label = QLabel("Manage BMS / PCS point table JSON templates and driver bindings for the current profile.")
    info_layout.addWidget(self.template_info_label)

    driver_row = QHBoxLayout()
    self.bms_driver_combo = QComboBox()
    self.pcs_driver_combo = QComboBox()
    self.apply_driver_binding_btn = QPushButton("Apply Driver Binding")
    self.apply_driver_binding_btn.clicked.connect(self.apply_driver_binding)
    driver_row.addWidget(QLabel("BMS Driver:"))
    driver_row.addWidget(self.bms_driver_combo)
    driver_row.addWidget(QLabel("PCS Driver:"))
    driver_row.addWidget(self.pcs_driver_combo)
    driver_row.addWidget(self.apply_driver_binding_btn)
    driver_row.addStretch()
    info_layout.addLayout(driver_row)

    btn_row = QHBoxLayout()
    self.import_point_template_btn = QPushButton("Import Point Table JSON")
    self.import_point_template_btn.clicked.connect(self.import_point_table_template)
    self.apply_point_template_btn = QPushButton("Set Selected As Active")
    self.apply_point_template_btn.clicked.connect(self.apply_selected_point_table_template)
    self.refresh_point_template_btn = QPushButton("Refresh Point Tables")
    self.refresh_point_template_btn.clicked.connect(self.refresh_point_template_view)
    self.open_templates_folder_btn = QPushButton("Open Point Tables Folder")
    self.open_templates_folder_btn.clicked.connect(self.open_point_templates_folder)

    btn_row.addWidget(self.import_point_template_btn)
    btn_row.addWidget(self.apply_point_template_btn)
    btn_row.addWidget(self.refresh_point_template_btn)
    btn_row.addWidget(self.open_templates_folder_btn)
    btn_row.addStretch()
    info_layout.addLayout(btn_row)

    self.point_template_table = QTableWidget(0, 5)
    self.point_template_table.setHorizontalHeaderLabels(["File", "Title", "Version", "Date", "Active"])
    self.point_template_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    self.point_template_table.verticalHeader().setDefaultSectionSize(28)
    info_layout.addWidget(self.point_template_table, 1)

    layout.addWidget(info_group, 1)

    tabs.addTab(template_tab, "Templates")
