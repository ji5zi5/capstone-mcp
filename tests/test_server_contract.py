# Copyright 2026 Capstone MCP contributors.
"""Regression contract test for capstone_mcp.server public exports."""

import json

import pytest

from capstone_mcp import server
from capstone_mcp.acquisition import RecordingStatus
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


def test_fastmcp_tool_count_contract() -> None:
    """Ensure FastMCP tool count does not regress below full capacity."""
    tools = server.MCP._tool_manager.list_tools()
    tool_names = {t.name for t in tools}
    assert len(tool_names) >= 75
    assert "capstone_attach" in tool_names
    assert "capstone_export_data" in tool_names
    assert "capstone_create_calculation" in tool_names
    assert "capstone_linear_fit" in tool_names
    assert "capstone_manage_graph" in tool_names


def test_systematic_tool_annotations() -> None:
    """Verify readOnlyHint and destructiveHint annotations across MCP tools."""
    tools = {t.name: t for t in server.MCP._tool_manager.list_tools()}

    # 1. Read-only inspection tools
    read_only_tools = [
        "capstone_windows",
        "capstone_snapshot",
        "capstone_read_value",
        "capstone_screenshot",
        "capstone_read_graph",
        "capstone_read_table",
        "capstone_inspect_file",
        "capstone_file_datasets",
        "capstone_extract_dataset",
        "capstone_recording_status",
        "capstone_linear_fit",
        "capstone_scan_wireless_sensors",
        "capstone_read_signal_generator_status",
        "capstone_live_configuration",
        "capstone_current_value",
        "capstone_acquisition_job",
        "capstone_read_fft_peaks",
    ]
    for name in read_only_tools:
        tool = tools[name]
        assert tool.annotations is not None, f"Tool {name} missing annotations"
        assert tool.annotations.readOnlyHint is True, f"Tool {name} expected readOnlyHint=True"

    # 2. Destructive modification tools
    destructive_tools = [
        "capstone_delete_run",
        "capstone_open_experiment",
        "capstone_set_graph_fits",
        "capstone_analyze_graph",
    ]
    for name in destructive_tools:
        tool = tools[name]
        assert tool.annotations is not None, f"Tool {name} missing annotations"
        assert tool.annotations.destructiveHint is True, f"Tool {name} expected destructiveHint=True"

    # 3. Instrument tool annotations systematic completeness
    instrument_tools = [
        "capstone_manage_instrument",
        "capstone_set_recording",
        "capstone_step_sampling_rate",
        "capstone_select_sensor",
        "capstone_configure_sensor",
        "capstone_zero_sensor",
        "capstone_set_signal_generator",
        "capstone_create_scope",
        "capstone_set_scope_trigger",
        "capstone_create_fft",
        "capstone_set_recording_condition",
        "capstone_set_sampling_mode",
        "capstone_keep_sample",
        "capstone_connect_wireless_sensor",
        "capstone_calibrate_sensor",
    ]
    for name in instrument_tools:
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
