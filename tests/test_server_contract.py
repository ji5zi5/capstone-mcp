# Copyright 2026 Capstone MCP contributors.
"""Regression contract test for capstone_mcp.server public exports."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from capstone_mcp import server
from capstone_mcp.acquisition import RecordingStatus
from capstone_mcp.models import Action, Button, Point
from capstone_mcp.repetition import (
    AcquisitionJob,
    JobStatus,
    RepeatPlan,
)


class DummyBackend:
    """Dummy backend for job contract testing."""

    def __init__(self) -> None:
        self.uncertain = False

    def observe(self) -> RecordingStatus:
        return RecordingStatus(running=True, text="Recording")

    def save(self, _path: str) -> None:
        pass

    def close(self) -> None:
        pass


def test_server_public_exports_complete() -> None:
    """Verify all symbols in __all__ exist and match expected callable/object types."""
    assert hasattr(server, "__all__")
    assert len(server.__all__) > 0

    for name in server.__all__:
        assert hasattr(server, name), f"server.__all__ declares {name!r}, but module does not export it"
        obj = getattr(server, name)
        assert obj is not None


def test_acquisition_job_delegation_to_jobs_instance() -> None:
    """Verify that module-level capstone_acquisition_job delegates dynamically to server.JOBS."""
    plan = RepeatPlan(process_id=1, window_handle=1, duration_seconds=1)
    job = AcquisitionJob(plan, DummyBackend())

    server.JOBS.jobs["test_contract_job"] = job
    try:
        retrieved = server.capstone_acquisition_job("test_contract_job")
        status = JobStatus.model_validate(retrieved)
        assert status.job_id == "test_contract_job"
        assert status.state == "running"
    finally:
        server.JOBS.jobs.pop("test_contract_job", None)


def test_fastmcp_tool_surface_ceiling() -> None:
    """Ensure FastMCP tool surface remains bounded within token budget (<= 22 tools)."""
    tools = server.MCP._tool_manager.list_tools()
    tool_names = {t.name for t in tools}
    assert len(tool_names) <= 22
    assert "capstone_attach" in tool_names
    assert "capstone_windows" in tool_names
    assert "capstone_snapshot" in tool_names
    assert "capstone_screenshot" in tool_names
    assert "capstone_interact_ui" in tool_names
    assert "capstone_manage_run" in tool_names
    assert "capstone_manage_graph" in tool_names
    assert "capstone_manage_display" in tool_names
    assert "capstone_manage_instrument" in tool_names
    assert "capstone_save_experiment" in tool_names
    assert "capstone_open_experiment" in tool_names
    assert "capstone_export_data" in tool_names
    assert "capstone_inspect_file" in tool_names
    assert "capstone_file_datasets" in tool_names
    assert "capstone_extract_dataset" in tool_names
    assert "capstone_linear_fit" in tool_names
    assert "capstone_plot" in tool_names
    assert "capstone_compare_runs" in tool_names
    assert "capstone_create_calculation" in tool_names
    assert "capstone_generate_lab_report" in tool_names
    assert "capstone_run_experiment_macro" in tool_names


def test_systematic_tool_annotations() -> None:
    """Verify readOnlyHint and destructiveHint annotations across active MCP tools."""
    tools = {t.name: t for t in server.MCP._tool_manager.list_tools()}

    # 1. Read-only inspection tools
    read_only_tools = [
        "capstone_windows",
        "capstone_snapshot",
        "capstone_screenshot",
        "capstone_inspect_file",
        "capstone_file_datasets",
        "capstone_extract_dataset",
        "capstone_linear_fit",
        "capstone_plot",
        "capstone_compare_runs",
    ]
    for name in read_only_tools:
        tool = tools[name]
        assert tool.annotations is not None, f"Tool {name} missing annotations"
        assert tool.annotations.readOnlyHint is True, f"Tool {name} expected readOnlyHint=True"

    # 2. Destructive modification tools
    destructive_tools = [
        "capstone_open_experiment",
    ]
    for name in destructive_tools:
        tool = tools[name]
        assert tool.annotations is not None, f"Tool {name} missing annotations"
        assert tool.annotations.destructiveHint is True, f"Tool {name} expected destructiveHint=True"

    # 3. Compound and non-destructive management tools
    compound_tools = [
        "capstone_attach",
        "capstone_interact_ui",
        "capstone_manage_instrument",
        "capstone_manage_display",
        "capstone_manage_graph",
        "capstone_manage_run",
        "capstone_save_experiment",
        "capstone_export_data",
        "capstone_create_calculation",
        "capstone_generate_lab_report",
        "capstone_run_experiment_macro",
    ]
    for name in compound_tools:
        tool = tools[name]
        assert tool.annotations is not None, f"Tool {name} missing annotations"
        assert tool.annotations.destructiveHint is False, f"Tool {name} expected destructiveHint=False"


@pytest.mark.anyio
async def test_dynamic_resources_contract() -> None:
    """Verify capstone://status, capstone://runs/active, and capstone://hardware/inventory."""
    resources = {str(r.uri): r for r in server.MCP._resource_manager.list_resources()}
    assert "capstone://status" in resources
    assert "capstone://runs/active" in resources
    assert "capstone://hardware/inventory" in resources
    assert "capstone://displays/active" in resources

    # Status resource read
    status_raw = await server.capstone_status_resource()
    status = json.loads(status_raw)
    assert "attached" in status
    assert "process_id" in status
    assert "windows_count" in status
    assert "active_jobs_count" in status
    assert "last_graph_failure" in status

    # Runs active resource read
    runs_raw = await server.capstone_active_runs_resource()
    runs = json.loads(runs_raw)
    assert "process_id" in runs
    assert "active_jobs" in runs

    # Hardware inventory resource read
    hw_raw = await server.capstone_hardware_inventory_resource()
    hw = json.loads(hw_raw)
    assert "attached" in hw
    assert "interfaces" in hw
    assert "sensors" in hw
    assert "wireless_devices" in hw
    assert "recording" in hw
    assert "sampling_rate" in hw

    # Displays active resource read
    disp_raw = await server.capstone_active_displays_resource()
    disp = json.loads(disp_raw)
    assert "attached" in disp
    assert "process_id" in disp
    assert "active_page" in disp
    assert "pages" in disp
    assert "displays" in disp
    assert "table_count" in disp
    assert "graph_count" in disp
    assert "digits_count" in disp
    assert "scope_count" in disp
    assert "fft_count" in disp


