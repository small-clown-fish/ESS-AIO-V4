from __future__ import annotations

from pathlib import Path
from bms_logger.paths import user_data_dir
import os

# Windows/HP laptops can be slow or unstable with Qt hardware OpenGL.
# Must be set before importing PySide6 / bms_logger.ui.
os.environ.setdefault("QT_OPENGL", "software")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

from bms_logger.release_manager import install_crash_handler
from bms_logger.ui import run


if __name__ == "__main__":
    install_crash_handler(user_data_dir() / "logs")
    run()
