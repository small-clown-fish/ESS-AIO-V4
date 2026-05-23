from __future__ import annotations

import sys
from .service import BmsPcsService
from .app_facade import AppFacade
from .controllers import DeviceController, PcsController, ProfileController, StrategyController, AuditController, ServiceActionController
from .strategy_engine import StrategyEngine
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Signal, QObject, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow

from .alarm_parser import AlarmParser
from .hv_controller import HvWorkflowWorker
from .recorder import AlarmRecorder, CsvRecorder
from .ui_control import UiControlMixin
from .ui_data import UiDataMixin
from .ui_device import UiDeviceMixin
from .ui_layout import UiLayoutMixin
from .worker import DeviceWorker, HeartbeatWorker, PcsPollingWorker
from .fleet_manager import FleetManager
from .cluster_strategy_runtime import ClusterStrategyWorker
from .models import Site, Cluster, Device
from .drivers import DEFAULT_BMS_DRIVER, DEFAULT_PCS_DRIVER
from .scheduler import TaskStatusStore
from .version import APP_TITLE, APP_VERSION
from .release_manager import ensure_profile
from .template_manager import TemplateManager
from .paths import resource_path, user_data_dir



class UiBridge(QObject):
    data_received = Signal(str, dict)
    error_received = Signal(str, str)
    task_status_received = Signal(str, dict)
    pcs_data_received = Signal(str, dict)
    pcs_error_received = Signal(str, str)
    heartbeat_written = Signal(str, int)
    heartbeat_error = Signal(str, str)


