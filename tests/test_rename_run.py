# Copyright 2026 Capstone MCP contributors.
"""Tests for dedicated run renaming in Data Summary."""

from unittest.mock import MagicMock

import pytest

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.models import Bounds, Control, Snapshot, Window
from capstone_mcp.run_rename import RenameRunRequest, rename_run


def test_rename_run_rejects_empty_name() -> None:
    app = Capstone()
    req = RenameRunRequest(handle=100, old_name="Run #1", new_name="")
    with pytest.raises(AutomationError, match="new_name"):
        _ = rename_run(app, req)


def test_rename_run_raises_when_run_not_found() -> None:
    app = Capstone()
    mock_window = Window(
        handle=100, title="Capstone", process_id=1,
        bounds=Bounds(left=0, top=0, right=800, bottom=600),
    )
    app.windows = MagicMock(return_value=[mock_window])
    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_window,
        controls=[
            Control(
                ref="ref:1", parent=None, name="Some Other Control",
                control_type="Button", automation_id="btn", enabled=True,
                visible=True, bounds=Bounds(left=0, top=0, right=10, bottom=10),
            ),
        ],
        truncated=False,
    ))

    req = RenameRunRequest(handle=100, old_name="Run #99", new_name="Final Run")
    with pytest.raises(AutomationError, match="not found"):
        _ = rename_run(app, req)


def test_rename_run_direct_value_pattern_success() -> None:
    app = Capstone()
    mock_window = Window(
        handle=100, title="Capstone", process_id=1,
        bounds=Bounds(left=0, top=0, right=800, bottom=600),
    )
    app.windows = MagicMock(return_value=[mock_window])

    initial_treeitem = Control(
        ref="ref:run1", parent=None, name="Run #1",
        control_type="TreeItem", automation_id="run_1", enabled=True,
        visible=True, bounds=Bounds(left=10, top=10, right=100, bottom=30),
    )
    renamed_treeitem = Control(
        ref="ref:run1", parent=None, name="1k Ohm Trial",
        control_type="TreeItem", automation_id="run_1", enabled=True,
        visible=True, bounds=Bounds(left=10, top=10, right=100, bottom=30),
    )

    call_count = 0

    def mock_snapshot(*_args: object, **_kwargs: object) -> Snapshot:
        nonlocal call_count
        call_count += 1
        return Snapshot(
            window=mock_window,
            controls=[renamed_treeitem if call_count > 1 else initial_treeitem],
            truncated=False,
        )

    app.snapshot = mock_snapshot

    mock_node = MagicMock()
    mock_node.iface_value.SetValue = MagicMock()
    app.control = MagicMock(return_value=mock_node)

    req = RenameRunRequest(handle=100, old_name="Run #1", new_name="1k Ohm Trial")
    res = rename_run(app, req)

    assert res.old_name == "Run #1"
    assert res.new_name == "1k Ohm Trial"
    assert res.verified is True
    mock_node.iface_value.SetValue.assert_called_once_with("1k Ohm Trial")
