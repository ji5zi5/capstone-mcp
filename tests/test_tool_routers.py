# Copyright 2026 Capstone MCP contributors.
"""Integration tests verifying domain tool routers and FastMCP registration."""

import pytest
from mcp.server.fastmcp import FastMCP

from capstone_mcp.automation_models import NativeRequest
from capstone_mcp.displays import (
    CreateTableRequest,
    CreateTableResult,
    DisplayAction,
    DisplayRequest,
    DisplayResult,
)
from capstone_mcp.graphs import (
    CreateGraphRequest,
    CreateGraphResult,
    GraphAction,
    GraphRequest,
    GraphResult,
)
from capstone_mcp.instruments import (
    InstrumentAction,
    InstrumentRequest,
    InstrumentResult,
    ZeroSensorRequest,
    ZeroSensorResult,
)
from capstone_mcp.server import MCP, ExportedData
from capstone_mcp.tools import (
    register_display_tools,
    register_file_tools,
    register_instrument_tools,
    register_physics_tools,
)


def test_server_has_all_tool_domains_registered() -> None:
    """Verify that MCP server registers tools from all domain routers."""
    tool_names = {t.name for t in MCP._tool_manager.list_tools()}
    assert len(tool_names) >= 26

    # 1. File tools
    expected_files = {
        "capstone_save_experiment",
        "capstone_open_experiment",
        "capstone_export_data",
        "capstone_csv_page",
        "capstone_inspect_file",
        "capstone_file_datasets",
        "capstone_extract_dataset",
        "capstone_fit_file",
        "capstone_compare_file",
    }
    assert expected_files.issubset(tool_names)

    # 2. Display tools
    expected_displays = {
        "capstone_manage_display",
        "capstone_manage_graph",
        "capstone_create_graph",
        "capstone_select_graph_measurement",
        "capstone_observe_graph",
        "capstone_graph_recovery",
        "capstone_graph_report",
        "capstone_read_graph",
        "capstone_fit_models",
        "capstone_set_graph_fits",
        "capstone_analyze_graph",
        "capstone_fit_graph",
        "capstone_toggle_graph_statistics",
        "capstone_measure_graph_area",
        "capstone_graph_delta",
        "capstone_create_table",
        "capstone_set_table_columns",
        "capstone_read_table",
        "capstone_create_digits",
        "capstone_rename_run",
        "capstone_delete_run",
        "capstone_set_run_visibility",
        "capstone_add_page",
        "capstone_set_page_layout",
    }
    assert expected_displays.issubset(tool_names)

    # 3. Instrument tools
    expected_instruments = {
        "capstone_manage_instrument",
        "capstone_recording_status",
        "capstone_set_recording",
        "capstone_step_sampling_rate",
        "capstone_select_sensor",
        "capstone_configure_sensor",
        "capstone_repeat_acquisition",
        "capstone_acquisition_job",
        "capstone_cancel_acquisition",
        "capstone_zero_sensor",
        "capstone_live_configuration",
        "capstone_current_value",
        "capstone_set_signal_generator",
        "capstone_read_signal_generator_status",
        "capstone_create_scope",
        "capstone_set_scope_trigger",
        "capstone_create_fft",
        "capstone_read_fft_peaks",
        "capstone_set_recording_condition",
        "capstone_set_sampling_mode",
        "capstone_keep_sample",
        "capstone_scan_wireless_sensors",
        "capstone_connect_wireless_sensor",
        "capstone_calibrate_sensor",
    }
    assert expected_instruments.issubset(tool_names)

    # 4. Physics tools
    expected_physics = {
        "capstone_guide",
        "capstone_plot",
        "capstone_linear_fit",
        "capstone_compare_runs",
        "capstone_create_calculation",
        "capstone_generate_lab_report",
        "capstone_run_experiment_macro",
    }
    assert expected_physics.issubset(tool_names)


