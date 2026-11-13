# Copyright 2026 Capstone MCP contributors.
"""Tests for oscilloscope and FFT spectrum display tools."""

from unittest.mock import MagicMock

import pytest

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.displays import (
    CreateFftRequest,
    CreateFftResult,
    CreateScopeRequest,
    CreateScopeResult,
    DisplayAction,
    DisplayRequest,
    DisplayResult,
    ReadFftPeaksRequest,
    ReadFftPeaksResult,
    ScopeTriggerResult,
    SetScopeTriggerRequest,
    manage_display,
)
from capstone_mcp.models import Bounds, Control, Snapshot, Window


def _create_mock_window(handle: int = 100) -> Window:
    return Window(
        handle=handle,
        title="Capstone - Experiment",
        process_id=1001,
        bounds=Bounds(left=0, top=0, right=1200, bottom=900),
    )


def test_create_scope_requires_foreground() -> None:
    app = Capstone()
    req = CreateScopeRequest(allow_foreground=False)
    with pytest.raises(AutomationError, match="allow_foreground=true"):
        _ = manage_display(
            app,
            DisplayRequest(action=DisplayAction.CREATE_SCOPE, create_scope=req),
        )


def test_create_scope_raises_when_palette_not_found() -> None:
    app = Capstone()
    mock_win = _create_mock_window()
    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_win,
        controls=[
            Control(
                ref="ref:graph", parent=None, name="Graph",
                control_type="Text", automation_id="Palette.ObjNameGraph",
                enabled=True, visible=True,
                bounds=Bounds(left=1100, top=50, right=1180, bottom=90),
            ),
        ],
        truncated=False,
    ))

    req = CreateScopeRequest()
    with pytest.raises(
        AutomationError,
        match="Expected Scope display palette item not found",
    ):
        _ = manage_display(
            app,
            DisplayRequest(action=DisplayAction.CREATE_SCOPE, create_scope=req),
        )


def test_create_scope_success() -> None:
    app = Capstone()
    mock_win = _create_mock_window()

    palette_scope = Control(
        ref="ref:palette_scope", parent=None, name="Scope",
        control_type="Text", automation_id="Palette.ObjNameScope",
        enabled=True, visible=True,
        bounds=Bounds(left=1100, top=100, right=1180, bottom=140),
    )
    timebase_edit = Control(
        ref="ref:timebase", parent=None, name="Timebase",
        control_type="Edit", automation_id="Scope.TimebaseEdit",
        enabled=True, visible=True,
        bounds=Bounds(left=200, top=100, right=280, bottom=130),
    )
    channel_edit = Control(
        ref="ref:channel", parent=None, name="Channel A",
        control_type="Edit", automation_id="Scope.ChannelSelector",
        enabled=True, visible=True,
        bounds=Bounds(left=200, top=140, right=280, bottom=170),
    )

    step = 0

    def mock_snapshot(*_args: object, **_kwargs: object) -> Snapshot:
        nonlocal step
        step += 1
        controls = [palette_scope]
        if step > 1:
            controls.extend([timebase_edit, channel_edit])
        return Snapshot(window=mock_win, controls=controls, truncated=False)

    app.snapshot = mock_snapshot
    app.focus_window = MagicMock()
    app.click = MagicMock()

    timebase_node = MagicMock()
    timebase_node.iface_value.SetValue = MagicMock()
    channel_node = MagicMock()
    channel_node.iface_value.SetValue = MagicMock()

    def mock_control(ref: str) -> MagicMock:
        if ref == "ref:timebase":
            return timebase_node
        if ref == "ref:channel":
            return channel_node
        mock_item = MagicMock()
        mock_item.rectangle.return_value = Bounds(
            left=1100, top=100, right=1180, bottom=140,
        )
        return mock_item

    app.control = mock_control

    req = CreateScopeRequest(timebase="2 ms/div", channel="Voltage (V)")
    display_res = manage_display(
        app,
        DisplayRequest(action=DisplayAction.CREATE_SCOPE, create_scope=req),
    )
    assert isinstance(display_res, DisplayResult)
    assert isinstance(display_res.create_scope, CreateScopeResult)
    res = display_res.create_scope

    assert res.display_type == "Scope"
    assert res.timebase == "2 ms/div"
    assert res.channel == "Voltage (V)"
    assert res.verified is True
    timebase_node.iface_value.SetValue.assert_called_once_with("2 ms/div")
    channel_node.iface_value.SetValue.assert_called_once_with("Voltage (V)")


