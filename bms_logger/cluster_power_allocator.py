from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List


@dataclass(slots=True)
class PcsDispatchTarget:
    name: str
    requested_kw: float
    limited_kw: float
    reason: str = ""


class ClusterPowerAllocator:
    """EMS-level power allocator for one BMS / multiple PCS cluster.

    The BMS limit is treated as the total cluster limit. The allocator then splits
    the final cluster target across online PCS devices. For commissioning, equal
    split is the safe default.
    """

    @staticmethod
    def clamp_total_power(requested_kw: float, allowed_kw: float | None, margin: float = 1.0) -> tuple[float, bool, str]:
        if allowed_kw is None or allowed_kw <= 0:
            return requested_kw, False, "no valid BMS cluster limit"
        allowed = abs(float(allowed_kw)) * max(0.0, float(margin or 1.0))
        final_abs = min(abs(float(requested_kw)), allowed)
        final = final_abs if requested_kw >= 0 else -final_abs
        return final, abs(final) < abs(float(requested_kw)) - 1e-9, f"BMS allowed cluster power={allowed:.3f}kW"

    @staticmethod
    def equal_split(total_kw: float, pcs_names: Iterable[str]) -> Dict[str, float]:
        names = [str(n) for n in pcs_names if str(n).strip()]
        if not names:
            return {}
        per = float(total_kw) / len(names)
        return {name: per for name in names}

    @staticmethod
    def capacity_weighted(total_kw: float, pcs_configs: Dict[str, Dict[str, Any]], pcs_names: Iterable[str]) -> Dict[str, float]:
        names = [str(n) for n in pcs_names if str(n).strip()]
        if not names:
            return {}
        weights: Dict[str, float] = {}
        for name in names:
            cfg = pcs_configs.get(name, {}) if isinstance(pcs_configs, dict) else {}
            rated = cfg.get("rated_kw") or cfg.get("rated_power_kw") or cfg.get("capacity_kw") or 1.0
            try:
                weights[name] = max(0.0, float(rated))
            except Exception:
                weights[name] = 1.0
        total_weight = sum(weights.values())
        if total_weight <= 0:
            return ClusterPowerAllocator.equal_split(total_kw, names)
        return {name: float(total_kw) * weights[name] / total_weight for name in names}

    @staticmethod
    def allocate(total_kw: float, pcs_configs: Dict[str, Dict[str, Any]], pcs_names: Iterable[str], mode: str = "equal_split") -> Dict[str, float]:
        mode = (mode or "equal_split").lower()
        enabled_names: List[str] = []
        for name in pcs_names:
            cfg = pcs_configs.get(name, {}) if isinstance(pcs_configs, dict) else {}
            if cfg and cfg.get("enabled", True) is False:
                continue
            enabled_names.append(str(name))
        if mode in {"capacity_weighted", "capacity", "weighted"}:
            return ClusterPowerAllocator.capacity_weighted(total_kw, pcs_configs, enabled_names)
        return ClusterPowerAllocator.equal_split(total_kw, enabled_names)
