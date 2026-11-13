# Copyright 2026 Capstone MCP contributors.
"""Tests for run visibility and multi-run overlay comparison tool."""

from unittest.mock import MagicMock

import pytest

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.models import Bounds, Control, Snapshot, Window
from capstone_mcp.runs import (
    SetRunVisibilityRequest,
    SetRunVisibilityResult,
    set_run_visibility,
)


def _make_window() -> Window:
    return Window(
        handle=100,
        title="Capstone",
        process_id=1,
        bounds=Bounds(left=0, top=0, right=1200, bottom=900),
    )


def test_set_run_visibility_rejects_empty_runs() -> None:
    app = Capstone()
    req = SetRunVisibilityRequest(handle=100, runs=[])
    with pytest.raises(AutomationError, match="runs must not be empty"):
        _ = set_run_visibility(app, req)


def test_set_run_visibility_requires_foreground() -> None:
    app = Capstone()
    req = SetRunVisibilityRequest(handle=100, runs=["Run #1"], allow_foreground=False)
    with pytest.raises(AutomationError, match="allow_foreground"):
        _ = set_run_visibility(app, req)


def test_set_run_visibility_raises_when_target_display_not_found() -> None:
    app = Capstone()
    mock_win = _make_window()
    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_win,
        controls=[
            Control(
                ref="ref:g1", parent=None, name="Graph 1",
                control_type="Pane", automation_id="graph_pane_1",
                enabled=True, visible=True,
                bounds=Bounds(left=0, top=0, right=500, bottom=500),
            ),
        ],
        truncated=False,
    ))

    req = SetRunVisibilityRequest(
        handle=100,
        runs=["Run #1"],
        target_displays=["Nonexistent Table"],
    )
    with pytest.raises(AutomationError, match="Target display 'Nonexistent Table'"):
        _ = set_run_visibility(app, req)


def test_set_run_visibility_raises_when_run_control_not_found() -> None:
    app = Capstone()
    mock_win = _make_window()
    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_win,
        controls=[
            Control(
                ref="ref:run1", parent=None, name="Run #1",
                control_type="CheckBox", automation_id="run_1_check",
                enabled=True, visible=True,
                bounds=Bounds(left=10, top=10, right=100, bottom=30),
            ),
        ],
        truncated=False,
    ))

    req = SetRunVisibilityRequest(handle=100, runs=["Run #99"])
    with pytest.raises(AutomationError, match="Run visibility control for 'Run #99'"):
        _ = set_run_visibility(app, req)


def test_set_run_visibility_success_toggle_pattern() -> None:
    app = Capstone()
    mock_win = _make_window()

    ctrl_run1 = Control(
        ref="ref:run1", parent=None, name="Run #1",
        control_type="CheckBox", automation_id="run_1_check",
        enabled=True, visible=True,
        bounds=Bounds(left=10, top=10, right=100, bottom=30),
    )
    ctrl_run2 = Control(
        ref="ref:run2", parent=None, name="Run #2",
        control_type="CheckBox", automation_id="run_2_check",
        enabled=True, visible=True,
        bounds=Bounds(left=10, top=35, right=100, bottom=55),
    )

    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_win,
        controls=[ctrl_run1, ctrl_run2],
        truncated=False,
    ))

    node_run1 = MagicMock()
    node_run1.iface_toggle.ToggleState = 0  # initially hidden

    node_run2 = MagicMock()
    node_run2.iface_toggle.ToggleState = 0  # initially hidden

    def mock_control(ref: str) -> MagicMock:
        if ref == "ref:run1":
            return node_run1
        if ref == "ref:run2":
            return node_run2
        return MagicMock()

    app.control = mock_control

    req = SetRunVisibilityRequest(handle=100, runs=["Run #1", "Run #2"], visible=True)
    result = set_run_visibility(app, req)

    assert isinstance(result, SetRunVisibilityResult)
    assert result.verified is True
    assert "Run #1" in result.visible_runs
    assert "Run #2" in result.visible_runs
    assert node_run1.iface_toggle.Toggle.call_count == 1
    assert node_run2.iface_toggle.Toggle.call_count == 1


