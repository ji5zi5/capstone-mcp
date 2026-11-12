# Copyright 2026 Capstone MCP contributors.
"""Tests for high-level calculator formula creation tool."""

from unittest.mock import MagicMock

import pytest

from capstone_mcp.calculator import (
    CreateCalculationRequest,
    CreateCalculationResult,
    create_calculation,
)
from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.models import Bounds, Control, Snapshot, Window


def test_create_calculation_rejects_empty_expression() -> None:
    app = Capstone()
    req = CreateCalculationRequest(handle=100, expression="")
    with pytest.raises(AutomationError, match="expression"):
        _ = create_calculation(app, req)


def test_create_calculation_raises_when_calculator_toggle_not_found() -> None:
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
                ref="ref:other", parent=None, name="Hardware Setup",
                control_type="CheckBox",
                automation_id="Palette.ObjNameHardware",
                enabled=True, visible=True,
                bounds=Bounds(left=0, top=0, right=50, bottom=50),
            ),
        ],
        truncated=False,
    ))

    req = CreateCalculationRequest(handle=100, expression="p = [m] * [v]")
    with pytest.raises(AutomationError, match="Calculator"):
        _ = create_calculation(app, req)


def test_create_calculation_success_opens_inputs_and_restores_drawer() -> None:
    app = Capstone()
    mock_window = Window(
        handle=100, title="Capstone", process_id=1,
        bounds=Bounds(left=0, top=0, right=1000, bottom=800),
    )
    app.windows = MagicMock(return_value=[mock_window])

    calc_toggle = Control(
        ref="ref:calc_btn", parent=None, name="Calculator",
        control_type="CheckBox", automation_id="Palette.ObjNameCalculator",
        enabled=True, visible=True,
        bounds=Bounds(left=10, top=100, right=50, bottom=140),
    )
    formula_edit = Control(
        ref="ref:edit_formula", parent=None, name="Calculation Formula",
        control_type="Edit", automation_id="Calculator.FormulaEditor",
        enabled=True, visible=True,
        bounds=Bounds(left=100, top=100, right=300, bottom=130),
    )
    unit_edit = Control(
        ref="ref:edit_unit", parent=None, name="Units",
        control_type="Edit", automation_id="Calculator.UnitEditor",
        enabled=True, visible=True,
        bounds=Bounds(left=310, top=100, right=360, bottom=130),
    )

    step = 0

    def mock_snapshot(*_args: object, **_kwargs: object) -> Snapshot:
        nonlocal step
        step += 1
        controls = [calc_toggle]
        if step > 1:
            controls.extend([formula_edit, unit_edit])
        return Snapshot(window=mock_window, controls=controls, truncated=False)

    app.snapshot = mock_snapshot
    app.focus_window = MagicMock()
    app.click = MagicMock()
    app.keys = MagicMock()

    mock_toggle_node = MagicMock()
    mock_toggle_node.iface_toggle.ToggleState = 0

    mock_formula_node = MagicMock()
    mock_formula_node.iface_value.SetValue = MagicMock()

    mock_unit_node = MagicMock()
    mock_unit_node.iface_value.SetValue = MagicMock()

    def mock_control(ref: str) -> MagicMock:
        if ref == "ref:calc_btn":
            return mock_toggle_node
        if ref == "ref:edit_formula":
            return mock_formula_node
        if ref == "ref:edit_unit":
            return mock_unit_node
        return MagicMock()

    app.control = mock_control

    req = CreateCalculationRequest(
        handle=100,
        expression="KE = 0.5 * [m] * [v]^2",
        unit="J",
    )
    result = create_calculation(app, req)

    assert isinstance(result, CreateCalculationResult)
    assert result.calculation_name == "KE"
    assert result.expression == "KE = 0.5 * [m] * [v]^2"
    assert result.unit == "J"
    assert result.status == "valid"
    assert result.verified is True

    # Check that calculator toggle was clicked to open and close/restore
    assert app.click.call_count == 2
    mock_formula_node.iface_value.SetValue.assert_called_once_with(
        "KE = 0.5 * [m] * [v]^2",
    )
    mock_unit_node.iface_value.SetValue.assert_called_once_with("J")
