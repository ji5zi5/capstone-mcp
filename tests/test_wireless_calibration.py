# Copyright 2026 Capstone MCP contributors.
"""Tests for wireless sensor discovery, pairing, and calibration tools."""

from unittest.mock import MagicMock

import pytest

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.models import Bounds, Control, Snapshot, Window
from capstone_mcp.wireless_calibration import (
    CalibrateSensorRequest,
    ConnectWirelessSensorRequest,
    ScanWirelessSensorsRequest,
    calibrate_sensor,
    connect_wireless_sensor,
    scan_wireless_sensors,
)


def _create_mock_window(handle: int = 100) -> Window:
    return Window(
        handle=handle,
        title="Capstone - Experiment",
        process_id=1001,
        bounds=Bounds(left=0, top=0, right=1200, bottom=900),
    )


def test_scan_wireless_sensors_requires_foreground() -> None:
    app = Capstone()
    req = ScanWirelessSensorsRequest(allow_foreground=False)
    with pytest.raises(AutomationError, match="allow_foreground=true"):
        _ = scan_wireless_sensors(app, req)


def test_scan_wireless_sensors_raises_when_toggle_missing() -> None:
    app = Capstone()
    mock_win = _create_mock_window()
    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_win,
        controls=[],
        truncated=False,
    ))
    req = ScanWirelessSensorsRequest()
    with pytest.raises(AutomationError, match="Hardware Setup palette toggle"):
        _ = scan_wireless_sensors(app, req)


def test_scan_wireless_sensors_success_discovers_sensors() -> None:
    app = Capstone()
    mock_win = _create_mock_window()

    toggle_btn = Control(
        ref="ref:hw_toggle", parent=None, name="Hardware Setup",
        control_type="CheckBox", automation_id="Palette.ObjNameHardware",
        enabled=True, visible=True,
        bounds=Bounds(left=10, top=50, right=50, bottom=90),
    )
    sensor1 = Control(
        ref="ref:s1", parent=None,
        name="Wireless Force Acceleration Sensor 642-108 (85%)",
        control_type="ListItem", automation_id="Device.642-108",
        enabled=True, visible=True,
        bounds=Bounds(left=100, top=100, right=300, bottom=130),
    )
    sensor2 = Control(
        ref="ref:s2", parent=None,
        name="Smart Cart Red 024-511 Connected",
        control_type="ListItem", automation_id="Device.024-511",
        enabled=True, visible=True,
        bounds=Bounds(left=100, top=140, right=300, bottom=170),
    )

    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_win,
        controls=[toggle_btn, sensor1, sensor2],
        truncated=False,
    ))
    app.click = MagicMock()

    toggle_node = MagicMock()
    toggle_node.iface_toggle.ToggleState = 1  # already open
    app.control = MagicMock(return_value=toggle_node)

    req = ScanWirelessSensorsRequest()
    res = scan_wireless_sensors(app, req)

    assert res.count == 2
    assert res.sensors[0].sensor_id == "642-108"
    assert res.sensors[0].battery_percent == 85
    assert res.sensors[0].connected is False
    assert res.sensors[1].sensor_id == "024-511"
    assert res.sensors[1].connected is True
    assert res.verified is True


def test_connect_wireless_sensor_requires_foreground() -> None:
    app = Capstone()
    req = ConnectWirelessSensorRequest(sensor_id="642-108", allow_foreground=False)
    with pytest.raises(AutomationError, match="allow_foreground=true"):
        _ = connect_wireless_sensor(app, req)


def test_connect_wireless_sensor_rejects_empty_id() -> None:
    app = Capstone()
    req = ConnectWirelessSensorRequest(sensor_id="")
    with pytest.raises(AutomationError, match="sensor_id must not be empty"):
        _ = connect_wireless_sensor(app, req)


def test_connect_wireless_sensor_raises_when_not_found() -> None:
    app = Capstone()
    mock_win = _create_mock_window()

    toggle_btn = Control(
        ref="ref:hw_toggle", parent=None, name="Hardware Setup",
        control_type="CheckBox", automation_id="Palette.ObjNameHardware",
        enabled=True, visible=True,
        bounds=Bounds(left=10, top=50, right=50, bottom=90),
    )
    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_win,
        controls=[toggle_btn],
        truncated=False,
    ))
    toggle_node = MagicMock()
    toggle_node.iface_toggle.ToggleState = 1
    app.control = MagicMock(return_value=toggle_node)

    req = ConnectWirelessSensorRequest(sensor_id="999-999")
    with pytest.raises(AutomationError, match="not found in Hardware Setup"):
        _ = connect_wireless_sensor(app, req)


