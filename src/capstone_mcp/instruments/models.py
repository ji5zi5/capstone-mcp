# Copyright 2026 Capstone MCP contributors.
"""Data models, request schemas, and typed outcomes for Capstone instruments."""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, computed_field, model_validator

from capstone_mcp.models import Model

# ---------------------------------------------------------------------------
# 1. Action Enumeration & Type Aliases
# ---------------------------------------------------------------------------


class InstrumentAction(StrEnum):
    """Supported operations on Capstone hardware and instruments."""

    SET_SAMPLING_RATE = "set_sampling_rate"
    ZERO_SENSOR = "zero_sensor"
    CONFIGURE_SIGNAL_GENERATOR = "configure_signal_generator"
    SET_RECORDING_CONDITION = "set_recording_condition"
    SET_SAMPLING_MODE = "set_sampling_mode"
    KEEP_SAMPLE = "keep_sample"
    SCAN_WIRELESS = "scan_wireless"
    CONNECT_WIRELESS = "connect_wireless"
    CALIBRATE_SENSOR = "calibrate_sensor"


type WaveformType = Literal["Sine", "Square", "Triangle", "Ramp", "DC"]
type ConditionType = Literal["none", "time", "sensor_threshold"]
type ComparisonOperator = Literal["above", "below", "rises_above", "falls_below"]
type SamplingMode = Literal["continuous", "keep_sample", "fast_monitor"]
type CalibrationType = Literal["two_point", "one_point"]


# ---------------------------------------------------------------------------
# 2. Sensor Selection & Sampling Rate Models
# ---------------------------------------------------------------------------


class SensorSelectionRequest(Model):
    """An exact observed sensor name and input-delivery policy."""

    sensor: str
    allow_foreground: bool = True


class SamplingRateRequest(Model):
    """A numeric rate and explicit display unit with a bounded step search."""

    sensor: str
    target: str = ""
    step_limit: int = Field(default=128, ge=1, le=512)
    handle: int = 0
    allow_foreground: bool = True


class SensorSelection(Model):
    """Observed sensor and native rate displays before and after selection."""

    requested_sensor: str
    before_sensor: str
    after_sensor: str
    before_sampling_rate: str
    after_sampling_rate: str
    changed: bool


class SamplingRateSelection(Model):
    """Observed native rate displays before and after bounded traversal."""

    sensor: str
    requested_rate: str
    before: str
    after: str
    changed: bool
    inputs_delivered: int


class SensorConfiguration(Model):
    """Confirmed sensor selection and the resulting supported sampling rate."""

    selection: SensorSelection
    rate: SamplingRateSelection


class _Settings(Model):
    """One fresh stopped-state observation of the native controls."""

    sensor: str
    sampling_rate: str


class _RateControls(Model):
    """Fresh rate label and step-control references from one snapshot."""

    display: str
    increase_ref: str
    increase_enabled: bool
    decrease_ref: str
    decrease_enabled: bool


# ---------------------------------------------------------------------------
# 3. Sensor Zero / Tare Models
# ---------------------------------------------------------------------------


class ZeroSensorRequest(Model):
    """Specification of target sensor to zero/tare."""

    sensor_name: str | None = None
    handle: int = 0
    allow_foreground: bool = True


class ZeroSensorResult(Model):
    """Outcome of sensor zeroing operation."""

    zeroed_sensors: list[str]
    verified: bool
    detail: str


# ---------------------------------------------------------------------------
# 4. Signal Generator Models
# ---------------------------------------------------------------------------

SIGNAL_GENERATOR_TOGGLE_SUFFIX: Final = ".ObjNameSignalGenerator"
SIGNAL_GENERATOR_NAME: Final = "Signal Generator"
DEFAULT_GENERATOR_NAME: Final = "Output 1"

VALID_WAVEFORMS: Final = {
    "sine": "Sine",
    "square": "Square",
    "triangle": "Triangle",
    "ramp": "Ramp",
    "dc": "DC",
}


