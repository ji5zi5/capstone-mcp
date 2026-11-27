# Copyright 2026 Capstone MCP contributors.
"""Regression contract test for capstone_mcp.server public exports."""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from capstone_mcp import resources as resource_module
from capstone_mcp import server
from capstone_mcp.acquisition import RecordingStatus
from capstone_mcp.bridge import NativeInventory
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


@pytest.mark.parametrize("program", ["capstone-mcp", "capstone-mcp-http"])
def test_help_exits_before_starting_a_transport(
    program: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    run = Mock()
    monkeypatch.setattr(server.MCP, "run", run)
    monkeypatch.setattr(sys, "argv", [program, "--help"])
    command = server.main if program == "capstone-mcp" else server.http_main
    with pytest.raises(SystemExit) as exit_info:
        command()
    assert exit_info.value.code == 0
    assert program in capsys.readouterr().out
    run.assert_not_called()


def test_http_port_can_change_while_binding_stays_local(monkeypatch: pytest.MonkeyPatch) -> None:
    run = Mock()
    monkeypatch.setattr(server.MCP, "run", run)
    monkeypatch.setattr(server.MCP.settings, "port", 8766)
    monkeypatch.setattr(sys, "argv", ["capstone-mcp-http", "--port", "9001"])
    server.http_main()
    assert server.MCP.settings.port == 9001
    assert server.MCP.settings.host == "127.0.0.1"
    run.assert_called_once_with(transport="streamable-http")


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
        "capstone_manage_run",
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


    # 4. Enforce OpenAI / m8ven directory compliance: all four hints must be explicit booleans
    for name, tool in tools.items():
        assert tool.annotations is not None, f"Tool {name} missing annotations"
        assert isinstance(
            tool.annotations.readOnlyHint, bool,
        ), f"Tool {name} missing boolean readOnlyHint"
        assert isinstance(
            tool.annotations.destructiveHint, bool,
        ), f"Tool {name} missing boolean destructiveHint"
        assert isinstance(
            tool.annotations.idempotentHint, bool,
        ), f"Tool {name} missing boolean idempotentHint"
        assert isinstance(
            tool.annotations.openWorldHint, bool,
        ), f"Tool {name} missing boolean openWorldHint"


def test_license_file_and_metadata_present() -> None:
    """Verify LICENSE file and pyproject.toml license metadata exist."""
    repo_root = Path(__file__).resolve().parent.parent
    license_file = repo_root / "LICENSE"
    assert license_file.exists(), "LICENSE file must exist in repository root"
    content = license_file.read_text(encoding="utf-8")
    assert "MIT License" in content
    assert "Capstone MCP contributors" in content

    pyproject_file = repo_root / "pyproject.toml"
    pyproject_content = pyproject_file.read_text(encoding="utf-8")
    assert 'license = "MIT"' in pyproject_content
    assert 'license-files = ["LICENSE"]' in pyproject_content


@pytest.mark.anyio
async def test_dynamic_resources_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify capstone://status, capstone://runs/active, and capstone://hardware/inventory."""
    session = Mock(debug_port=9222)
    session.read_live_inventory.return_value = NativeInventory(
        sensors=[], measurements=[],
    )
    monkeypatch.setattr(resource_module, "UnifiedSessionManager", Mock(return_value=session))
    monkeypatch.setattr(server, "_native", AsyncMock(return_value=[]))
    resources = {str(r.uri): r for r in server.MCP._resource_manager.list_resources()}
    assert "capstone://status" in resources
    assert "capstone://runs/active" in resources
    assert "capstone://hardware/inventory" in resources
    assert "capstone://displays/active" in resources
    assert "capstone://measurements/live" in resources

    # Status resource read
    status_raw = await server.capstone_status_resource()
    status = json.loads(status_raw)
    assert status["version"] == server.__version__
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

    # Live measurements resource read
    live_raw = await server.capstone_live_measurements_resource()
    live = json.loads(live_raw)
    assert "status" in live
    assert "sensors" in live
    assert "measurements" in live

    assert "fft_count" in disp


@pytest.mark.anyio
async def test_interact_ui_omission_never_moves_foreground() -> None:
    with patch.object(server, "_native", new_callable=AsyncMock) as native:
        native.return_value = {"detail": "unexpected input"}
        with pytest.raises(ValueError, match="allow_foreground=true"):
            await server.capstone_interact_ui(
                "click", handle=10, point=Point(x=5, y=5),
            )
        with pytest.raises(ValueError, match="allow_foreground=true"):
            await server.capstone_interact_ui("keys", handle=10, keys="{ENTER}")
        with pytest.raises(ValueError, match="allow_foreground=true"):
            await server.capstone_interact_ui(
                "action", ref="target", ui_action=Action.FOCUS,
            )
        native.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("action", ["click", "double_click", "scroll"])
async def test_interact_ui_requires_point_before_sending_mouse_input(action: str) -> None:
    with patch.object(server, "_native", new_callable=AsyncMock) as native:
        with pytest.raises(ValueError, match="explicit point"):
            await server.capstone_interact_ui(action, handle=10, allow_foreground=True)
        native.assert_not_awaited()


@pytest.mark.anyio
async def test_ui_value_write_requires_explicit_value_but_allows_clearing() -> None:
    with patch.object(server.WORKER, "call", return_value={"detail": "value written"}) as call:
        with pytest.raises(ValueError, match="explicit value"):
            await server.capstone_interact_ui("set_value", ref="editor")
        call.assert_not_called()

        await server.capstone_interact_ui("set_value", ref="editor", value="")
        request = call.call_args.args[0]
        assert (request.operation, request.ref, request.value) == ("set_value", "editor", "")


@pytest.mark.anyio
async def test_capstone_interact_ui_dispatch() -> None:
    """Verify capstone_interact_ui correctly dispatches all UI action types."""
    with patch.object(server, "_native", new_callable=AsyncMock) as mock_native:
        mock_native.return_value = {"detail": "success", "delivered": True}

        # 1. Click
        res_click = await server.capstone_interact_ui(
            "click", handle=10, point=Point(x=100, y=200), button=Button.LEFT,
            allow_foreground=True,
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
            allow_foreground=True,
        )
        assert mock_native.call_args[0][0].double is True

        # 3. Drag
        await server.capstone_interact_ui(
            "drag", handle=10, start=Point(x=10, y=20), end=Point(x=30, y=40),
            allow_foreground=True,
        )
        assert mock_native.call_args[0][0].operation == "drag"

        # 4. Scroll
        await server.capstone_interact_ui(
            "scroll", handle=10, point=Point(x=10, y=10), notches=5,
            allow_foreground=True,
        )
        assert mock_native.call_args[0][0].operation == "scroll"

        # 5. Keys
        await server.capstone_interact_ui(
            "keys", handle=10, keys="{ENTER}",
            allow_foreground=True,
        )
        assert mock_native.call_args[0][0].operation == "keys"

        # 6. Type
        await server.capstone_interact_ui(
            "type", handle=10, text="sample",
            allow_foreground=True,
        )
        assert mock_native.call_args[0][0].operation == "keys"
        assert mock_native.call_args[0][0].unicode_input is True

        # 7. Action
        await server.capstone_interact_ui(
            "action", ref="ctrl_1", ui_action=Action.INVOKE,
            allow_foreground=True,
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
