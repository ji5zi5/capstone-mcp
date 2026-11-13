# Copyright 2026 Capstone MCP contributors.
"""Unified Instrument Manager engine and functional manage_instrument seam."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.instruments.generator import (
    read_signal_generator_status,
    set_signal_generator,
)
from capstone_mcp.instruments.models import (
    CalibrateSensorRequest,
    CalibrateSensorResult,
    ConnectWirelessSensorRequest,
    ConnectWirelessSensorResult,
    InstrumentAction,
    InstrumentRequest,
    InstrumentResult,
    KeepSampleRequest,
    KeepSampleResult,
    ReadSignalGeneratorStatusRequest,
    SamplingRateRequest,
    SamplingRateSelection,
    ScanWirelessSensorsRequest,
    ScanWirelessSensorsResult,
    SensorSelection,
    SensorSelectionRequest,
    SetRecordingConditionRequest,
    SetRecordingConditionResult,
    SetSamplingModeRequest,
    SetSamplingModeResult,
    SetSignalGeneratorRequest,
    SetSignalGeneratorResult,
    SignalGeneratorStatusResult,
    ZeroSensorRequest,
    ZeroSensorResult,
)
from capstone_mcp.instruments.sensors import (
    select_sensor,
    target_sampling_rate,
    zero_sensor,
)
from capstone_mcp.instruments.triggers import (
    keep_sample,
    set_recording_condition,
    set_sampling_mode,
)
from capstone_mcp.instruments.wireless import (
    calibrate_sensor,
    connect_wireless_sensor,
    scan_wireless_sensors,
)

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# InstrumentManager Engine
# ---------------------------------------------------------------------------


class InstrumentManager:
    """Central engine managing Capstone sensors, instruments, and hardware."""

    def __init__(self, app: Capstone) -> None:
        """Initialize InstrumentManager with Capstone desktop instance."""
        self.app = app

    # -----------------------------------------------------------------------
    # Direct Action Operations
    # -----------------------------------------------------------------------

    def set_sampling_rate(
        self, request: SamplingRateRequest,
    ) -> SamplingRateSelection | SensorSelection:
        """Select sensor or navigate to target sampling rate."""
        if request.target:
            return target_sampling_rate(self.app, request.handle, request)
        return select_sensor(
            self.app,
            request.handle,
            SensorSelectionRequest(
                sensor=request.sensor,
                allow_foreground=request.allow_foreground,
            ),
        )

    def zero_sensor(self, request: ZeroSensorRequest) -> ZeroSensorResult:
        """Execute zero/tare for specified sensor or all zeroable sensors."""
        return zero_sensor(self.app, request)

    def configure_signal_generator(
        self, request: SetSignalGeneratorRequest,
    ) -> SetSignalGeneratorResult | SignalGeneratorStatusResult:
        """Configure signal generator parameters or read current status."""
        if request.read_only:
            return read_signal_generator_status(
                self.app,
                ReadSignalGeneratorStatusRequest(
                    generator_name=request.generator_name,
                    handle=request.handle,
                    allow_foreground=request.allow_foreground,
                    keep_open=request.keep_open,
                ),
            )
        return set_signal_generator(self.app, request)

    def set_recording_condition(
        self, request: SetRecordingConditionRequest,
    ) -> SetRecordingConditionResult:
        """Configure start/stop recording trigger conditions."""
        return set_recording_condition(self.app, request)

    def set_sampling_mode(
        self, request: SetSamplingModeRequest,
    ) -> SetSamplingModeResult:
        """Switch Capstone sampling mode (continuous, keep_sample, fast_monitor)."""
        return set_sampling_mode(self.app, request)

    def keep_sample(self, request: KeepSampleRequest) -> KeepSampleResult:
        """Record a discrete manual sampling data point."""
        return keep_sample(self.app, request)

    def scan_wireless(
        self, request: ScanWirelessSensorsRequest,
    ) -> ScanWirelessSensorsResult:
        """Scan and discover Bluetooth wireless sensors."""
        return scan_wireless_sensors(self.app, request)

    def connect_wireless(
        self, request: ConnectWirelessSensorRequest,
    ) -> ConnectWirelessSensorResult:
        """Pair and connect a discovered wireless sensor."""
        return connect_wireless_sensor(self.app, request)

    def calibrate_sensor(
        self, request: CalibrateSensorRequest,
    ) -> CalibrateSensorResult:
        """Automate multi-point sensor calibration wizard."""
        return calibrate_sensor(self.app, request)

    # -----------------------------------------------------------------------
    # Unified Action Dispatchers
    # -----------------------------------------------------------------------

    def _manage_set_sampling_rate(self, request: InstrumentRequest) -> InstrumentResult:
        if request.set_sampling_rate is None:
            msg = (
                "set_sampling_rate request must be provided for "
                "SET_SAMPLING_RATE action."
            )
            raise AutomationError(msg)
        return InstrumentResult(
            action=request.action,
            set_sampling_rate=self.set_sampling_rate(request.set_sampling_rate),
        )

    def _manage_zero_sensor(self, request: InstrumentRequest) -> InstrumentResult:
        if request.zero_sensor is None:
            msg = "zero_sensor request must be provided for ZERO_SENSOR action."
            raise AutomationError(msg)
        return InstrumentResult(
            action=request.action,
            zero_sensor=self.zero_sensor(request.zero_sensor),
        )

    def _manage_configure_signal_generator(
        self, request: InstrumentRequest,
    ) -> InstrumentResult:
        if request.configure_signal_generator is None:
            msg = (
                "configure_signal_generator request must be provided for "
                "CONFIGURE_SIGNAL_GENERATOR action."
            )
            raise AutomationError(msg)
        return InstrumentResult(
            action=request.action,
            configure_signal_generator=self.configure_signal_generator(
                request.configure_signal_generator,
            ),
        )

    def _manage_set_recording_condition(
        self, request: InstrumentRequest,
    ) -> InstrumentResult:
        if request.set_recording_condition is None:
            msg = (
                "set_recording_condition request must be provided for "
                "SET_RECORDING_CONDITION action."
            )
            raise AutomationError(msg)
        return InstrumentResult(
            action=request.action,
            set_recording_condition=self.set_recording_condition(
                request.set_recording_condition,
            ),
        )

    def _manage_set_sampling_mode(
        self, request: InstrumentRequest,
    ) -> InstrumentResult:
        if request.set_sampling_mode is None:
            msg = (
                "set_sampling_mode request must be provided for "
                "SET_SAMPLING_MODE action."
            )
            raise AutomationError(msg)
        return InstrumentResult(
            action=request.action,
            set_sampling_mode=self.set_sampling_mode(request.set_sampling_mode),
        )

    def _manage_keep_sample(self, request: InstrumentRequest) -> InstrumentResult:
        if request.keep_sample is None:
            msg = "keep_sample request must be provided for KEEP_SAMPLE action."
            raise AutomationError(msg)
        return InstrumentResult(
            action=request.action,
            keep_sample=self.keep_sample(request.keep_sample),
        )

    def _manage_scan_wireless(self, request: InstrumentRequest) -> InstrumentResult:
        if request.scan_wireless is None:
            msg = "scan_wireless request must be provided for SCAN_WIRELESS action."
            raise AutomationError(msg)
        return InstrumentResult(
            action=request.action,
            scan_wireless=self.scan_wireless(request.scan_wireless),
        )

    def _manage_connect_wireless(self, request: InstrumentRequest) -> InstrumentResult:
        if request.connect_wireless is None:
            msg = (
                "connect_wireless request must be provided for "
                "CONNECT_WIRELESS action."
            )
            raise AutomationError(msg)
        return InstrumentResult(
            action=request.action,
            connect_wireless=self.connect_wireless(request.connect_wireless),
        )

    def _manage_calibrate_sensor(self, request: InstrumentRequest) -> InstrumentResult:
        if request.calibrate_sensor is None:
            msg = (
                "calibrate_sensor request must be provided for "
                "CALIBRATE_SENSOR action."
            )
            raise AutomationError(msg)
        return InstrumentResult(
            action=request.action,
            calibrate_sensor=self.calibrate_sensor(request.calibrate_sensor),
        )

    def manage(self, request: InstrumentRequest) -> InstrumentResult:
        """Unified dispatch method for all instrument actions."""
        dispatchers: dict[
            InstrumentAction,
            Callable[[InstrumentRequest], InstrumentResult],
        ] = {
            InstrumentAction.SET_SAMPLING_RATE: self._manage_set_sampling_rate,
            InstrumentAction.ZERO_SENSOR: self._manage_zero_sensor,
            InstrumentAction.CONFIGURE_SIGNAL_GENERATOR: (
                self._manage_configure_signal_generator
            ),
            InstrumentAction.SET_RECORDING_CONDITION: (
                self._manage_set_recording_condition
            ),
            InstrumentAction.SET_SAMPLING_MODE: self._manage_set_sampling_mode,
            InstrumentAction.KEEP_SAMPLE: self._manage_keep_sample,
            InstrumentAction.SCAN_WIRELESS: self._manage_scan_wireless,
            InstrumentAction.CONNECT_WIRELESS: self._manage_connect_wireless,
            InstrumentAction.CALIBRATE_SENSOR: self._manage_calibrate_sensor,
        }
        handler = dispatchers.get(request.action)
        if handler is None:
            msg = f"Unsupported InstrumentAction: {request.action}"
            raise AutomationError(msg)
        return handler(request)


def manage_instrument(app: Capstone, request: InstrumentRequest) -> InstrumentResult:
    """Functional convenience wrapper for the unified instrument management seam."""
    return InstrumentManager(app).manage(request)
