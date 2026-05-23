from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

from .paths import resource_path


def profile_key_from_path(path: str | Path) -> str:
    stem = Path(path).stem
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("_")
    return stem or "bms_profile"


def list_bms_profiles(dirs: Iterable[Path]) -> Dict[str, Path]:
    found: Dict[str, Path] = {}
    for directory in dirs:
        if not directory.exists() or not directory.is_dir():
            continue
        for child in sorted(directory.iterdir()):
            if child.is_dir() and (child / "bms_register_map.json").exists():
                found.setdefault(child.name, child)
    return found


def load_bms_profile(profile_key: str, dirs: Iterable[Path]) -> Tuple[str, Dict[str, Any], Path]:
    key = str(profile_key or "catl_v22").strip() or "catl_v22"
    profiles = list_bms_profiles(dirs)
    if key not in profiles:
        raise FileNotFoundError(f"BMS profile not found: {key}")
    path = profiles[key]
    meta_path = path / "profile.json"
    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
            if not isinstance(meta, dict):
                meta = {}
    else:
        meta = {}
    meta.setdefault("profile_key", key)
    meta.setdefault("display_name", key)
    meta["register_map_path"] = str(path / "bms_register_map.json")
    meta["alarm_map_path"] = str(path / "alarm_map.json")
    return key, meta, path


def default_bms_profile_dirs(extra_dir: Path | None = None) -> list[Path]:
    dirs = []
    if extra_dir is not None:
        dirs.append(extra_dir / "bms_profiles")
    dirs.append(resource_path("bms_profiles"))
    return dirs


def install_bms_profile(src_dir: str | Path, target_root: Path, *, key: str | None = None) -> tuple[str, Path]:
    src = Path(src_dir)
    if not src.is_dir():
        raise ValueError("BMS profile import expects a folder containing bms_register_map.json and alarm_map.json")
    if not (src / "bms_register_map.json").exists():
        raise ValueError("BMS profile folder missing bms_register_map.json")
    profile_key = key or src.name
    target = target_root / profile_key
    target.mkdir(parents=True, exist_ok=True)
    for filename in ["bms_register_map.json", "alarm_map.json", "profile.json"]:
        if (src / filename).exists():
            shutil.copy2(src / filename, target / filename)
    return profile_key, target