class MainWindow(
    UiLayoutMixin,
    UiDeviceMixin,
    UiDataMixin,
    UiControlMixin,
    QMainWindow,
):
    DETAIL_FIELDS = [
        ("bms_heartbeat", "BMS Heartbeat"),
        ("bms_power_on", "BMS Power On"),
        ("bms_status", "BMS Status"),
        ("number_of_racks", "Number of Racks"),
        ("system_voltage", "System Voltage (V)"),
        ("system_current", "System Current (A)"),
        ("soc", "SOC (%)"),
        ("soh", "SOH (%)"),
        ("max_cell_voltage", "Max Cell Voltage (mV)"),
        ("min_cell_voltage", "Min Cell Voltage (mV)"),
        ("avg_cell_voltage", "Avg Cell Voltage (mV)"),
        ("max_cell_temperature", "Max Cell Temp (°C)"),
        ("min_cell_temperature", "Min Cell Temp (°C)"),
        ("avg_cell_temperature", "Avg Cell Temp (°C)"),
        ("max_charge_current_allowed", "Max Charge Current Allowed (A)"),
        ("max_discharge_current_allowed", "Max Discharge Current Allowed (A)"),
        ("max_charge_power_allowed", "Max Charge Power Allowed (kW)"),
        ("max_discharge_power_allowed", "Max Discharge Power Allowed (kW)"),
        ("system_power", "System Power (kW)"),
    ]

    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle(APP_TITLE)
        self.resize(1280, 860)

        font = self.font()
        font.setPointSize(16)
        self.setFont(font)

        self.bridge = UiBridge()
        self.bridge.data_received.connect(self.on_data_received)
        self.bridge.error_received.connect(self.on_error_received)
        self.bridge.task_status_received.connect(self.on_task_status_received)
        self.bridge.pcs_data_received.connect(self.on_pcs_data_received)
        self.bridge.pcs_error_received.connect(self.on_pcs_error_received)
        self.bridge.heartbeat_written.connect(self.on_heartbeat_written)
        self.bridge.heartbeat_error.connect(self.on_heartbeat_error)

        self.device_workers: Dict[str, DeviceWorker] = {}
        self.pcs_workers: Dict[str, PcsPollingWorker] = {}
        self.task_status_store = TaskStatusStore()
        self.task_status_rows: Dict[str, int] = {}
        self.worker_start_stagger_seconds: float = 0.25
        self.ui_refresh_interval: float = 1.0
        self._last_ui_refresh_time: Dict[str, float] = {}
        self.heartbeat_workers: Dict[str, HeartbeatWorker] = {}
        self.hv_workers: Dict[str, HvWorkflowWorker] = {}
        self.charge_discharge_workers: Dict[str, Any] = {}
        self.cluster_strategy_workers: Dict[str, ClusterStrategyWorker] = {}
        # CSV recorders are created only when the operator explicitly starts recording.
        # Polling/connection itself does NOT write CSV, which avoids Windows UI/disk lag.
        self.recorders: Dict[str, CsvRecorder] = {}
        self.pcs_recorders: Dict[str, CsvRecorder] = {}
        self.alarm_recorders: Dict[str, AlarmRecorder] = {}
        self.bms_csv_recording_devices: set[str] = set()
        self.pcs_csv_recording_devices: set[str] = set()
        self.service = BmsPcsService()
        self.device_controller = DeviceController(self)
        self.pcs_controller = PcsController(self)
        self.profile_controller = ProfileController(self)
        self.strategy_controller = StrategyController(self)
        self.audit_controller = AuditController(self)
        self.service_action_controller = ServiceActionController(self)
        self.app_facade = AppFacade(self)
        self.fleet_manager = FleetManager(log=self.log, status_callback=lambda dn, status: self.bridge.task_status_received.emit(dn, status))
        self.fleet_status_timer = QTimer(self)
        self.fleet_status_timer.setInterval(1000)
        self.fleet_status_timer.timeout.connect(self.refresh_fleet_heartbeat_status)
        self.fleet_status_timer.start()

        self.device_rows: Dict[str, int] = {}
        self.devices: List[Dict[str, Any]] = []
        # Keep user/project data outside the installation folder. This is important
        # for Windows/PyInstaller builds where Program Files/_MEIPASS may be read-only.
        self.profile_root = user_data_dir() / "profiles"
        self.current_profile_name: str = "default"
        self.current_profile_dir: Path = self.profile_root / self.current_profile_name
        self.current_profile_dir.mkdir(parents=True, exist_ok=True)
        self.startup_self_check_result = ensure_profile(self.current_profile_dir, resource_path("."))
        self.strategy_engine = StrategyEngine(self.current_profile_dir)
        self.template_manager = TemplateManager(self)
        self.fake_mode: bool = False
        self.bms_driver_key: str = DEFAULT_BMS_DRIVER
        self.pcs_driver_key: str = DEFAULT_PCS_DRIVER
        self.alarm_parser = AlarmParser(self.current_profile_dir / "alarm_map.json")
        self.pcs_configs: Dict[str, Dict[str, Any]] = {}
        self.current_pcs_name: str = ""
        self.latest_snapshots: Dict[str, Dict[str, Any]] = {}
        self.latest_pcs_snapshots: Dict[str, Dict[str, Any]] = {}
        self.packet_records = []
        self.debug_session: Dict[str, Any] = {"name": "Default Session", "started_at": "-", "ended_at": "-", "notes": ""}
        self.bms_last_heartbeat: Dict[str, int] = {}
        self.bms_heartbeat_same_count: Dict[str, int] = {}
        self.history_rows: list[dict[str, str]] = []
        self.history_csv_path: str = ""

        self.recent_buffers: Dict[str, deque] = defaultdict(lambda: deque(maxlen=300))
        self.series_buffers: Dict[str, Dict[str, deque]] = defaultdict(
            lambda: {
                "soc": deque(maxlen=300),
                "system_voltage": deque(maxlen=300),
                "system_current": deque(maxlen=300),
                "online": deque(maxlen=300),
            }
        )
        # v3.0 phase 3: dynamic point histories for driver-driven plotting.
        self.dynamic_point_buffers: Dict[str, Dict[str, deque]] = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=300))
        )
        self.selected_dynamic_points: list[str] = []
        # v3.7: CAN decoded signal histories share the curve system, but keep
        # a separate buffer so imported CAN logs do not pollute live BMS points.
        self.can_signal_buffers: Dict[str, deque] = defaultdict(lambda: deque(maxlen=20000))
        self.selected_can_signals: list[str] = []
        self.favorite_points: set[str] = set()
        self.sample_index: Dict[str, int] = defaultdict(int)

        self.current_curve_device: Optional[str] = None
        self.current_detail_device: Optional[str] = None
        self.current_alarm_device: Optional[str] = None
        self.current_control_device: Optional[str] = None

        self.site = Site(name="Default Site")
        self.default_cluster = Cluster(name="Cluster-1")
        self.site.clusters.append(self.default_cluster)

        self.pcs_config: Dict[str, Any] = self.load_pcs_config() or {}
        self.pcs_config.setdefault("driver", self.pcs_driver_key)
        # Do not create/bind a default PCS at startup. A site may be used for
        # BMS-only commissioning; PCS is added and connected manually by operator.
        if self.pcs_config.get("enabled") and self.pcs_config.get("name"):
            # Load PCS device instance so it is visible in the PCS Devices page,
            # but do NOT bind it to the default cluster and do NOT connect it.
            # BMS-only commissioning must never trigger PCS network traffic.
            self.current_pcs_name = str(self.pcs_config.get("name"))
            self.pcs_configs[self.current_pcs_name] = self.pcs_config


        self.last_error_message: str = "-"
        self.last_hv_status: str = "Idle"
        self.last_heartbeat_status: str = "Stopped"
        self.last_sampling_status: str = "Stopped"
        self.operation_log_file = None
        self.cutoff_alarm_states: Dict[str, Dict[str, bool]] = {}

        self.heartbeat_interval: float = 1.0
        self.hv_step_timeout: float = 30.0
        self.hv_poll_interval: float = 1.0
        self.pcs_zero_power_threshold: float = 0.1
        self.charge_cutoff_max_cell_voltage: float = 3650.0
        self.discharge_cutoff_min_cell_voltage: float = 2500.0

        self.power_derating_enabled: bool = False
        self.derating_margin_mv: float = 50.0
        self.derating_power_kw: float = 10.0
        self.derating_state: Dict[str, Dict[str, Any]] = {}
        self.last_user_power_kw: Dict[str, float] = {}

        self.power_tracking_enabled: bool = True
        self.power_tracking_tolerance_kw: float = 5.0
        self.power_tracking_confirm_count: int = 3
        self.power_tracking_counters: Dict[str, int] = {}

        self.power_tracking_auto_retry: bool = False
        self.power_tracking_retry_interval: int = 5  # 秒
        self.power_tracking_max_retry: int = 3

        self.power_tracking_retry_state: Dict[str, Dict[str, Any]] = {}

        self.pcs_fault_protection_enabled: bool = True
        self.pcs_fault_protection_mode: str = "Alarm Only"
        self.pcs_fault_confirm_count: int = 3
        self.pcs_control_ui_enabled: bool = True
        self.pcs_fault_counters: Dict[str, int] = {}

        self.cutoff_mode: str = "Alarm Only"
        self.cutoff_action_latched: Dict[str, Dict[str, bool]] = {}

        self.cutoff_trigger_confirm_count: int = 3
        self.cutoff_recover_confirm_count: int = 3
        self.cutoff_counters: Dict[str, Dict[str, int]] = {}
        self.alarm_history_window_before_minutes: int = 5
        self.alarm_history_window_after_minutes: int = 5
        self.load_runtime_config()

        self.detail_value_labels: Dict[str, QLabel] = {}
        self.pcs_status_labels: Dict[str, QLabel] = {}

        self._build_ui()
        self._build_menu()
        self._apply_comfortable_style()

        self.auto_load_startup_configs()
        try:
            self.log(f"[INFO] User data dir: {user_data_dir()}")
            self.log(f"[INFO] Active profile dir: {self.current_profile_dir}")
            self.log(f"[INFO] Site config path: {self.get_profile_path('site_config.json')}")
        except Exception:
            pass

        self.refresh_global_status_bar()
        try:
            self.refresh_template_package_view()
        except Exception:
            pass
        if hasattr(self, "refresh_release_view"):
            self.refresh_release_view()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.stop_all()
        super().closeEvent(event)


def run() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
