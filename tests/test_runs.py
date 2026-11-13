# Copyright 2026 Capstone MCP contributors.
"""Tests for the deep Run Management module (capstone_mcp.runs)."""

from unittest.mock import MagicMock

import pytest
from mcp.server.fastmcp import FastMCP

from capstone_mcp.automation_models import NativeRequest
from capstone_mcp.models import Bounds, Control, Snapshot, Window
from capstone_mcp.runs import (
    DeleteRunRequest,
    RenameRunRequest,
    RunAction,
    RunRequest,
    SetRunVisibilityRequest,
    manage_run,
    register_run_tools,
)


def _make_control(
    ref: str,
    name: str,
    control_type: str = "TreeItem",
    *,
    visible: bool = True,
) -> Control:
    return Control(
        ref=ref,
        parent=None,
        name=name,
        control_type=control_type,
        automation_id=f"auto:{ref}",
        enabled=True,
        visible=visible,
        bounds=Bounds(left=0, top=0, right=100, bottom=100),
    )


def _make_mock_app(controls: list[Control]) -> MagicMock:
    app = MagicMock()
    mock_window = Window(
        handle=100,
        title="Capstone",
        process_id=1,
        bounds=Bounds(left=0, top=0, right=800, bottom=600),
    )
    app.snapshot.return_value = Snapshot(
        window=mock_window,
        controls=controls,
        truncated=False,
    )
    app.windows.return_value = [mock_window]
    return app


def test_rename_run_via_unified_manager() -> None:
    # Given: Data Summary has Run #1
    run_ctrl = _make_control(ref="ref:run1", name="Run #1")
    renamed_ctrl = _make_control(ref="ref:run1", name="Baseline Run")
    call_count = 0

    def mock_snapshot(*_args: object, **_kwargs: object) -> Snapshot:
        nonlocal call_count
        call_count += 1
        return Snapshot(
            window=Window(
                handle=100,
                title="Capstone",
                process_id=1,
                bounds=Bounds(left=0, top=0, right=800, bottom=600),
            ),
            controls=[renamed_ctrl if call_count > 1 else run_ctrl],
            truncated=False,
        )

    app = MagicMock()
    app.snapshot = mock_snapshot
    app.windows.return_value = []
    node_mock = MagicMock()
    app.control.return_value = node_mock

    # When: rename to "Baseline Run"
    result = manage_run(
        app,
        RunRequest(
            action=RunAction.RENAME,
            rename=RenameRunRequest(old_name="Run #1", new_name="Baseline Run"),
        ),
    )

    # Then:
    assert result.rename is not None
    assert result.rename.verified is True
    assert result.rename.new_name == "Baseline Run"
    node_mock.iface_value.SetValue.assert_called_once_with("Baseline Run")


def test_delete_run_via_unified_manager() -> None:
    # Given: Data Summary has Run #1 and Run #2
    run1 = _make_control(ref="ref:1", name="Run #1")
    run2 = _make_control(ref="ref:2", name="Run #2")
    app = _make_mock_app([run1, run2])

    # When: delete last run
    result = manage_run(
        app,
        RunRequest(
            action=RunAction.DELETE,
            delete=DeleteRunRequest(run_name="last_run"),
        ),
    )

    # Then:
    assert result.delete is not None
    assert result.delete.verified is True
    assert result.delete.deleted_run == "Run #2"


def test_visibility_toggle_via_unified_manager() -> None:
    # Given: Display container with run checkbox
    disp_ctrl = _make_control(ref="ref:disp", name="Graph 1", control_type="Custom")
    chk_ctrl = _make_control(ref="ref:chk", name="Run #1", control_type="CheckBox")
    app = _make_mock_app([disp_ctrl, chk_ctrl])
    node_mock = MagicMock()
    node_mock.iface_toggle.ToggleState = 0
    app.control.return_value = node_mock

    # When: toggle visibility
    result = manage_run(
        app,
        RunRequest(
            action=RunAction.SET_VISIBILITY,
            visibility=SetRunVisibilityRequest(runs=["Run #1"], visible=True),
        ),
    )

    # Then:
    assert result.visibility is not None
    assert "Run #1" in result.visibility.visible_runs
    node_mock.iface_toggle.Toggle.assert_called_once()


@pytest.mark.anyio
async def test_capstone_manage_run_tool_delegation() -> None:
    """Verify capstone_manage_run delegates correctly via NativeRequest."""
    mcp = FastMCP("test-runs")
    captured_requests: list[NativeRequest] = []

    async def mock_native(
        req: NativeRequest,
        *,
        mutates: bool = False,
    ) -> dict[str, object]:
        del mutates
        captured_requests.append(req)
        return {
            "action": req.run_request["action"],  # pyright: ignore[reportIndexIssue]
            "rename": {
                "old_name": "Run #1",
                "new_name": "Trial 1",
                "verified": True,
                "detail": "Renamed successfully",
            },
        }

    tools = register_run_tools(mcp, mock_native)
    assert "capstone_manage_run" in tools
    manage_tool = tools["capstone_manage_run"]

    result = await manage_tool(
        RunRequest(
            action=RunAction.RENAME,
            rename=RenameRunRequest(old_name="Run #1", new_name="Trial 1"),
        ),
    )

    assert result.action == RunAction.RENAME
    assert result.rename is not None
    assert result.rename.new_name == "Trial 1"
    assert len(captured_requests) == 1
    assert captured_requests[0].operation == "manage_run"
    assert captured_requests[0].run_request["action"] == "rename"  # pyright: ignore[reportIndexIssue]