def test_set_scope_trigger_requires_foreground() -> None:
    app = Capstone()
    req = SetScopeTriggerRequest(allow_foreground=False)
    with pytest.raises(AutomationError, match="allow_foreground=true"):
        _ = manage_display(
            app,
            DisplayRequest(
                action=DisplayAction.SET_SCOPE_TRIGGER,
                set_scope_trigger=req,
            ),
        )


def test_set_scope_trigger_rejects_invalid_inputs() -> None:
    app = Capstone()
    req1 = SetScopeTriggerRequest(trigger_slope="diagonal")
    with pytest.raises(AutomationError, match="Unsupported trigger slope"):
        _ = manage_display(
            app,
            DisplayRequest(
                action=DisplayAction.SET_SCOPE_TRIGGER,
                set_scope_trigger=req1,
            ),
        )

    req2 = SetScopeTriggerRequest(trigger_mode="infinite")
    with pytest.raises(AutomationError, match="Unsupported trigger mode"):
        _ = manage_display(
            app,
            DisplayRequest(
                action=DisplayAction.SET_SCOPE_TRIGGER,
                set_scope_trigger=req2,
            ),
        )


def test_set_scope_trigger_success() -> None:
    app = Capstone()
    mock_win = _create_mock_window()

    level_ctrl = Control(
        ref="ref:lvl", parent=None, name="Trigger Level",
        control_type="Edit", automation_id="Scope.TriggerLevel",
        enabled=True, visible=True,
        bounds=Bounds(left=300, top=100, right=380, bottom=130),
    )
    slope_ctrl = Control(
        ref="ref:slope", parent=None, name="Rising Edge",
        control_type="Button", automation_id="Scope.TriggerSlope",
        enabled=True, visible=True,
        bounds=Bounds(left=390, top=100, right=450, bottom=130),
    )
    mode_ctrl = Control(
        ref="ref:mode", parent=None, name="Auto",
        control_type="ComboBox", automation_id="Scope.TriggerMode",
        enabled=True, visible=True,
        bounds=Bounds(left=460, top=100, right=520, bottom=130),
    )

    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_win,
        controls=[level_ctrl, slope_ctrl, mode_ctrl],
        truncated=False,
    ))

    lvl_node = MagicMock()
    lvl_node.iface_value.SetValue = MagicMock()
    slope_node = MagicMock()
    slope_node.iface_value.SetValue = MagicMock()
    mode_node = MagicMock()
    mode_node.iface_value.SetValue = MagicMock()

    def mock_ctrl(ref: str) -> MagicMock:
        mapping = {
            "ref:lvl": lvl_node,
            "ref:slope": slope_node,
            "ref:mode": mode_node,
        }
        return mapping.get(ref, MagicMock())

    app.control = mock_ctrl

    req = SetScopeTriggerRequest(
        trigger_level=1.25,
        trigger_slope="falling",
        trigger_mode="single",
    )
    display_res = manage_display(
        app,
        DisplayRequest(
            action=DisplayAction.SET_SCOPE_TRIGGER,
            set_scope_trigger=req,
        ),
    )
    assert isinstance(display_res, DisplayResult)
    assert isinstance(display_res.set_scope_trigger, ScopeTriggerResult)
    res = display_res.set_scope_trigger

    assert res.trigger_level == 1.25
    assert res.trigger_slope == "falling"
    assert res.trigger_mode == "single"
    assert res.verified is True
    lvl_node.iface_value.SetValue.assert_called_once_with("1.25 V")
    slope_node.iface_value.SetValue.assert_called_once_with("falling")
    mode_node.iface_value.SetValue.assert_called_once_with("single")