class SetSignalGeneratorRequest(Model):
    """Parameters for configuring the Capstone Signal Generator."""

    waveform: str = "Sine"
    frequency: float | None = 1000.0
    amplitude: float | None = 1.0
    enabled: bool = True
    generator_name: str | None = None
    handle: int = 0
    allow_foreground: bool = True
    keep_open: bool = False
    read_only: bool = False


class SetSignalGeneratorResult(Model):
    """Outcome of configuring the Capstone Signal Generator."""

    generator_name: str
    waveform: str
    frequency: float | None
    amplitude: float | None
    enabled: bool
    verified: bool = True
    detail: str = ""


class ReadSignalGeneratorStatusRequest(Model):
    """Request to read the current state of the Capstone Signal Generator."""

    generator_name: str | None = None
    handle: int = 0
    allow_foreground: bool = True
    keep_open: bool = False


class SignalGeneratorStatusResult(Model):
    """Current state of the Capstone Signal Generator."""

    generator_name: str
    enabled: bool
    waveform: str
    frequency: float | None
    amplitude: float | None
    verified: bool = True
    detail: str = ""


# ---------------------------------------------------------------------------
# 5. Smart Triggers & Manual Sampling Models
# ---------------------------------------------------------------------------

RECORDING_CONDITIONS_SUFFIX: Final = ".ObjNameRecordingConditions"
RECORDING_CONDITIONS_NAME: Final = "Recording Conditions"
SAMPLING_MODE_SUFFIX: Final = ".SamplingModeSelector"
KEEP_SAMPLE_SUFFIX: Final = ".KeepSampleButton"


class ConditionSpec(Model):
    """Specification of a start or stop recording condition."""

    condition_type: ConditionType = "none"
    measurement: str | None = None
    operator: ComparisonOperator | None = None
    threshold: float | None = None
    unit: str | None = None


class SetRecordingConditionRequest(Model):
    """Specification for start/stop recording conditions."""

    start_condition: ConditionSpec | None = None
    stop_condition: ConditionSpec | None = None
    handle: int = 0
    allow_foreground: bool = True
    keep_open: bool = False


class SetRecordingConditionResult(Model):
    """Result of setting recording conditions."""

    start_condition: ConditionSpec | None = None
    stop_condition: ConditionSpec | None = None
    verified: bool = True
    detail: str = ""


class SetSamplingModeRequest(Model):
    """Specification for switching sampling mode."""

    mode: SamplingMode = "continuous"
    handle: int = 0
    allow_foreground: bool = True


class SetSamplingModeResult(Model):
    """Result of switching sampling mode."""

    mode: SamplingMode
    previous_mode: str | None = None
    verified: bool = True
    detail: str = ""


class KeepSampleRequest(Model):
    """Specification for taking a manual sample point."""

    value: float | None = None
    variable_name: str | None = None
    handle: int = 0
    allow_foreground: bool = True


class KeepSampleResult(Model):
    """Outcome of keeping a sample point."""

    recorded_value: float | None = None
    variable_name: str | None = None
    sample_retained: bool = True
    verified: bool = True
    detail: str = ""


# ---------------------------------------------------------------------------
# 6. Wireless Sensors & Multi-Point Calibration Models
# ---------------------------------------------------------------------------

HARDWARE_SETUP_TOGGLE_SUFFIX: Final = ".ObjNameHardware"
HARDWARE_SETUP_NAME: Final = "Hardware Setup"
CALIBRATION_TOGGLE_SUFFIX: Final = ".ObjNameCalibration"
CALIBRATION_NAME: Final = "Calibration"

VALID_CALIBRATIONS: Final = {
    "two_point": "two_point",
    "2_point": "two_point",
    "2-point": "two_point",
    "two standards": "two_point",
    "one_point": "one_point",
    "1_point": "one_point",
    "1-point": "one_point",
    "one standard": "one_point",
}


class WirelessSensorInfo(Model):
    """Information about a discovered wireless sensor."""

    sensor_id: str
    name: str
    connected: bool = False
    battery_percent: int | None = None
    signal_strength: str | None = None


class ScanWirelessSensorsRequest(Model):
    """Parameters for scanning wireless Bluetooth sensors."""

    handle: int = 0
    timeout_seconds: float = 5.0
    allow_foreground: bool = True
    keep_open: bool = False


