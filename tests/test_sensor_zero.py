# Copyright 2026 Capstone MCP contributors.
"""Tests for dedicated sensor zero/tare tool."""

from unittest.mock import MagicMock

import pytest

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.instruments import (
    InstrumentAction,
    InstrumentRequest,
    InstrumentResult,
    ZeroSensorRequest,
    ZeroSensorResult,
    manage_instrument,
)
from capstone_mcp.models import Bounds, Control, Snapshot, Window


def test_zero_sensor_raises_when_no_zero_button_found() -> None:
    app = Capstone()
    mock_window = Window(
        handle=100, title="Capstone", process_id=1,
        bounds=Bounds(left=0, top=0, right=1000, bottom=800),
    )
    app.windows = MagicMock(return_value=[mock_window])
    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_window,
        controls=[
            Control(
                ref="ref:btn", parent=None, name="Record",
                control_type="Button", automation_id="record_btn",
                enabled=True, visible=True,
                bounds=Bounds(left=0, top=0, right=50, bottom=50),
            ),
        ],
        truncated=False,
    ))

    req = InstrumentRequest(
        action=InstrumentAction.ZERO_SENSOR,
        zero_sensor=ZeroSensorRequest(handle=100),
    )
    with pytest.raises(AutomationError, match="No zeroable sensors"):
        _ = manage_instrument(app, req)


def test_zero_sensor_all_sensors_success() -> None:
    app = Capstone()
    mock_window = Window(
        handle=100, title="Capstone", process_id=1,
        bounds=Bounds(left=0, top=0, right=1000, bottom=800),
    )
    app.windows = MagicMock(return_value=[mock_window])

    zero_btn1 = Control(
        ref="ref:zero1", parent=None, name="Zero Force Sensor",
        control_type="Button", automation_id="ForceSensor.ZeroButton",
        enabled=True, visible=True,
        bounds=Bounds(left=100, top=700, right=150, bottom=730),
    )
    zero_btn2 = Control(
        ref="ref:zero2", parent=None, name="Zero Pressure Sensor",
        control_type="Button", automation_id="PressureSensor.ZeroButton",
        enabled=True, visible=True,
        bounds=Bounds(left=200, top=700, right=250, bottom=730),
    )

    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_window,
        controls=[zero_btn1, zero_btn2],
        truncated=False,
    ))
    app.click = MagicMock()

    req = InstrumentRequest(
        action=InstrumentAction.ZERO_SENSOR,
        zero_sensor=ZeroSensorRequest(handle=100, sensor_name=None),
    )
    inst_res = manage_instrument(app, req)

    assert isinstance(inst_res, InstrumentResult)
    assert isinstance(inst_res.zero_sensor, ZeroSensorResult)
    res = inst_res.zero_sensor
    assert len(res.zeroed_sensors) == 2
    assert res.verified is True
    assert app.click.call_count == 2


def test_zero_sensor_specific_sensor_success() -> None:
    app = Capstone()
    mock_window = Window(
        handle=100, title="Capstone", process_id=1,
        bounds=Bounds(left=0, top=0, right=1000, bottom=800),
    )
    app.windows = MagicMock(return_value=[mock_window])

    zero_btn1 = Control(
        ref="ref:zero1", parent=None, name="Zero Force Sensor",
        control_type="Button", automation_id="ForceSensor.ZeroButton",
        enabled=True, visible=True,
        bounds=Bounds(left=100, top=700, right=150, bottom=730),
    )
    zero_btn2 = Control(
        ref="ref:zero2", parent=None, name="Zero Pressure Sensor",
        control_type="Button", automation_id="PressureSensor.ZeroButton",
        enabled=True, visible=True,
        bounds=Bounds(left=200, top=700, right=250, bottom=730),
    )

    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_window,
        controls=[zero_btn1, zero_btn2],
        truncated=False,
    ))
    app.click = MagicMock()

    req = InstrumentRequest(
        action=InstrumentAction.ZERO_SENSOR,
        zero_sensor=ZeroSensorRequest(handle=100, sensor_name="Force Sensor"),
    )
    inst_res = manage_instrument(app, req)

    assert isinstance(inst_res, InstrumentResult)
    assert isinstance(inst_res.zero_sensor, ZeroSensorResult)
    res = inst_res.zero_sensor
    assert res.zeroed_sensors == ["Zero Force Sensor"]
    assert res.verified is True
    assert app.click.call_count == 1
    app.click.assert_called_once_with(100, "ref:zero1", allow_foreground=True)
