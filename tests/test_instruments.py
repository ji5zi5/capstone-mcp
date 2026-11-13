# Copyright 2026 Capstone MCP contributors.
"""Unit contract tests for the unified manage_instrument seam and InstrumentManager."""

from unittest.mock import MagicMock

import pytest

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.instruments import (
    CalibrateSensorRequest,
    CalibrateSensorResult,
    ConditionSpec,
    ConnectWirelessSensorRequest,
    ConnectWirelessSensorResult,
    InstrumentAction,
    InstrumentManager,
    InstrumentRequest,
    KeepSampleRequest,
    KeepSampleResult,
    SamplingRateRequest,
    SamplingRateSelection,
    ScanWirelessSensorsRequest,
    ScanWirelessSensorsResult,
    SensorSelection,
    SetRecordingConditionRequest,
    SetRecordingConditionResult,
    SetSamplingModeRequest,
    SetSamplingModeResult,
    SetSignalGeneratorRequest,
    SetSignalGeneratorResult,
    SignalGeneratorStatusResult,
    WirelessSensorInfo,
    ZeroSensorRequest,
    ZeroSensorResult,
    manage_instrument,
)


@pytest.fixture
def mock_app() -> Capstone:
    return MagicMock(spec=Capstone)


# ---------------------------------------------------------------------------
# 1. Contract Tests for All 9 InstrumentAction Variants
# ---------------------------------------------------------------------------


