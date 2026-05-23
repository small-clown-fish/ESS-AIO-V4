from __future__ import annotations

import json
import csv
from collections import deque
from pathlib import Path
from typing import Any, Dict

from PySide6.QtCharts import QChart, QLineSeries
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem, QInputDialog
from PySide6.QtGui import QColor





class DetailsMixin:
    def refresh_details(self, device_name: str) -> None:
        self.current_detail_device = device_name
        self.detail_device_label.setText(f"Current device: {device_name}")

        snapshot = self.latest_snapshots.get(device_name, {})
        for key, _label in self.DETAIL_FIELDS:
            value = snapshot.get(key, "-")
            self.detail_value_labels[key].setText(str(value))


