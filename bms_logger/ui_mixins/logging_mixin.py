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





class LoggingMixin:
    def _should_show_log_message(self, message: str, *, interval: float = 5.0) -> bool:
        """Throttle repeated high-frequency UI log lines.

        The operation log still receives important ERROR/CUTOFF entries, but the
        QTextEdit view is protected from thousands of identical timeout lines.
        """
        import re
        import time

        noisy_patterns = (
            "Read telemetry failed",
            "Connect failed",
            "connect failed",
            "Broken pipe",
            "transaction_id",
            "No response received",
            "Heartbeat exception",
            "BMS_TIMEOUT",
            "cluster allowed power is 0",
        )
        if not (message.startswith("[ERROR]") or any(p in message for p in noisy_patterns)):
            return True
        bucket = getattr(self, "_log_throttle_state", None)
        if bucket is None:
            bucket = {}
            self._log_throttle_state = bucket
        # Normalize counters/details so repeated failures collapse together.
        key = message
        key = re.sub(r"transaction_id=\d+", "transaction_id=n", key)
        key = re.sub(r"got id=\d+", "got id=n", key)
        key = re.sub(r"\(\d+\)", "(n)", key)
        key = re.sub(r"retry=\d+s", "retry=ns", key)
        now = time.time()
        last = float(bucket.get(key, 0.0))
        if now - last < interval:
            return False
        bucket[key] = now
        return True

    def log(self, message: str) -> None:
        show_in_view = self._should_show_log_message(message)
        if hasattr(self, "log_text") and show_in_view:
            self.log_text.append(message)

            # 限制最大行数（比如 1000 行）
            doc = self.log_text.document()
            max_lines = 1000
            if doc.blockCount() > max_lines:
                cursor = self.log_text.textCursor()
                cursor.movePosition(cursor.MoveOperation.Start)
                cursor.select(cursor.SelectionType.LineUnderCursor)
                cursor.removeSelectedText()
                cursor.deleteChar()

            # 自动滚动到底部
            self.log_text.verticalScrollBar().setValue(
                self.log_text.verticalScrollBar().maximum()
            )

        elif show_in_view:
            print(message)

        if message.startswith("[ERROR]") or message.startswith("[CUTOFF]"):
            self.operation_log(message)

    def control_log(self, message: str) -> None:
        if hasattr(self, "control_log_text"):
            self.control_log_text.append(message)

            doc = self.control_log_text.document()
            max_lines = 1000
            if doc.blockCount() > max_lines:
                cursor = self.control_log_text.textCursor()
                cursor.movePosition(cursor.MoveOperation.Start)
                cursor.select(cursor.SelectionType.LineUnderCursor)
                cursor.removeSelectedText()
                cursor.deleteChar()

            self.control_log_text.verticalScrollBar().setValue(
                self.control_log_text.verticalScrollBar().maximum()
            )

        else:
            print(message)

        self.operation_log(message)

    def operation_log(self, message: str) -> None:
        from datetime import datetime
        from pathlib import Path

        try:
            log_dir = self.get_profile_path("logs")
            log_dir.mkdir(parents=True, exist_ok=True)

            date_str = datetime.now().strftime("%Y%m%d")
            log_path = log_dir / f"operation_{date_str}.log"

            # Size based rotation for Windows/site long-run tests. Keep 5 files of
            # about 10MB per day so an error storm cannot fill the disk or slow UI.
            max_bytes = 10 * 1024 * 1024
            backup_count = 5
            try:
                if log_path.exists() and log_path.stat().st_size >= max_bytes:
                    for index in range(backup_count - 1, 0, -1):
                        src = log_dir / f"operation_{date_str}.log.{index}"
                        dst = log_dir / f"operation_{date_str}.log.{index + 1}"
                        if src.exists():
                            if dst.exists():
                                dst.unlink()
                            src.rename(dst)
                    first = log_dir / f"operation_{date_str}.log.1"
                    if first.exists():
                        first.unlink()
                    log_path.rename(first)
            except Exception:
                pass

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            line = f"{timestamp} {message}\n"

            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line)

        except Exception:
            pass

    def handle_load_operation_log(self) -> None:
        default_dir = self.get_profile_path("logs")

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load operation log",
            str(default_dir),
            "Log Files (*.log);;Text Files (*.txt);;All Files (*)",
        )

        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            self.log_text.setPlainText(content)
            self.log(f"[INFO] Loaded operation log: {path}")

        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to load operation log:\n{exc}")

    def handle_clear_log_view(self) -> None:
        if hasattr(self, "log_text"):
            self.log_text.clear()