def test_isolated_router_registration() -> None:
    """Verify each router can independently register tools on a blank FastMCP instance."""

    async def mock_native(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {}

    # File router
    mcp_files = FastMCP("test-files")
    file_tools = register_file_tools(mcp_files, mock_native)
    assert len(file_tools) == 9
    assert len(mcp_files._tool_manager.list_tools()) == 9

    # Display router
    mcp_displays = FastMCP("test-displays")
    display_tools = register_display_tools(
        mcp_displays, mock_native, get_last_failure=lambda: None,
    )
    assert len(display_tools) == 24
    assert len(mcp_displays._tool_manager.list_tools()) == 24
    assert "capstone_manage_graph" in display_tools
    assert "capstone_manage_display" in display_tools

    # Instrument router
    mcp_instruments = FastMCP("test-instruments")
    instrument_tools = register_instrument_tools(mcp_instruments, mock_native)
    assert len(instrument_tools) == 24
    assert len(mcp_instruments._tool_manager.list_tools()) == 24
    assert "capstone_manage_instrument" in instrument_tools

    # Physics router
    mcp_physics = FastMCP("test-physics")
    physics_tools = register_physics_tools(mcp_physics, mock_native)
    assert len(physics_tools) == 7
    assert len(mcp_physics._tool_manager.list_tools()) == 7


def test_exported_data_backward_compatible() -> None:
    """Verify ExportedData can be imported from server module."""
    assert ExportedData is not None


@pytest.mark.anyio
async def test_manage_graph_tool_delegation() -> None:
    """Verify capstone_manage_graph invokes native with operation='manage_graph'."""
    captured_requests: list[NativeRequest] = []

    async def mock_native(
        req: NativeRequest,
        *_args: object,
        **_kwargs: object,
    ) -> dict[str, object]:
        captured_requests.append(req)
        return GraphResult(
            action=GraphAction.CREATE,
            create=CreateGraphResult(detail="Graph created", verified=True),
        ).model_dump()

    mcp = FastMCP("test-manage-graph")
    tools = register_display_tools(mcp, mock_native)
    manage_fn = tools["capstone_manage_graph"]

    res = await manage_fn(
        GraphRequest(
            action=GraphAction.CREATE,
            create=CreateGraphRequest(handle=42),
        ),
    )
    assert isinstance(res, GraphResult)
    assert len(captured_requests) == 1
    assert captured_requests[0].operation == "manage_graph"
    assert captured_requests[0].graph_request["action"] == "create"


@pytest.mark.anyio
async def test_legacy_graph_tools_delegate_to_manage_graph() -> None:
    """Verify legacy tool capstone_create_graph delegates to manage_graph."""
    captured_requests: list[NativeRequest] = []

    async def mock_native(
        req: NativeRequest,
        *_args: object,
        **_kwargs: object,
    ) -> dict[str, object]:
        captured_requests.append(req)
        return GraphResult(
            action=GraphAction.CREATE,
            create=CreateGraphResult(detail="Legacy created", verified=True),
        ).model_dump()

    mcp = FastMCP("test-legacy-graph")
    tools = register_display_tools(mcp, mock_native)
    create_fn = tools["capstone_create_graph"]

    res = await create_fn(handle=100)
    assert res.delivered is True
    assert res.detail == "Legacy created"
    assert len(captured_requests) == 1
    assert captured_requests[0].operation == "manage_graph"
    assert captured_requests[0].graph_request["action"] == "create"


@pytest.mark.anyio
async def test_manage_instrument_tool_delegation() -> None:
    """Verify capstone_manage_instrument invokes native with 'manage_instrument'."""
    captured_requests: list[NativeRequest] = []

    async def mock_native(
        req: NativeRequest,
        *_args: object,
        **_kwargs: object,
    ) -> dict[str, object]:
        captured_requests.append(req)
        return InstrumentResult(
            action=InstrumentAction.ZERO_SENSOR,
            zero_sensor=ZeroSensorResult(
                zeroed_sensors=["Force Sensor"],
                verified=True,
                detail="Zeroed",
            ),
        ).model_dump()

    mcp = FastMCP("test-manage-instrument")
    tools = register_instrument_tools(mcp, mock_native)
    manage_fn = tools["capstone_manage_instrument"]

    res = await manage_fn(
        InstrumentRequest(
            action=InstrumentAction.ZERO_SENSOR,
            zero_sensor=ZeroSensorRequest(handle=42, sensor_name="Force Sensor"),
        ),
    )
    assert isinstance(res, InstrumentResult)
    assert len(captured_requests) == 1
    assert captured_requests[0].operation == "manage_instrument"
    assert captured_requests[0].instrument_request["action"] == "zero_sensor"


@pytest.mark.anyio
async def test_legacy_instrument_tools_delegate_to_manage_instrument() -> None:
    """Verify legacy tool capstone_zero_sensor delegates to manage_instrument."""
    captured_requests: list[NativeRequest] = []

    async def mock_native(
        req: NativeRequest,
        *_args: object,
        **_kwargs: object,
    ) -> dict[str, object]:
        captured_requests.append(req)
        return InstrumentResult(
            action=InstrumentAction.ZERO_SENSOR,
            zero_sensor=ZeroSensorResult(
                zeroed_sensors=["Force Sensor"],
                verified=True,
                detail="Legacy zeroed",
            ),
        ).model_dump()

    mcp = FastMCP("test-legacy-instrument")
    tools = register_instrument_tools(mcp, mock_native)
    zero_fn = tools["capstone_zero_sensor"]

    res = await zero_fn(handle=100, sensor_name="Force Sensor")
    assert res.verified is True
    assert res.detail == "Legacy zeroed"
    assert len(captured_requests) == 1
    assert captured_requests[0].operation == "manage_instrument"
    assert captured_requests[0].instrument_request["action"] == "zero_sensor"


@pytest.mark.anyio
async def test_manage_display_tool_delegation() -> None:
    """Verify capstone_manage_display invokes native with 'manage_display'."""
    captured_requests: list[NativeRequest] = []

    async def mock_native(
        req: NativeRequest,
        *_args: object,
        **_kwargs: object,
    ) -> dict[str, object]:
        captured_requests.append(req)
        return DisplayResult(
            action=DisplayAction.CREATE_TABLE,
            create_table=CreateTableResult(
                table_id="Table_1",
                name="Table 1",
                verified=True,
                detail="Table created",
            ),
        ).model_dump()

    mcp = FastMCP("test-manage-display")
    tools = register_display_tools(mcp, mock_native)
    manage_fn = tools["capstone_manage_display"]

    res = await manage_fn(
        DisplayRequest(
            action=DisplayAction.CREATE_TABLE,
            create_table=CreateTableRequest(handle=42, table_name="Table 1"),
        ),
    )
    assert isinstance(res, DisplayResult)
    assert len(captured_requests) == 1
    assert captured_requests[0].operation == "manage_display"
    assert captured_requests[0].display_request["action"] == "create_table"


@pytest.mark.anyio
async def test_legacy_display_tools_delegate_to_manage_display() -> None:
    """Verify legacy tool capstone_create_table delegates to manage_display."""
    captured_requests: list[NativeRequest] = []

    async def mock_native(
        req: NativeRequest,
        *_args: object,
        **_kwargs: object,
    ) -> dict[str, object]:
        captured_requests.append(req)
        return DisplayResult(
            action=DisplayAction.CREATE_TABLE,
            create_table=CreateTableResult(
                table_id="Table_1",
                name="Table 1",
                verified=True,
                detail="Legacy table created",
            ),
        ).model_dump()

    mcp = FastMCP("test-legacy-display")
    tools = register_display_tools(mcp, mock_native)
    create_table_fn = tools["capstone_create_table"]

    res = await create_table_fn(handle=100, table_name="Table 1")
    assert res.verified is True
    assert res.detail == "Legacy table created"
    assert len(captured_requests) == 1
    assert captured_requests[0].operation == "manage_display"
    assert captured_requests[0].display_request["action"] == "create_table"
