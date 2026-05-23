from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


def profile_key_from_path(path: str | Path) -> str:
    stem = Path(path).stem
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("_")
    return stem or "pcs_profile"


def profile_display_name(key: str, profile: Dict[str, Any] | None = None) -> str:
    if profile:
        return str(profile.get("display_name") or profile.get("name") or key)
    return key


def safe_load_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"PCS profile is not a JSON object: {path}")
    return data


def list_profile_files(dirs: Iterable[Path]) -> Dict[str, Path]:
    found: Dict[str, Path] = {}
    for directory in dirs:
        if not directory.exists() or not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            key = profile_key_from_path(path)
            found.setdefault(key, path)
    return found


def load_profile(profile_key_or_path: str, dirs: Iterable[Path]) -> Tuple[str, Dict[str, Any], Path]:
    raw = str(profile_key_or_path or "").strip()
    if not raw:
        raise FileNotFoundError("Empty PCS profile key")

    candidate = Path(raw)
    if candidate.exists():
        key = profile_key_from_path(candidate)
        data = safe_load_json(candidate)
        data.setdefault("profile_key", key)
        return key, data, candidate

    files = list_profile_files(dirs)
    key = profile_key_from_path(raw)
    if raw in files:
        path = files[raw]
    elif key in files:
        path = files[key]
    else:
        raise FileNotFoundError(f"PCS profile not found: {raw}")

    data = safe_load_json(path)
    data.setdefault("profile_key", key)
    return key, data, path


def merge_device_with_profile(device_cfg: Dict[str, Any], profile: Dict[str, Any] | None) -> Dict[str, Any]:
    """Return runtime PCS config used by PcsClient.

    The profile owns protocol details (points/driver/vendor/model). The device instance owns
    connection/runtime details (name/host/port/unit_id/enabled/fake_scenario). Device values
    intentionally override profile defaults.
    """
    if not profile:
        return dict(device_cfg)

    merged = dict(profile)
    merged.update({k: v for k, v in device_cfg.items() if k != "points"})
    if "points" in device_cfg and device_cfg.get("points"):
        # Backward compatibility: old device entries may carry embedded points.
        merged["points"] = device_cfg["points"]
    else:
        merged["points"] = profile.get("points", {})
    merged.setdefault("driver", profile.get("driver", "generic_modbus_pcs"))
    merged.setdefault("timeout", profile.get("timeout", 3.0))
    return merged


def install_profile(src_path: str | Path, target_dir: Path, *, key: str | None = None) -> Tuple[str, Path]:
    src = Path(src_path)
    target_dir.mkdir(parents=True, exist_ok=True)
    profile_key = profile_key_from_path(key or src)
    target = target_dir / f"{profile_key}.json"
    if src.resolve() != target.resolve():
        shutil.copy2(src, target)
    return profile_key, target
