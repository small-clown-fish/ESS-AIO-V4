from __future__ import annotations

from .ui_control_mixins.common_control_mixin import CommonControlMixin
from .ui_control_mixins.bms_control_mixin import BmsControlMixin
from .ui_control_mixins.hv_control_mixin import HvControlMixin
from .ui_control_mixins.pcs_control_mixin import PcsControlMixin
from .ui_control_mixins.cutoff_control_mixin import CutoffControlMixin
from .ui_control_mixins.execution_mixin import ExecutionMixin
from .ui_control_mixins.debug_control_mixin import DebugControlMixin
from .ui_control_mixins.derating_control_mixin import DeratingControlMixin
from .ui_control_mixins.charge_discharge_mixin import ChargeDischargeControlMixin


class UiControlMixin(
    CommonControlMixin,
    BmsControlMixin,
    HvControlMixin,
    PcsControlMixin,
    CutoffControlMixin,
    ExecutionMixin,
    DebugControlMixin,
    DeratingControlMixin,
    ChargeDischargeControlMixin,
):
    pass
