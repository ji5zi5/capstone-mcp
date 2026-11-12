# Copyright 2026 Capstone MCP contributors.
"""Tests for smart triggers, recording conditions, and keep sample tools."""

from unittest.mock import MagicMock

import pytest

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.models import Bounds, Control, Snapshot, Window
from capstone_mcp.smart_triggers import (
    ConditionSpec,
    KeepSampleRequest,
    KeepSampleResult,
    SetRecordingConditionRequest,
    SetRecordingConditionResult,
    SetSamplingModeRequest,
    SetSamplingModeResult,
    keep_sample,
    set_recording_condition,
    set_sampling_mode,
)


def _make_window() -> Window:
    return Window(
        handle=100,
        title="Capstone",
        process_id=1,
        bounds=Bounds(left=0, top=0, right=1200, bottom=900),
    )


# --- Tests for set_recording_condition ---


def test_set_recording_condition_rejects_missing_foreground() -> None:
    app = Capstone()
    req = SetRecordingConditionRequest(
        handle=100,
        start_condition=ConditionSpec(condition_type="time", threshold=5.0),
        allow_foreground=False,
    )
    with pytest.raises(AutomationError, match="allow_foreground"):
        _ = set_recording_condition(app, req)


def test_set_recording_condition_rejects_empty_conditions() -> None:
    app = Capstone()
    req = SetRecordingConditionRequest(handle=100)
    with pytest.raises(AutomationError, match="At least one"):
        _ = set_recording_condition(app, req)


def test_set_recording_condition_raises_when_toggle_not_found() -> None:
    app = Capstone()
    mock_win = _make_window()
    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_win,
        controls=[
            Control(
                ref="ref:btn", parent=None, name="Calculator",
                control_type="CheckBox", automation_id="ObjNameCalculator",
                enabled=True, visible=True,
                bounds=Bounds(left=0, top=0, right=50, bottom=50),
            ),
        ],
        truncated=False,
    ))

    req = SetRecordingConditionRequest(
        handle=100,
        start_condition=ConditionSpec(condition_type="time", threshold=3.0),
    )
    with pytest.raises(AutomationError, match="Recording Conditions toggle button"):
        _ = set_recording_condition(app, req)


def test_set_recording_condition_success() -> None:
    app = Capstone()
    mock_win = _make_window()

    toggle_ctrl = Control(
        ref="ref:rc_toggle", parent=None, name="Recording Conditions",
        control_type="CheckBox",
        automation_id="Controls.ObjNameRecordingConditions",
        enabled=True, visible=True,
        bounds=Bounds(left=10, top=10, right=60, bottom=60),
    )
    start_type_ctrl = Control(
        ref="ref:start_type", parent=None, name="Start Condition Type",
        control_type="ComboBox", automation_id="start_type_combo",
        enabled=True, visible=True,
        bounds=Bounds(left=100, top=10, right=200, bottom=40),
    )
    start_thresh_ctrl = Control(
        ref="ref:start_thresh", parent=None, name="Start Threshold",
        control_type="Edit", automation_id="start_threshold_edit",
        enabled=True, visible=True,
        bounds=Bounds(left=210, top=10, right=280, bottom=40),
    )
    stop_type_ctrl = Control(
        ref="ref:stop_type", parent=None, name="Stop Condition Type",
        control_type="ComboBox", automation_id="stop_type_combo",
        enabled=True, visible=True,
        bounds=Bounds(left=100, top=50, right=200, bottom=80),
    )
    stop_thresh_ctrl = Control(
        ref="ref:stop_thresh", parent=None, name="Stop Threshold",
        control_type="Edit", automation_id="stop_threshold_edit",
        enabled=True, visible=True,
        bounds=Bounds(left=210, top=50, right=280, bottom=80),
    )

    step = 0

    def mock_snapshot(*_args: object, **_kwargs: object) -> Snapshot:
        nonlocal step
        step += 1
        ctrls = [toggle_ctrl]
        if step > 1:
            ctrls.extend([
                start_type_ctrl,
                start_thresh_ctrl,
                stop_type_ctrl,
                stop_thresh_ctrl,
            ])
        return Snapshot(window=mock_win, controls=ctrls, truncated=False)

    app.snapshot = mock_snapshot
    app.click = MagicMock()
    app.keys = MagicMock()

    toggle_node = MagicMock()
    toggle_node.iface_toggle.ToggleState = 0  # closed

    start_thresh_node = MagicMock()
    stop_thresh_node = MagicMock()

    def mock_control(ref: str) -> MagicMock:
        if ref == "ref:rc_toggle":
            return toggle_node
        if ref == "ref:start_thresh":
            return start_thresh_node
        if ref == "ref:stop_thresh":
            return stop_thresh_node
        return MagicMock()

    app.control = mock_control

    req = SetRecordingConditionRequest(
        handle=100,
        start_condition=ConditionSpec(
            condition_type="sensor_threshold",
            measurement="Force",
            operator="above",
            threshold=5.0,
        ),
        stop_condition=ConditionSpec(
            condition_type="time",
            threshold=10.0,
        ),
    )
    result = set_recording_condition(app, req)

    assert isinstance(result, SetRecordingConditionResult)
    assert result.verified is True
    assert result.start_condition is not None
    assert result.start_condition.threshold == 5.0
    assert result.stop_condition is not None
    assert result.stop_condition.threshold == 10.0
    # Opened and restored
    assert app.click.call_count == 2


