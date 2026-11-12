# Copyright 2026 Capstone MCP contributors.
"""Tests for dedicated run deletion tool in Data Summary."""

from unittest.mock import MagicMock

import pytest

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.models import Bounds, Control, Snapshot, Window
from capstone_mcp.run_delete import DeleteRunRequest, DeleteRunResult, delete_run


def test_delete_run_raises_when_no_runs_exist() -> None:
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

    req = DeleteRunRequest(handle=100, run_name="last_run")
    with pytest.raises(AutomationError, match="No runs found"):
        _ = delete_run(app, req)


def test_delete_run_raises_when_named_run_not_found() -> None:
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
                ref="ref:run1", parent=None, name="Run #1",
                control_type="TreeItem", automation_id="run_1",
                enabled=True, visible=True,
                bounds=Bounds(left=10, top=10, right=100, bottom=30),
            ),
        ],
        truncated=False,
    ))

    req = DeleteRunRequest(handle=100, run_name="Run #99")
    with pytest.raises(AutomationError, match="not found"):
        _ = delete_run(app, req)


def test_delete_run_last_run_success_with_modal_auto_dismiss() -> None:
    app = Capstone()
    main_window = Window(
        handle=100, title="Capstone", process_id=1,
        bounds=Bounds(left=0, top=0, right=1000, bottom=800),
    )
    dialog_window = Window(
        handle=200, title="Delete Run", process_id=1,
        bounds=Bounds(left=300, top=300, right=600, bottom=500),
    )

    run1 = Control(
        ref="ref:run1", parent=None, name="Run #1",
        control_type="TreeItem", automation_id="run_1",
        enabled=True, visible=True,
        bounds=Bounds(left=10, top=10, right=100, bottom=30),
    )
    run2 = Control(
        ref="ref:run2", parent=None, name="Run #2",
        control_type="TreeItem", automation_id="run_2",
        enabled=True, visible=True,
        bounds=Bounds(left=10, top=35, right=100, bottom=55),
    )
    yes_btn = Control(
        ref="ref:yes", parent=None, name="Yes",
        control_type="Button", automation_id="yes_button",
        enabled=True, visible=True,
        bounds=Bounds(left=350, top=450, right=420, bottom=480),
    )

    delete_triggered = False
    confirmed = False

    def mock_windows() -> list[Window]:
        if delete_triggered and not confirmed:
            return [main_window, dialog_window]
        return [main_window]

    def mock_keys(
        _handle: int, key: str, *_args: object, **_kwargs: object,
    ) -> None:
        nonlocal delete_triggered
        if "{DELETE}" in key:
            delete_triggered = True

    def mock_click(
        handle: int, ref: str, *_args: object, **_kwargs: object,
    ) -> None:
        nonlocal confirmed
        if handle == 200 and ref == "ref:yes":
            confirmed = True

    def mock_snapshot(handle: int, *_args: object, **_kwargs: object) -> Snapshot:
        if handle == 200:
            return Snapshot(window=dialog_window, controls=[yes_btn], truncated=False)
        if confirmed:
            return Snapshot(window=main_window, controls=[run1], truncated=False)
        return Snapshot(window=main_window, controls=[run1, run2], truncated=False)

    app.windows = mock_windows
    app.snapshot = mock_snapshot
    app.click = mock_click
    app.keys = mock_keys

    mock_run2_node = MagicMock()
    mock_run2_node.set_focus = MagicMock()
    app.control = MagicMock(return_value=mock_run2_node)

    req = DeleteRunRequest(handle=100, run_name="last_run")
    res = delete_run(app, req)

    assert isinstance(res, DeleteRunResult)
    assert res.deleted_run == "Run #2"
    assert res.verified is True
    assert delete_triggered is True
    assert confirmed is True
