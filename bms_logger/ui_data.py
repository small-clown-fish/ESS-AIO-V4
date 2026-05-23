from __future__ import annotations

from .ui_mixins.logging_mixin import LoggingMixin
from .ui_mixins.config_mixin import ConfigMixin
from .ui_mixins.status_mixin import StatusMixin
from .ui_mixins.scheduler_mixin import SchedulerMixin
from .ui_mixins.data_receive_mixin import DataReceiveMixin
from .ui_mixins.curves_mixin import CurvesMixin
from .ui_mixins.points_mixin import PointsMixin
from .ui_mixins.details_mixin import DetailsMixin
from .ui_mixins.alarm_mixin import AlarmMixin
from .ui_mixins.site_mixin import SiteMixin
from .ui_mixins.pcs_mixin import PcsConfigMixin
from .ui_mixins.profile_mixin import ProfileMixin
from .ui_mixins.diagnostics_mixin import DiagnosticsMixin
from .ui_mixins.replay_mixin import ReplayMixin
from .ui_mixins.strategy_mixin import StrategyMixin
from .ui_mixins.driver_mixin import DriverConfigMixin
from .ui_mixins.packet_mixin import PacketAnalyzerMixin
from .ui_mixins.report_mixin import ReportMixin
from .ui_mixins.timeline_mixin import TimelineMixin
from .ui_mixins.release_mixin import ReleaseMixin
from .ui_mixins.template_mixin import TemplateMixin


class UiDataMixin(
    LoggingMixin,
    ConfigMixin,
    StatusMixin,
    SchedulerMixin,
    DataReceiveMixin,
    CurvesMixin,
    PointsMixin,
    DetailsMixin,
    AlarmMixin,
    SiteMixin,
    PcsConfigMixin,
    ProfileMixin,
    DiagnosticsMixin,
    ReplayMixin,
    StrategyMixin,
    DriverConfigMixin,
    PacketAnalyzerMixin,
    ReportMixin,
    TimelineMixin,
    ReleaseMixin,
    TemplateMixin,
):
    pass
