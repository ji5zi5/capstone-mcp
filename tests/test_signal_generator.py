# Copyright 2026 Capstone MCP contributors.
"""Tests for Capstone Signal Generator control and status tools."""

from unittest.mock import MagicMock

import pytest

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.models import Bounds, Control, Snapshot, Window
from capstone_mcp.signal_generator import (
    ReadSignalGeneratorStatusRequest,
    SetSignalGeneratorRequest,
    read_signal_generator_status,
    set_signal_generator,
)


def _create_mock_window(handle: int = 100) -> Window:
    return Window(
        handle=handle,
        title="Capstone - Experiment",
        process_id=1001,
        bounds=Bounds(left=0, top=0, right=1200, bottom=900),
    )


def test_set_signal_generator_requires_foreground() -> None:
    app = Capstone()
    req = SetSignalGeneratorRequest(allow_foreground=False)
    with pytest.raises(AutomationError, match="allow_foreground=true"):
        _ = set_signal_generator(app, req)


def test_set_signal_generator_rejects_invalid_waveform() -> None:
    app = Capstone()
    req = SetSignalGeneratorRequest(waveform="InvalidWave")
    with pytest.raises(AutomationError, match="Unsupported waveform"):
        _ = set_signal_generator(app, req)


def test_set_signal_generator_rejects_negative_frequency() -> None:
    app = Capstone()
    req = SetSignalGeneratorRequest(frequency=-10.0)
    with pytest.raises(AutomationError, match="Frequency must be non-negative"):
        _ = set_signal_generator(app, req)


def test_set_signal_generator_raises_when_toggle_not_found() -> None:
    app = Capstone()
    mock_win = _create_mock_window()
    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_win,
        controls=[
            Control(
                ref="ref:other", parent=None, name="Calculator",
                control_type="CheckBox", automation_id="Palette.ObjNameCalculator",
                enabled=True, visible=True,
                bounds=Bounds(left=0, top=0, right=50, bottom=50),
            ),
        ],
        truncated=False,
    ))

    req = SetSignalGeneratorRequest()
    with pytest.raises(
        AutomationError,
        match="Signal Generator palette toggle button not found",
    ):
        _ = set_signal_generator(app, req)


def test_set_signal_generator_success_opens_configures_and_restores() -> None:
    app = Capstone()
    mock_win = _create_mock_window()

    toggle_btn = Control(
        ref="ref:sig_toggle", parent=None, name="Signal Generator",
        control_type="CheckBox", automation_id="Palette.ObjNameSignalGenerator",
        enabled=True, visible=True,
        bounds=Bounds(left=10, top=50, right=50, bottom=90),
    )
    power_btn = Control(
        ref="ref:power_btn", parent=None, name="Power",
        control_type="Button", automation_id="SignalGenerator.Power",
        enabled=True, visible=True,
        bounds=Bounds(left=100, top=50, right=150, bottom=80),
    )
    wave_ctrl = Control(
        ref="ref:wave_ctrl", parent=None, name="Waveform",
        control_type="ComboBox", automation_id="SignalGenerator.Waveform",
        enabled=True, visible=True,
        bounds=Bounds(left=100, top=90, right=200, bottom=120),
    )
    freq_edit = Control(
        ref="ref:freq_edit", parent=None, name="Frequency",
        control_type="Edit", automation_id="SignalGenerator.Frequency",
        enabled=True, visible=True,
        bounds=Bounds(left=100, top=130, right=200, bottom=160),
    )
    amp_edit = Control(
        ref="ref:amp_edit", parent=None, name="Amplitude",
        control_type="Edit", automation_id="SignalGenerator.Amplitude",
        enabled=True, visible=True,
        bounds=Bounds(left=100, top=170, right=200, bottom=200),
    )

    step = 0

    def mock_snapshot(*_args: object, **_kwargs: object) -> Snapshot:
        nonlocal step
        step += 1
        controls = [toggle_btn]
        if step > 1:
            controls.extend([power_btn, wave_ctrl, freq_edit, amp_edit])
        return Snapshot(window=mock_win, controls=controls, truncated=False)

    app.snapshot = mock_snapshot
    app.click = MagicMock()
    app.keys = MagicMock()
    app.type_text = MagicMock()

    toggle_node = MagicMock()
    toggle_node.iface_toggle.ToggleState = 0  # initially closed

    power_node = MagicMock()
    power_node.iface_toggle.ToggleState = 0  # initially off

    wave_node = MagicMock()
    wave_node.iface_value.SetValue = MagicMock()

    freq_node = MagicMock()
    freq_node.iface_value.SetValue = MagicMock()

    amp_node = MagicMock()
    amp_node.iface_value.SetValue = MagicMock()

    def mock_control(ref: str) -> MagicMock:
        if ref == "ref:sig_toggle":
            return toggle_node
        if ref == "ref:power_btn":
            return power_node
        if ref == "ref:wave_ctrl":
            return wave_node
        if ref == "ref:freq_edit":
            return freq_node
        if ref == "ref:amp_edit":
            return amp_node
        return MagicMock()

    app.control = mock_control

    req = SetSignalGeneratorRequest(
        waveform="square",
        frequency=500.0,
        amplitude=3.5,
        enabled=True,
        keep_open=False,
    )
    result = set_signal_generator(app, req)

    assert result.waveform == "Square"
    assert result.frequency == 500.0
    assert result.amplitude == 3.5
    assert result.enabled is True
    assert result.verified is True

    # Check drawer open and restore calls
    assert app.click.call_count == 3
    wave_node.iface_value.SetValue.assert_called_once_with("Square")
    freq_node.iface_value.SetValue.assert_called_once_with("500.0 Hz")
    amp_node.iface_value.SetValue.assert_called_once_with("3.5 V")


