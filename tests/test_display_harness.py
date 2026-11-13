# Copyright 2026 Capstone MCP contributors.
"""Unit tests for the consolidated DisplayHarness module."""

from unittest.mock import MagicMock

import pytest

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.displays import (
    DisplayHarness,
    click_control,
    double_click_control,
    drag_control,
    find_display_container,
    find_display_containers,
    find_palette_item,
    is_within_bounds,
    set_control_value,
)
from capstone_mcp.models import Action, Bounds, Control


def _make_control(
    ref: str,
    name: str,
    control_type: str = "Custom",
    automation_id: str = "",
    bounds: Bounds | None = None,
) -> Control:
    return Control(
        ref=ref,
        parent=None,
        name=name,
        control_type=control_type,
        automation_id=automation_id or f"id:{ref}",
        enabled=True,
        visible=True,
        bounds=bounds or Bounds(left=10, top=10, right=100, bottom=100),
    )


# ---------------------------------------------------------------------------
# Click and Double-Click Fallback Tests
# ---------------------------------------------------------------------------


def test_click_via_app_click() -> None:
    app = Capstone()
    app.click = MagicMock()
    ctrl = _make_control("ref:1", "Button 1")

    click_control(app, 100, ctrl, allow_foreground=True)

    app.click.assert_called_once_with(100, "ref:1", allow_foreground=True)


def test_click_fallback_to_node_invoke() -> None:
    app = Capstone()
    mock_node = MagicMock()
    app.control = MagicMock(return_value=mock_node)
    ctrl = _make_control("ref:1", "Button 1")

    click_control(app, 100, ctrl)

    mock_node.invoke.assert_called_once()


def test_click_double_fallback_to_click_input() -> None:
    app = Capstone()
    mock_node = MagicMock()
    app.control = MagicMock(return_value=mock_node)
    ctrl = _make_control(
        "ref:1",
        "Palette Item",
        bounds=Bounds(left=0, top=0, right=100, bottom=100),
    )

    double_click_control(app, 100, ctrl)

    mock_node.click_input.assert_called_once_with(
        button="left",
        double=True,
        coords=(50, 50),
        absolute=True,
    )


def test_click_fallback_to_app_act() -> None:
    app = Capstone()
    app.control = MagicMock(side_effect=RuntimeError("no control"))
    app.act = MagicMock()
    ctrl = _make_control("ref:1", "Button 1")

    click_control(app, 100, ctrl)

    app.act.assert_called_once_with(
        100, Action.INVOKE, ref="ref:1", allow_foreground=True,
    )


# ---------------------------------------------------------------------------
# Drag and Value Setting Tests
# ---------------------------------------------------------------------------


def test_drag_via_app_drag() -> None:
    app = Capstone()
    app.drag = MagicMock()
    source = _make_control("ref:src", "Palette Item")
    target = _make_control("ref:dst", "Layout Area")

    drag_control(app, 100, source, target)

    app.drag.assert_called_once_with(
        100, "ref:src", "ref:dst", allow_foreground=True,
    )


def test_drag_fallback_to_drag_mouse() -> None:
    app = Capstone()
    mock_node = MagicMock()
    app.control = MagicMock(return_value=mock_node)
    source = _make_control("ref:src", "Palette Item")
    target = _make_control(
        "ref:dst",
        "Layout Area",
        bounds=Bounds(left=200, top=200, right=400, bottom=400),
    )

    drag_control(app, 100, source, target)

    mock_node.drag_mouse.assert_called_once_with((300, 300))


def test_set_control_value_via_iface_value() -> None:
    app = Capstone()
    mock_node = MagicMock()
    mock_node.iface_value.SetValue = MagicMock()
    app.control = MagicMock(return_value=mock_node)
    ctrl = _make_control("ref:input", "TextBox")

    set_control_value(app, 100, ctrl, "50.0")

    mock_node.iface_value.SetValue.assert_called_once_with("50.0")


def test_set_control_value_fallback_keyboard() -> None:
    app = Capstone()
    app.click = MagicMock()
    app.keys = MagicMock()
    app.type_text = MagicMock()
    mock_node = MagicMock()
    mock_node.iface_value = None
    app.control = MagicMock(return_value=mock_node)
    ctrl = _make_control("ref:input", "TextBox")

    set_control_value(app, 100, ctrl, "100 ms")

    app.click.assert_called_once_with(100, "ref:input", allow_foreground=True)
    app.type_text.assert_called_once_with("100 ms")


# ---------------------------------------------------------------------------
# Bounds and Finding Containers / Palette Tests
# ---------------------------------------------------------------------------


def test_is_within_bounds() -> None:
    outer = _make_control(
        "ref:outer", "Outer",
        bounds=Bounds(left=10, top=10, right=200, bottom=200),
    )
    inner = _make_control(
        "ref:inner", "Inner",
        bounds=Bounds(left=20, top=20, right=100, bottom=100),
    )
    outside = _make_control(
        "ref:outside", "Outside",
        bounds=Bounds(left=0, top=0, right=50, bottom=50),
    )

    assert is_within_bounds(inner, outer) is True
    assert is_within_bounds(outside, outer) is False


def test_find_palette_item_matches_name_or_suffix() -> None:
    item = _make_control(
        "ref:p1", "Scope", control_type="Button",
        automation_id="Displays.ObjNameScope",
    )
    controls = [item]

    found = find_palette_item(controls, "Scope", ".ObjNameScope")
    assert found.ref == "ref:p1"


def test_find_palette_item_missing_raises() -> None:
    controls = [_make_control("ref:p1", "Other", control_type="Button")]

    with pytest.raises(AutomationError, match="not found in window snapshot"):
        _ = find_palette_item(controls, "FFT")


def test_find_display_container_by_type_and_keywords() -> None:
    table = _make_control(
        "ref:tbl", "Data Table", control_type="Table",
        automation_id="TableDisplay",
    )
    graph = _make_control(
        "ref:grp", "Graph 1", control_type="Custom",
        automation_id="GraphDisplay",
    )
    controls = [table, graph]

    found_tbl = find_display_container(controls, "table")
    assert found_tbl.ref == "ref:tbl"

    found_grp = find_display_container(controls, "graph")
    assert found_grp.ref == "ref:grp"


def test_find_display_containers_multiple() -> None:
    c1 = _make_control("ref:1", "Graph 1", control_type="Custom")
    c2 = _make_control("ref:2", "Table 1", control_type="Table")
    c3 = _make_control("ref:3", "Button", control_type="Button")
    controls = [c1, c2, c3]

    found = find_display_containers(controls, ("graph", "table"))
    assert len(found) == 2
    assert {c.ref for c in found} == {"ref:1", "ref:2"}


def test_display_harness_class_interface() -> None:
    app = Capstone()
    app.click = MagicMock()
    harness = DisplayHarness(app)
    ctrl = _make_control("ref:c", "Container")

    harness.click(100, ctrl)
    app.click.assert_called_once_with(100, "ref:c", allow_foreground=True)
    assert harness.is_within_bounds(ctrl, ctrl) is True