# --- Tests for set_sampling_mode ---


def test_set_sampling_mode_requires_foreground() -> None:
    app = Capstone()
    req = SetSamplingModeRequest(handle=100, mode="keep_sample", allow_foreground=False)
    with pytest.raises(AutomationError, match="allow_foreground"):
        _ = set_sampling_mode(app, req)


def test_set_sampling_mode_raises_when_control_not_found() -> None:
    app = Capstone()
    mock_win = _make_window()
    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_win,
        controls=[],
        truncated=False,
    ))

    req = SetSamplingModeRequest(handle=100, mode="keep_sample")
    with pytest.raises(AutomationError, match="Sampling mode control"):
        _ = set_sampling_mode(app, req)


def test_set_sampling_mode_success() -> None:
    app = Capstone()
    mock_win = _make_window()

    mode_btn = Control(
        ref="ref:keep_radio", parent=None, name="Keep Sample",
        control_type="RadioButton", automation_id="mode_keep_sample",
        enabled=True, visible=True,
        bounds=Bounds(left=100, top=800, right=200, bottom=830),
    )
    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_win,
        controls=[mode_btn],
        truncated=False,
    ))

    btn_node = MagicMock()
    app.control = MagicMock(return_value=btn_node)

    req = SetSamplingModeRequest(handle=100, mode="keep_sample")
    result = set_sampling_mode(app, req)

    assert isinstance(result, SetSamplingModeResult)
    assert result.mode == "keep_sample"
    assert result.verified is True
    btn_node.iface_selection_item.Select.assert_called_once()


# --- Tests for keep_sample ---


def test_keep_sample_requires_foreground() -> None:
    app = Capstone()
    req = KeepSampleRequest(handle=100, allow_foreground=False)
    with pytest.raises(AutomationError, match="allow_foreground"):
        _ = keep_sample(app, req)


def test_keep_sample_raises_when_button_not_found() -> None:
    app = Capstone()
    mock_win = _make_window()
    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_win,
        controls=[],
        truncated=False,
    ))

    req = KeepSampleRequest(handle=100)
    with pytest.raises(AutomationError, match="Keep Sample button not found"):
        _ = keep_sample(app, req)


def test_keep_sample_success_with_value_entry() -> None:
    app = Capstone()
    mock_win = _make_window()

    keep_btn = Control(
        ref="ref:keep_btn", parent=None, name="Keep Sample",
        control_type="Button", automation_id="ControlBar.KeepSampleButton",
        enabled=True, visible=True,
        bounds=Bounds(left=50, top=800, right=150, bottom=830),
    )
    val_edit = Control(
        ref="ref:val_edit", parent=None, name="Position Value",
        control_type="Edit", automation_id="SampleValueEdit",
        enabled=True, visible=True,
        bounds=Bounds(left=300, top=400, right=400, bottom=430),
    )

    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_win,
        controls=[keep_btn, val_edit],
        truncated=False,
    ))
    app.click = MagicMock()
    app.keys = MagicMock()

    val_node = MagicMock()
    app.control = MagicMock(return_value=val_node)

    req = KeepSampleRequest(handle=100, value=0.25, variable_name="Position")
    result = keep_sample(app, req)

    assert isinstance(result, KeepSampleResult)
    assert result.sample_retained is True
    assert result.recorded_value == 0.25
    assert result.variable_name == "Position"
    assert result.verified is True
    app.click.assert_called_once_with(100, "ref:keep_btn", allow_foreground=True)
    val_node.iface_value.SetValue.assert_called_once_with("0.25")
    app.keys.assert_called_once_with(100, "{ENTER}", allow_foreground=True)