class ScanWirelessSensorsResult(Model):
    """Discovered wireless sensors and summary."""

    sensors: list[WirelessSensorInfo]
    count: int
    verified: bool = True
    detail: str = ""


class ConnectWirelessSensorRequest(Model):
    """Parameters for connecting/pairing a wireless sensor."""

    sensor_id: str
    handle: int = 0
    allow_foreground: bool = True
    keep_open: bool = False


class ConnectWirelessSensorResult(Model):
    """Outcome of wireless sensor connection."""

    sensor_id: str
    name: str
    connected: bool = True
    verified: bool = True
    detail: str = ""


class CalibrateSensorRequest(Model):
    """Parameters for sensor calibration wizard."""

    sensor_name: str
    measurement_type: str | None = None
    calibration_type: str = "two_point"
    standard_1: float = 0.0
    standard_2: float | None = None
    handle: int = 0
    allow_foreground: bool = True
    keep_open: bool = False


class CalibrateSensorResult(Model):
    """Outcome of sensor calibration wizard."""

    sensor_name: str
    measurement_type: str
    calibration_type: str
    standard_1: float
    standard_2: float | None = None
    verified: bool = True
    detail: str = ""


# ---------------------------------------------------------------------------
# 7. Unified Seam Request & Result Models
# ---------------------------------------------------------------------------


class InstrumentRequest(Model):
    """Unified request for all Capstone instrument and hardware operations."""

    action: InstrumentAction
    set_sampling_rate: SamplingRateRequest | None = None
    zero_sensor: ZeroSensorRequest | None = None
    configure_signal_generator: SetSignalGeneratorRequest | None = None
    set_recording_condition: SetRecordingConditionRequest | None = None
    set_sampling_mode: SetSamplingModeRequest | None = None
    keep_sample: KeepSampleRequest | None = None
    scan_wireless: ScanWirelessSensorsRequest | None = None
    connect_wireless: ConnectWirelessSensorRequest | None = None
    calibrate_sensor: CalibrateSensorRequest | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_payload(cls, data: object) -> object:
        if isinstance(data, dict):
            if "sampling_rate" in data and "set_sampling_rate" not in data:
                data["set_sampling_rate"] = data["sampling_rate"]
            if "signal_generator" in data and "configure_signal_generator" not in data:
                data["configure_signal_generator"] = data["signal_generator"]
            if "recording_condition" in data and "set_recording_condition" not in data:
                data["set_recording_condition"] = data["recording_condition"]
            if "sampling_mode" in data and "set_sampling_mode" not in data:
                data["set_sampling_mode"] = data["sampling_mode"]
        return data


class InstrumentResult(Model):
    """Unified result containing the outcome of the requested instrument action."""

    action: InstrumentAction
    set_sampling_rate: SamplingRateSelection | SensorSelection | None = None
    zero_sensor: ZeroSensorResult | None = None
    configure_signal_generator: (
        SetSignalGeneratorResult | SignalGeneratorStatusResult | None
    ) = None
    set_recording_condition: SetRecordingConditionResult | None = None
    set_sampling_mode: SetSamplingModeResult | None = None
    keep_sample: KeepSampleResult | None = None
    scan_wireless: ScanWirelessSensorsResult | None = None
    connect_wireless: ConnectWirelessSensorResult | None = None
    calibrate_sensor: CalibrateSensorResult | None = None

    @computed_field
    @property
    def sampling_rate(self) -> SamplingRateSelection | SensorSelection | None:
        """Backward-compatible sampling rate selection alias."""
        return self.set_sampling_rate

    @computed_field
    @property
    def signal_generator(
        self,
    ) -> SetSignalGeneratorResult | SignalGeneratorStatusResult | None:
        """Backward-compatible signal generator result alias."""
        return self.configure_signal_generator

    @computed_field
    @property
    def recording_condition(self) -> SetRecordingConditionResult | None:
        """Backward-compatible recording condition result alias."""
        return self.set_recording_condition

    @computed_field
    @property
    def sampling_mode(self) -> SetSamplingModeResult | None:
        """Backward-compatible sampling mode result alias."""
        return self.set_sampling_mode
