# Copyright 2026 Capstone MCP contributors.
"""Tests for high-level Digits display creation and monitoring tool."""

from unittest.mock import MagicMock

import pytest

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.displays import (
    CreateDigitsRequest,
    CreateDigitsResult,
    DisplayAction,
    DisplayRequest,
    DisplayResult,
    manage_display,
)
from capstone_mcp.models import Bounds, Control, Snapshot, Window


def _mock_window(handle: int = 100) -> Window:
    return Window(
        handle=handle,
        title="Capstone",
        process_id=1,
        bounds=Bounds(left=0, top=0, right=1200, bottom=900),
    )


def test_create_digits_refuses_disabled_foreground() -> None:
    app = Capstone()
    req = DisplayRequest(
        action=DisplayAction.CREATE_DIGITS,
        create_digits=CreateDigitsRequest(handle=100, allow_foreground=False),
    )
    with pytest.raises(AutomationError, match="allow_foreground=true"):
        manage_display(app, req)


def test_create_digits_raises_when_palette_missing() -> None:
    app = Capstone()
    mock_win = _mock_window()
    app.snapshot = MagicMock(
        return_value=Snapshot(
            window=mock_win,
            controls=[
                Control(
                    ref="ref:other",
                    parent=None,
                    name="Graph",
                    control_type="Text",
                    automation_id="Palette.Graph",
                    enabled=True,
                    visible=True,
                    bounds=Bounds(left=10, top=10, right=50, bottom=50),
                ),
            ],
            truncated=False,
        ),
    )
    with pytest.raises(AutomationError, match="Digits display palette item not found"):
        manage_display(
            app,
            DisplayRequest(
                action=DisplayAction.CREATE_DIGITS,
                create_digits=CreateDigitsRequest(handle=100),
            ),
        )


def test_create_digits_success_without_binding() -> None:
    app = Capstone()
    mock_win = _mock_window()

    palette_item = Control(
        ref="ref:digits_palette",
        parent=None,
        name="Digits",
        control_type="Text",
        automation_id="Palette.ObjNameDigits",
        enabled=True,
        visible=True,
        bounds=Bounds(left=10, top=200, right=60, bottom=230),
    )
    digits_ctrl = Control(
        ref="ref:digits_widget",
        parent=None,
        name="Digits 1",
        control_type="Custom",
        automation_id="DigitsDisplay",
        enabled=True,
        visible=True,
        bounds=Bounds(left=100, top=100, right=400, bottom=300),
    )
    value_text = Control(
        ref="ref:val",
        parent="ref:digits_widget",
        name="0.00",
        control_type="Text",
        automation_id="DisplayValue",
        enabled=True,
        visible=True,
        bounds=Bounds(left=120, top=140, right=300, bottom=220),
    )

    call_count = 0

    def mock_snapshot(*_args: object, **_kwargs: object) -> Snapshot:
        nonlocal call_count
        call_count += 1
        ctrls = [palette_item]
        if call_count > 1:
            ctrls.extend([digits_ctrl, value_text])
        return Snapshot(window=mock_win, controls=ctrls, truncated=False)

    app.snapshot = mock_snapshot
    app.click = MagicMock()

    display_res = manage_display(
        app,
        DisplayRequest(
            action=DisplayAction.CREATE_DIGITS,
            create_digits=CreateDigitsRequest(handle=100),
        ),
    )

    assert isinstance(display_res, DisplayResult)
    assert isinstance(display_res.create_digits, CreateDigitsResult)
    res = display_res.create_digits
    assert res.created is True
    assert res.digits_name == "Digits 1"
    assert res.current_value == 0.0
    assert res.verified is True
    app.click.assert_called_once_with(100, "ref:digits_palette", allow_foreground=True)


def test_create_digits_success_with_measurement_and_unit() -> None:
    app = Capstone()
    mock_win = _mock_window()

    palette_item = Control(
        ref="ref:digits_palette",
        parent=None,
        name="Digits",
        control_type="Text",
        automation_id="Palette.ObjNameDigits",
        enabled=True,
        visible=True,
        bounds=Bounds(left=10, top=200, right=60, bottom=230),
    )
    digits_ctrl = Control(
        ref="ref:digits_widget",
        parent=None,
        name="Digits",
        control_type="Custom",
        automation_id="DigitsDisplay",
        enabled=True,
        visible=True,
        bounds=Bounds(left=100, top=100, right=500, bottom=350),
    )
    selector = Control(
        ref="ref:selector",
        parent="ref:digits_widget",
        name="<Select Measurement>",
        control_type="Button",
        automation_id="MeasurementSelector",
        enabled=True,
        visible=True,
        bounds=Bounds(left=110, top=110, right=280, bottom=135),
    )
    value_text = Control(
        ref="ref:val",
        parent="ref:digits_widget",
        name="9.81",
        control_type="Text",
        automation_id="DisplayValue",
        enabled=True,
        visible=True,
        bounds=Bounds(left=150, top=150, right=350, bottom=260),
    )
    unit_text = Control(
        ref="ref:unit",
        parent="ref:digits_widget",
        name="m/s^2",
        control_type="Text",
        automation_id="DisplayUnit",
        enabled=True,
        visible=True,
        bounds=Bounds(left=360, top=200, right=450, bottom=240),
    )

    call_count = 0

    def mock_snapshot(*_args: object, **_kwargs: object) -> Snapshot:
        nonlocal call_count
        call_count += 1
        ctrls = [palette_item]
        if call_count > 1:
            ctrls.extend([digits_ctrl, selector, value_text, unit_text])
        return Snapshot(window=mock_win, controls=ctrls, truncated=False)

    app.snapshot = mock_snapshot
    app.click = MagicMock()
    app.keys = MagicMock()

    mock_node = MagicMock()
    mock_node.iface_value.SetValue = MagicMock()
    app.control = MagicMock(return_value=mock_node)

    display_res = manage_display(
        app,
        DisplayRequest(
            action=DisplayAction.CREATE_DIGITS,
            create_digits=CreateDigitsRequest(
                handle=100,
                measurement="Acceleration (m/s^2)",
            ),
        ),
    )

    assert isinstance(display_res, DisplayResult)
    assert isinstance(display_res.create_digits, CreateDigitsResult)
    res = display_res.create_digits
    assert res.created is True
    assert res.digits_name == "Digits"
    assert res.measurement == "Acceleration (m/s^2)"
    assert res.current_value == 9.81
    assert res.unit == "m/s^2"
    assert res.verified is True
    assert app.click.call_count == 2