def test_create_fft_success() -> None:
    app = Capstone()
    mock_win = _create_mock_window()

    palette_fft = Control(
        ref="ref:palette_fft", parent=None, name="FFT",
        control_type="Text", automation_id="Palette.ObjNameFFT",
        enabled=True, visible=True,
        bounds=Bounds(left=1100, top=200, right=1180, bottom=240),
    )
    meas_ctrl = Control(
        ref="ref:fft_meas", parent=None, name="Measurement",
        control_type="Edit", automation_id="FFT.MeasurementSelector",
        enabled=True, visible=True,
        bounds=Bounds(left=200, top=200, right=300, bottom=230),
    )
    range_ctrl = Control(
        ref="ref:fft_range", parent=None, name="Span",
        control_type="Edit", automation_id="FFT.FreqRangeEdit",
        enabled=True, visible=True,
        bounds=Bounds(left=310, top=200, right=400, bottom=230),
    )

    step = 0

    def mock_snapshot(*_args: object, **_kwargs: object) -> Snapshot:
        nonlocal step
        step += 1
        controls = [palette_fft]
        if step > 1:
            controls.extend([meas_ctrl, range_ctrl])
        return Snapshot(window=mock_win, controls=controls, truncated=False)

    app.snapshot = mock_snapshot
    app.focus_window = MagicMock()
    app.click = MagicMock()

    meas_node = MagicMock()
    meas_node.iface_value.SetValue = MagicMock()
    range_node = MagicMock()
    range_node.iface_value.SetValue = MagicMock()

    def mock_ctrl(ref: str) -> MagicMock:
        if ref == "ref:fft_meas":
            return meas_node
        if ref == "ref:fft_range":
            return range_node
        mock_item = MagicMock()
        mock_item.rectangle.return_value = Bounds(
            left=1100, top=200, right=1180, bottom=240,
        )
        return mock_item

    app.control = mock_ctrl

    req = CreateFftRequest(measurement="Sound Sensor", frequency_range="0 - 5000 Hz")
    display_res = manage_display(
        app,
        DisplayRequest(action=DisplayAction.CREATE_FFT, create_fft=req),
    )
    assert isinstance(display_res, DisplayResult)
    assert isinstance(display_res.create_fft, CreateFftResult)
    res = display_res.create_fft

    assert res.display_type == "FFT"
    assert res.measurement == "Sound Sensor"
    assert res.frequency_range == "0 - 5000 Hz"
    assert res.verified is True
    meas_node.iface_value.SetValue.assert_called_once_with("Sound Sensor")
    range_node.iface_value.SetValue.assert_called_once_with("0 - 5000 Hz")


def test_read_fft_peaks_success() -> None:
    app = Capstone()
    mock_win = _create_mock_window()

    coord_peak1 = Control(
        ref="ref:p1", parent=None, name="(440 Hz, 5.2 V)",
        control_type="Text", automation_id="FFT.Coordinate1",
        enabled=True, visible=True,
        bounds=Bounds(left=200, top=200, right=300, bottom=220),
    )
    coord_peak2 = Control(
        ref="ref:p2", parent=None, name="(880 Hz, 2.1 V)",
        control_type="Text", automation_id="FFT.Coordinate2",
        enabled=True, visible=True,
        bounds=Bounds(left=350, top=200, right=450, bottom=220),
    )
    coord_peak3 = Control(
        ref="ref:p3", parent=None, name="f = 1320 Hz, amp = 0.8 V",
        control_type="Text", automation_id="FFT.Coordinate3",
        enabled=True, visible=True,
        bounds=Bounds(left=500, top=200, right=600, bottom=220),
    )

    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_win,
        controls=[coord_peak1, coord_peak2, coord_peak3],
        truncated=False,
    ))

    req = ReadFftPeaksRequest(top_k=2)
    display_res = manage_display(
        app,
        DisplayRequest(action=DisplayAction.READ_FFT_PEAKS, read_fft_peaks=req),
    )
    assert isinstance(display_res, DisplayResult)
    assert isinstance(display_res.read_fft_peaks, ReadFftPeaksResult)
    res = display_res.read_fft_peaks

    assert res.peak_count == 2
    assert len(res.peaks) == 2
    # Sorted by amplitude descending: 5.2 V (440 Hz), 2.1 V (880 Hz)
    assert res.peaks[0].frequency_hz == 440.0
    assert res.peaks[0].amplitude == 5.2
    assert res.peaks[1].frequency_hz == 880.0
    assert res.peaks[1].amplitude == 2.1
    assert res.verified is True