def test_set_signal_generator_keep_open() -> None:
    app = Capstone()
    mock_win = _create_mock_window()

    toggle_btn = Control(
        ref="ref:sig_toggle", parent=None, name="Signal Generator",
        control_type="CheckBox", automation_id="Palette.ObjNameSignalGenerator",
        enabled=True, visible=True,
        bounds=Bounds(left=10, top=50, right=50, bottom=90),
    )
    power_btn = Control(
        ref="ref:power_btn", parent=None, name="Power",
        control_type="Button", automation_id="SignalGenerator.Power",
        enabled=True, visible=True,
        bounds=Bounds(left=100, top=50, right=150, bottom=80),
    )

    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_win,
        controls=[toggle_btn, power_btn],
        truncated=False,
    ))
    app.click = MagicMock()

    toggle_node = MagicMock()
    toggle_node.iface_toggle.ToggleState = 0
    power_node = MagicMock()
    power_node.iface_toggle.ToggleState = 1  # already on

    def mock_ctrl(ref: str) -> MagicMock:
        return toggle_node if ref == "ref:sig_toggle" else power_node

    app.control = MagicMock(side_effect=mock_ctrl)

    req = SetSignalGeneratorRequest(enabled=True, keep_open=True)
    result = set_signal_generator(app, req)
    assert result.verified is True

    # 1 click to open, 0 to change power (already on), 0 to close (keep_open=True)
    assert app.click.call_count == 1


def test_read_signal_generator_status_success() -> None:
    app = Capstone()
    mock_win = _create_mock_window()

    toggle_btn = Control(
        ref="ref:sig_toggle", parent=None, name="Signal Generator",
        control_type="CheckBox", automation_id="Palette.ObjNameSignalGenerator",
        enabled=True, visible=True,
        bounds=Bounds(left=10, top=50, right=50, bottom=90),
    )
    power_btn = Control(
        ref="ref:power_btn", parent=None, name="Power",
        control_type="Button", automation_id="SignalGenerator.Power",
        enabled=True, visible=True,
        bounds=Bounds(left=100, top=50, right=150, bottom=80),
    )
    wave_ctrl = Control(
        ref="ref:wave_ctrl", parent=None, name="Triangle",
        control_type="ComboBox", automation_id="SignalGenerator.Waveform",
        enabled=True, visible=True,
        bounds=Bounds(left=100, top=90, right=200, bottom=120),
    )
    freq_edit = Control(
        ref="ref:freq_edit", parent=None, name="2000 Hz",
        control_type="Edit", automation_id="SignalGenerator.Frequency",
        enabled=True, visible=True,
        bounds=Bounds(left=100, top=130, right=200, bottom=160),
    )
    amp_edit = Control(
        ref="ref:amp_edit", parent=None, name="2.5 V",
        control_type="Edit", automation_id="SignalGenerator.Amplitude",
        enabled=True, visible=True,
        bounds=Bounds(left=100, top=170, right=200, bottom=200),
    )

    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_win,
        controls=[toggle_btn, power_btn, wave_ctrl, freq_edit, amp_edit],
        truncated=False,
    ))
    app.click = MagicMock()

    toggle_node = MagicMock()
    toggle_node.iface_toggle.ToggleState = 1  # already open!

    power_node = MagicMock()
    power_node.iface_toggle.ToggleState = 1  # ON

    wave_node = MagicMock()
    wave_node.iface_value.CurrentValue = "Triangle"

    freq_node = MagicMock()
    freq_node.iface_value.CurrentValue = "2000 Hz"

    amp_node = MagicMock()
    amp_node.iface_value.CurrentValue = "2.5 V"

    def mock_control(ref: str) -> MagicMock:
        mapping = {
            "ref:sig_toggle": toggle_node,
            "ref:power_btn": power_node,
            "ref:wave_ctrl": wave_node,
            "ref:freq_edit": freq_node,
            "ref:amp_edit": amp_node,
        }
        return mapping.get(ref, MagicMock())

    app.control = mock_control

    req = ReadSignalGeneratorStatusRequest()
    result = read_signal_generator_status(app, req)

    assert result.enabled is True
    assert result.waveform == "Triangle"
    assert result.frequency == 2000.0
    assert result.amplitude == 2.5
    assert result.verified is True
    # Drawer was already open, so no toggle clicks should occur!
    assert app.click.call_count == 0