def test_connect_wireless_sensor_success() -> None:
    app = Capstone()
    mock_win = _create_mock_window()

    toggle_btn = Control(
        ref="ref:hw_toggle", parent=None, name="Hardware Setup",
        control_type="CheckBox", automation_id="Palette.ObjNameHardware",
        enabled=True, visible=True,
        bounds=Bounds(left=10, top=50, right=50, bottom=90),
    )
    sensor_item = Control(
        ref="ref:s1", parent=None,
        name="Wireless Force Sensor 642-108",
        control_type="ListItem", automation_id="Device.642-108",
        enabled=True, visible=True,
        bounds=Bounds(left=100, top=100, right=300, bottom=130),
    )
    connect_btn = Control(
        ref="ref:conn_btn", parent=None,
        name="Connect",
        control_type="Button", automation_id="Device.642-108.Connect",
        enabled=True, visible=True,
        bounds=Bounds(left=310, top=100, right=380, bottom=130),
    )

    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_win,
        controls=[toggle_btn, sensor_item, connect_btn],
        truncated=False,
    ))
    app.click = MagicMock()

    toggle_node = MagicMock()
    toggle_node.iface_toggle.ToggleState = 1
    app.control = MagicMock(return_value=toggle_node)

    req = ConnectWirelessSensorRequest(sensor_id="642-108", handle=100)
    res = connect_wireless_sensor(app, req)

    assert res.sensor_id == "642-108"
    assert res.connected is True
    assert res.verified is True
    app.click.assert_called_once_with(100, "ref:conn_btn", allow_foreground=True)


def test_calibrate_sensor_requires_foreground() -> None:
    app = Capstone()
    req = CalibrateSensorRequest(sensor_name="Force", allow_foreground=False)
    with pytest.raises(AutomationError, match="allow_foreground=true"):
        _ = calibrate_sensor(app, req)


def test_calibrate_sensor_rejects_invalid_type() -> None:
    app = Capstone()
    req = CalibrateSensorRequest(sensor_name="Force", calibration_type="3_point")
    with pytest.raises(AutomationError, match="Unsupported calibration type"):
        _ = calibrate_sensor(app, req)


def test_calibrate_sensor_requires_standard_2_for_two_point() -> None:
    app = Capstone()
    req = CalibrateSensorRequest(
        sensor_name="Force",
        calibration_type="two_point",
        standard_1=0.0,
        standard_2=None,
    )
    with pytest.raises(AutomationError, match="standard_2 is required"):
        _ = calibrate_sensor(app, req)


def test_calibrate_sensor_two_point_success() -> None:
    app = Capstone()
    mock_win = _create_mock_window()

    toggle_btn = Control(
        ref="ref:cal_toggle", parent=None, name="Calibration",
        control_type="CheckBox", automation_id="Palette.ObjNameCalibration",
        enabled=True, visible=True,
        bounds=Bounds(left=10, top=50, right=50, bottom=90),
    )
    meas_item = Control(
        ref="ref:meas", parent=None, name="Force Sensor",
        control_type="RadioButton", automation_id="Cal.MeasSelector",
        enabled=True, visible=True,
        bounds=Bounds(left=100, top=100, right=200, bottom=130),
    )
    next_btn = Control(
        ref="ref:next", parent=None, name="Next",
        control_type="Button", automation_id="Cal.Next",
        enabled=True, visible=True,
        bounds=Bounds(left=300, top=400, right=360, bottom=430),
    )
    std_edit = Control(
        ref="ref:std_edit", parent=None, name="Standard Value",
        control_type="Edit", automation_id="Cal.StdValue",
        enabled=True, visible=True,
        bounds=Bounds(left=100, top=150, right=200, bottom=180),
    )
    set_btn = Control(
        ref="ref:set_btn", parent=None, name="Set",
        control_type="Button", automation_id="Cal.Set",
        enabled=True, visible=True,
        bounds=Bounds(left=210, top=150, right=260, bottom=180),
    )
    finish_btn = Control(
        ref="ref:finish", parent=None, name="Finish",
        control_type="Button", automation_id="Cal.Finish",
        enabled=True, visible=True,
        bounds=Bounds(left=300, top=400, right=360, bottom=430),
    )

    step = 0

    def mock_snapshot(*_args: object, **_kwargs: object) -> Snapshot:
        nonlocal step
        step += 1
        controls = [toggle_btn]
        if step == 1:
            controls.extend([meas_item, next_btn])
        elif step in (2, 3):
            controls.extend([std_edit, set_btn, next_btn])
        else:
            controls.extend([finish_btn])
        return Snapshot(window=mock_win, controls=controls, truncated=False)

    app.snapshot = mock_snapshot
    app.click = MagicMock()
    app.keys = MagicMock()
    app.type_text = MagicMock()

    toggle_node = MagicMock()
    toggle_node.iface_toggle.ToggleState = 1  # already open

    std_node = MagicMock()
    std_node.iface_value.SetValue = MagicMock()

    def mock_ctrl(ref: str) -> MagicMock:
        if ref == "ref:cal_toggle":
            return toggle_node
        if ref == "ref:std_edit":
            return std_node
        return MagicMock()

    app.control = mock_ctrl

    req = CalibrateSensorRequest(
        sensor_name="Force Sensor",
        measurement_type="Force",
        calibration_type="two_point",
        standard_1=0.0,
        standard_2=9.8,
    )
    res = calibrate_sensor(app, req)

    assert res.sensor_name == "Force Sensor"
    assert res.calibration_type == "two_point"
    assert res.standard_1 == 0.0
    assert res.standard_2 == 9.8
    assert res.verified is True
    assert std_node.iface_value.SetValue.call_count == 2
