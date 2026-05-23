from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "ESS-AIO"


def app_base_dir() -> Path:
    """Return the directory that contains bundled resources.

    Works in source checkout and PyInstaller one-folder/one-file builds.
    """
    if getattr(sys, "frozen", False):
        candidates = []
        if hasattr(sys, "_MEIPASS"):
            candidates.append(Path(getattr(sys, "_MEIPASS")))
        candidates.append(Path(sys.executable).resolve().parent)
        candidates.append(Path(sys.executable).resolve().parent / "_internal")
        for c in candidates:
            if c.exists():
                return c
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_path(relative: str | Path) -> Path:
    relative = Path(relative)
    base = app_base_dir()
    # Try common PyInstaller locations first.
    candidates = [
        base / relative,
        base / "_internal" / relative,
        Path(__file__).resolve().parent.parent / relative,
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def user_data_dir() -> Path:
    if os.name == "nt":
        root = os.getenv("APPDATA") or os.getenv("LOCALAPPDATA")
        base = Path(root) if root else Path.home() / "AppData" / "Roaming"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home() / ".local" / "share"
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_cache_dir() -> Path:
    if os.name == "nt":
        root = os.getenv("LOCALAPPDATA")
        base = Path(root) if root else Path.home() / "AppData" / "Local"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path.home() / ".cache"
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def packet_cache_dir() -> Path:
    path = user_cache_dir() / "packet_cache"
    path.mkdir(parents=True, exist_ok=True)
    return path