@pytest.mark.anyio
async def test_capstone_interact_ui_dispatch() -> None:
    """Verify capstone_interact_ui correctly dispatches all UI action types."""
    with patch.object(server, "_native", new_callable=AsyncMock) as mock_native:
        mock_native.return_value = {"detail": "success", "delivered": True}

        # 1. Click
        res_click = await server.capstone_interact_ui(
            "click", handle=10, point=Point(x=100, y=200), button=Button.LEFT,
        )
        assert res_click.delivered is True
        mock_native.assert_called_with(
            server.NativeRequest(
                operation="click",
                handle=10,
                point=Point(x=100, y=200),
                button=Button.LEFT,
                double=False,
                allow_foreground=True,
            ),
            mutates=True,
        )

        # 2. Double Click
        await server.capstone_interact_ui(
            "double_click", handle=10, point=Point(x=50, y=60),
        )
        assert mock_native.call_args[0][0].double is True

        # 3. Drag
        await server.capstone_interact_ui(
            "drag", handle=10, start=Point(x=10, y=20), end=Point(x=30, y=40),
        )
        assert mock_native.call_args[0][0].operation == "drag"

        # 4. Scroll
        await server.capstone_interact_ui(
            "scroll", handle=10, point=Point(x=10, y=10), notches=5,
        )
        assert mock_native.call_args[0][0].operation == "scroll"

        # 5. Keys
        await server.capstone_interact_ui(
            "keys", handle=10, keys="{ENTER}",
        )
        assert mock_native.call_args[0][0].operation == "keys"

        # 6. Type
        await server.capstone_interact_ui(
            "type", handle=10, text="sample",
        )
        assert mock_native.call_args[0][0].operation == "keys"
        assert mock_native.call_args[0][0].unicode_input is True

        # 7. Action
        await server.capstone_interact_ui(
            "action", ref="ctrl_1", ui_action=Action.INVOKE,
        )
        assert mock_native.call_args[0][0].operation == "action"

        # 8. Read Value
        mock_native.return_value = "read_text_result"
        res_read = await server.capstone_interact_ui(
            "read_value", ref="ctrl_2",
        )
        assert res_read.detail == "read_text_result"

        # 9. Set Value
        mock_native.return_value = {"detail": "value_set", "delivered": True}
        await server.capstone_interact_ui(
            "set_value", ref="ctrl_3", value="new_text",
        )
        assert mock_native.call_args[0][0].operation == "set_value"

    # 10. Validation errors
    with pytest.raises(ValueError, match="requires both start and end points"):
        await server.capstone_interact_ui("drag", handle=10)

    with pytest.raises(ValueError, match="requires ref"):
        await server.capstone_interact_ui("action", handle=10)

    with pytest.raises(ValueError, match="requires both ref and ui_action"):
        await server.capstone_interact_ui("action", ref="ctrl_1")

    with pytest.raises(ValueError, match="requires ref"):
        await server.capstone_interact_ui("read_value", handle=10)

    with pytest.raises(ValueError, match="requires ref"):
        await server.capstone_interact_ui("set_value", handle=10)