def test_set_run_visibility_hide_run_success() -> None:
    app = Capstone()
    mock_win = _make_window()

    ctrl_run1 = Control(
        ref="ref:run1", parent=None, name="Run #1",
        control_type="CheckBox", automation_id="run_1_check",
        enabled=True, visible=True,
        bounds=Bounds(left=10, top=10, right=100, bottom=30),
    )
    ctrl_run2 = Control(
        ref="ref:run2", parent=None, name="Run #2",
        control_type="CheckBox", automation_id="run_2_check",
        enabled=True, visible=True,
        bounds=Bounds(left=10, top=35, right=100, bottom=55),
    )

    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_win,
        controls=[ctrl_run1, ctrl_run2],
        truncated=False,
    ))

    node_run1 = MagicMock()
    node_run1.iface_toggle.ToggleState = 1  # visible

    node_run2 = MagicMock()
    node_run2.iface_toggle.ToggleState = 1  # visible

    def mock_control(ref: str) -> MagicMock:
        if ref == "ref:run1":
            return node_run1
        if ref == "ref:run2":
            return node_run2
        return MagicMock()

    app.control = mock_control

    req = SetRunVisibilityRequest(handle=100, runs=["Run #1"], visible=False)
    result = set_run_visibility(app, req)

    assert isinstance(result, SetRunVisibilityResult)
    assert result.verified is True
    assert "Run #1" not in result.visible_runs
    assert "Run #2" in result.visible_runs
    node_run1.iface_toggle.Toggle.assert_called_once()
    node_run2.iface_toggle.Toggle.assert_not_called()


def test_set_run_visibility_target_specific_display_bounds() -> None:
    app = Capstone()
    mock_win = _make_window()

    graph_ctrl = Control(
        ref="ref:graph1", parent=None, name="Graph 1",
        control_type="Pane", automation_id="graph_container",
        enabled=True, visible=True,
        bounds=Bounds(left=0, top=0, right=400, bottom=400),
    )
    table_ctrl = Control(
        ref="ref:table1", parent=None, name="Table 1",
        control_type="Pane", automation_id="table_container",
        enabled=True, visible=True,
        bounds=Bounds(left=450, top=0, right=850, bottom=400),
    )
    # run1 inside Graph 1
    graph_run1 = Control(
        ref="ref:g_run1", parent="ref:graph1", name="Run #1",
        control_type="CheckBox", automation_id="g_run_1",
        enabled=True, visible=True,
        bounds=Bounds(left=10, top=10, right=80, bottom=30),
    )
    # run1 inside Table 1
    table_run1 = Control(
        ref="ref:t_run1", parent="ref:table1", name="Run #1",
        control_type="CheckBox", automation_id="t_run_1",
        enabled=True, visible=True,
        bounds=Bounds(left=460, top=10, right=530, bottom=30),
    )

    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_win,
        controls=[graph_ctrl, table_ctrl, graph_run1, table_run1],
        truncated=False,
    ))

    node_g_run1 = MagicMock()
    node_g_run1.iface_toggle.ToggleState = 0
    node_t_run1 = MagicMock()
    node_t_run1.iface_toggle.ToggleState = 0

    def mock_control(ref: str) -> MagicMock:
        if ref == "ref:g_run1":
            return node_g_run1
        if ref == "ref:t_run1":
            return node_t_run1
        return MagicMock()

    app.control = mock_control

    # Target only Graph 1
    req = SetRunVisibilityRequest(
        handle=100,
        runs=["Run #1"],
        visible=True,
        target_displays=["Graph 1"],
    )
    result = set_run_visibility(app, req)

    assert result.target_displays == ["Graph 1"]
    node_g_run1.iface_toggle.Toggle.assert_called_once()
    node_t_run1.iface_toggle.Toggle.assert_not_called()