def test_manage_instrument_set_sampling_rate(
    mock_app: Capstone,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_result = SamplingRateSelection(
        sensor="Force Sensor",
        requested_rate="100 Hz",
        before="10 Hz",
        after="100 Hz",
        changed=True,
        inputs_delivered=3,
    )
    monkeypatch.setattr(
        "capstone_mcp.instruments.manager.target_sampling_rate",
        MagicMock(return_value=expected_result),
    )

    req = InstrumentRequest(
        action=InstrumentAction.SET_SAMPLING_RATE,
        set_sampling_rate=SamplingRateRequest(
            sensor="Force Sensor",
            target="100 Hz",
        ),
    )
    res = manage_instrument(mock_app, req)

    assert res.action == InstrumentAction.SET_SAMPLING_RATE
    assert res.set_sampling_rate == expected_result
    assert res.sampling_rate == expected_result  # Computed property alias


def test_manage_instrument_select_sensor_fallback(
    mock_app: Capstone,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_result = SensorSelection(
        requested_sensor="Motion Sensor",
        before_sensor="Force Sensor",
        after_sensor="Motion Sensor",
        before_sampling_rate="10 Hz",
        after_sampling_rate="20 Hz",
        changed=True,
    )
    monkeypatch.setattr(
        "capstone_mcp.instruments.manager.select_sensor",
        MagicMock(return_value=expected_result),
    )

    req = InstrumentRequest(
        action=InstrumentAction.SET_SAMPLING_RATE,
        set_sampling_rate=SamplingRateRequest(
            sensor="Motion Sensor",
            target="",  # Empty target triggers sensor selection only
        ),
    )
    res = manage_instrument(mock_app, req)

    assert res.action == InstrumentAction.SET_SAMPLING_RATE
    assert res.set_sampling_rate == expected_result
    assert res.sampling_rate == expected_result


def test_manage_instrument_zero_sensor(
    mock_app: Capstone,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_result = ZeroSensorResult(
        zeroed_sensors=["Force Sensor"],
        verified=True,
        detail="Zero/Tare executed for 1 sensor(s): Force Sensor.",
    )
    monkeypatch.setattr(
        "capstone_mcp.instruments.manager.zero_sensor",
        MagicMock(return_value=expected_result),
    )

    req = InstrumentRequest(
        action=InstrumentAction.ZERO_SENSOR,
        zero_sensor=ZeroSensorRequest(sensor_name="Force Sensor"),
    )
    res = manage_instrument(mock_app, req)

    assert res.action == InstrumentAction.ZERO_SENSOR
    assert res.zero_sensor == expected_result


def test_manage_instrument_configure_signal_generator_set(
    mock_app: Capstone,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_result = SetSignalGeneratorResult(
        generator_name="Output 1",
        waveform="Sine",
        frequency=500.0,
        amplitude=2.5,
        enabled=True,
        verified=True,
        detail="Signal Generator configured.",
    )
    monkeypatch.setattr(
        "capstone_mcp.instruments.manager.set_signal_generator",
        MagicMock(return_value=expected_result),
    )

    req = InstrumentRequest(
        action=InstrumentAction.CONFIGURE_SIGNAL_GENERATOR,
        configure_signal_generator=SetSignalGeneratorRequest(
            waveform="Sine",
            frequency=500.0,
            amplitude=2.5,
            enabled=True,
        ),
    )
    res = manage_instrument(mock_app, req)

    assert res.action == InstrumentAction.CONFIGURE_SIGNAL_GENERATOR
    assert res.configure_signal_generator == expected_result
    assert res.signal_generator == expected_result


def test_manage_instrument_configure_signal_generator_read_only(
    mock_app: Capstone,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_result = SignalGeneratorStatusResult(
        generator_name="Output 1",
        enabled=True,
        waveform="Square",
        frequency=1000.0,
        amplitude=1.0,
        verified=True,
        detail="Signal Generator status read.",
    )
    monkeypatch.setattr(
        "capstone_mcp.instruments.manager.read_signal_generator_status",
        MagicMock(return_value=expected_result),
    )

    req = InstrumentRequest(
        action=InstrumentAction.CONFIGURE_SIGNAL_GENERATOR,
        configure_signal_generator=SetSignalGeneratorRequest(read_only=True),
    )
    res = manage_instrument(mock_app, req)

    assert res.action == InstrumentAction.CONFIGURE_SIGNAL_GENERATOR
    assert res.configure_signal_generator == expected_result
    assert res.signal_generator == expected_result


def test_manage_instrument_set_recording_condition(
    mock_app: Capstone,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cond = ConditionSpec(
        condition_type="sensor_threshold",
        measurement="Force",
        operator="above",
        threshold=5.0,
    )
    expected_result = SetRecordingConditionResult(
        start_condition=cond,
        stop_condition=None,
        verified=True,
        detail="Recording conditions applied.",
    )
    monkeypatch.setattr(
        "capstone_mcp.instruments.manager.set_recording_condition",
        MagicMock(return_value=expected_result),
    )

    req = InstrumentRequest(
        action=InstrumentAction.SET_RECORDING_CONDITION,
        set_recording_condition=SetRecordingConditionRequest(start_condition=cond),
    )
    res = manage_instrument(mock_app, req)

    assert res.action == InstrumentAction.SET_RECORDING_CONDITION
    assert res.set_recording_condition == expected_result
    assert res.recording_condition == expected_result


def test_manage_instrument_set_sampling_mode(
    mock_app: Capstone,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_result = SetSamplingModeResult(
        mode="keep_sample",
        previous_mode="continuous",
        verified=True,
        detail="Sampling mode switched.",
    )
    monkeypatch.setattr(
        "capstone_mcp.instruments.manager.set_sampling_mode",
        MagicMock(return_value=expected_result),
    )

    req = InstrumentRequest(
        action=InstrumentAction.SET_SAMPLING_MODE,
        set_sampling_mode=SetSamplingModeRequest(mode="keep_sample"),
    )
    res = manage_instrument(mock_app, req)

    assert res.action == InstrumentAction.SET_SAMPLING_MODE
    assert res.set_sampling_mode == expected_result
    assert res.sampling_mode == expected_result


def test_manage_instrument_keep_sample(
    mock_app: Capstone,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_result = KeepSampleResult(
        recorded_value=0.05,
        variable_name="Mass (kg)",
        sample_retained=True,
        verified=True,
        detail="Sample point recorded.",
    )
    monkeypatch.setattr(
        "capstone_mcp.instruments.manager.keep_sample",
        MagicMock(return_value=expected_result),
    )

    req = InstrumentRequest(
        action=InstrumentAction.KEEP_SAMPLE,
        keep_sample=KeepSampleRequest(value=0.05, variable_name="Mass (kg)"),
    )
    res = manage_instrument(mock_app, req)

    assert res.action == InstrumentAction.KEEP_SAMPLE
    assert res.keep_sample == expected_result


def test_manage_instrument_scan_wireless(
    mock_app: Capstone,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sensor_info = WirelessSensorInfo(
        sensor_id="123-456",
        name="Wireless Force Sensor 123-456",
        connected=False,
        battery_percent=90,
    )
    expected_result = ScanWirelessSensorsResult(
        sensors=[sensor_info],
        count=1,
        verified=True,
        detail="Found 1 wireless sensor(s).",
    )
    monkeypatch.setattr(
        "capstone_mcp.instruments.manager.scan_wireless_sensors",
        MagicMock(return_value=expected_result),
    )

    req = InstrumentRequest(
        action=InstrumentAction.SCAN_WIRELESS,
        scan_wireless=ScanWirelessSensorsRequest(timeout_seconds=3.0),
    )
    res = manage_instrument(mock_app, req)

    assert res.action == InstrumentAction.SCAN_WIRELESS
    assert res.scan_wireless == expected_result


def test_manage_instrument_connect_wireless(
    mock_app: Capstone,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_result = ConnectWirelessSensorResult(
        sensor_id="123-456",
        name="Wireless Force Sensor 123-456",
        connected=True,
        verified=True,
        detail="Connected wireless sensor.",
    )
    monkeypatch.setattr(
        "capstone_mcp.instruments.manager.connect_wireless_sensor",
        MagicMock(return_value=expected_result),
    )

    req = InstrumentRequest(
        action=InstrumentAction.CONNECT_WIRELESS,
        connect_wireless=ConnectWirelessSensorRequest(sensor_id="123-456"),
    )
    res = manage_instrument(mock_app, req)

    assert res.action == InstrumentAction.CONNECT_WIRELESS
    assert res.connect_wireless == expected_result


def test_manage_instrument_calibrate_sensor(
    mock_app: Capstone,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_result = CalibrateSensorResult(
        sensor_name="Force Sensor",
        measurement_type="Force",
        calibration_type="two_point",
        standard_1=0.0,
        standard_2=9.8,
        verified=True,
        detail="Sensor calibrated.",
    )
    monkeypatch.setattr(
        "capstone_mcp.instruments.manager.calibrate_sensor",
        MagicMock(return_value=expected_result),
    )

    req = InstrumentRequest(
        action=InstrumentAction.CALIBRATE_SENSOR,
        calibrate_sensor=CalibrateSensorRequest(
            sensor_name="Force Sensor",
            measurement_type="Force",
            calibration_type="two_point",
            standard_1=0.0,
            standard_2=9.8,
        ),
    )
    res = manage_instrument(mock_app, req)

    assert res.action == InstrumentAction.CALIBRATE_SENSOR
    assert res.calibrate_sensor == expected_result


# ---------------------------------------------------------------------------
# 2. Error Handling & Validation Tests
# ---------------------------------------------------------------------------


def test_manage_instrument_missing_payload_raises(mock_app: Capstone) -> None:
    actions_and_names = [
        (InstrumentAction.SET_SAMPLING_RATE, "set_sampling_rate"),
        (InstrumentAction.ZERO_SENSOR, "zero_sensor"),
        (InstrumentAction.CONFIGURE_SIGNAL_GENERATOR, "configure_signal_generator"),
        (InstrumentAction.SET_RECORDING_CONDITION, "set_recording_condition"),
        (InstrumentAction.SET_SAMPLING_MODE, "set_sampling_mode"),
        (InstrumentAction.KEEP_SAMPLE, "keep_sample"),
        (InstrumentAction.SCAN_WIRELESS, "scan_wireless"),
        (InstrumentAction.CONNECT_WIRELESS, "connect_wireless"),
        (InstrumentAction.CALIBRATE_SENSOR, "calibrate_sensor"),
    ]

    for action, _field_name in actions_and_names:
        req = InstrumentRequest(action=action)
        with pytest.raises(AutomationError, match=f"{action} request must be provided"):
            manage_instrument(mock_app, req)


def test_manage_instrument_unsupported_action(mock_app: Capstone) -> None:
    mgr = InstrumentManager(mock_app)
    req = InstrumentRequest(
        action=InstrumentAction.SET_SAMPLING_RATE,
        set_sampling_rate=SamplingRateRequest(sensor="Test"),
    )
    object.__setattr__(req, "action", "unsupported_action")
    with pytest.raises(AutomationError, match="Unsupported InstrumentAction"):
        mgr.manage(req)


# ---------------------------------------------------------------------------
# 3. Request Payload Normalization Tests
# ---------------------------------------------------------------------------


def test_instrument_request_alias_normalization() -> None:
    data = {
        "action": "set_sampling_rate",
        "sampling_rate": {"sensor": "Force Sensor", "target": "100 Hz"},
    }
    req = InstrumentRequest.model_validate(data)
    assert req.set_sampling_rate is not None
    assert req.set_sampling_rate.sensor == "Force Sensor"
    assert req.set_sampling_rate.target == "100 Hz"

    data_gen = {
        "action": "configure_signal_generator",
        "signal_generator": {"waveform": "Square", "frequency": 200.0},
    }
    req_gen = InstrumentRequest.model_validate(data_gen)
    assert req_gen.configure_signal_generator is not None
    assert req_gen.configure_signal_generator.waveform == "Square"
    assert req_gen.configure_signal_generator.frequency == 200.0
