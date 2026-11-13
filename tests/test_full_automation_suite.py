# Copyright 2026 Capstone MCP contributors.
"""Integration verification for all 22 operations across Tickets #32-#40."""

from unittest.mock import patch

import pytest

from capstone_mcp.automation_models import NativeRequest
from capstone_mcp.displays import (
    AddPageResult,
    CreateDigitsResult,
    CreateFftResult,
    CreateScopeResult,
    CreateTableResult,
    DisplayAction,
    DisplayResult,
    ReadFftPeaksResult,
    ReadTableResult,
    ScopeTriggerResult,
    SetPageLayoutResult,
    SetTableColumnsResult,
)
from capstone_mcp.graphs import (
    GraphDeltaResult,
    MeasureGraphAreaResult,
    ToggleGraphStatisticsResult,
)
from capstone_mcp.instruments import (
    CalibrateSensorResult,
    ConnectWirelessSensorResult,
    InstrumentAction,
    InstrumentResult,
    KeepSampleResult,
    ScanWirelessSensorsResult,
    SetRecordingConditionResult,
    SetSamplingModeResult,
    SetSignalGeneratorResult,
    SignalGeneratorStatusResult,
)
from capstone_mcp.native_loop import NativeDesktop
from capstone_mcp.runs import SetRunVisibilityResult
from capstone_mcp.server import MCP

NEW_TOOLS = [
    "capstone_create_table",
    "capstone_set_table_columns",
    "capstone_read_table",
    "capstone_create_digits",
    "capstone_toggle_graph_statistics",
    "capstone_measure_graph_area",
    "capstone_graph_delta",
    "capstone_set_run_visibility",
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
    "capstone_add_page",
    "capstone_set_page_layout",
]


@pytest.mark.anyio
async def test_all_22_new_tools_registered_on_server() -> None:
    """Ensure all 22 high-level tools are registered on FastMCP."""
    tools = await MCP.list_tools()
    tool_names = {t.name for t in tools}
    for tool_name in NEW_TOOLS:
        msg = f"Tool {tool_name} was not registered on MCP server"
        assert tool_name in tool_names, msg


def test_dispatch_table_and_digits_operations() -> None:
    desktop = NativeDesktop()

    with patch("capstone_mcp.native_loop.manage_display") as mock_md:
        mock_md.return_value = DisplayResult(
            action=DisplayAction.CREATE_TABLE,
            create_table=CreateTableResult(
                created=True, table_name="Table 1",
            ),
        )
        res = desktop.dispatch(NativeRequest(
            operation="create_table", table_name="Table 1",
        ))
        assert res["created"] is True
        mock_md.assert_called_once()

    with patch("capstone_mcp.native_loop.manage_display") as mock_md:
        mock_md.return_value = DisplayResult(
            action=DisplayAction.SET_TABLE_COLUMNS,
            set_table_columns=SetTableColumnsResult(
                table_name="Table", columns=["Time"], column_count=1,
            ),
        )
        res = desktop.dispatch(NativeRequest(
            operation="set_table_columns", columns=["Time"],
        ))
        assert res["column_count"] == 1
        mock_md.assert_called_once()

    with patch("capstone_mcp.native_loop.manage_display") as mock_md:
        mock_md.return_value = DisplayResult(
            action=DisplayAction.READ_TABLE,
            read_table=ReadTableResult(
                columns=["Time"], rows=[], total_rows=0,
                page=1, page_size=50, total_pages=0,
            ),
        )
        res = desktop.dispatch(NativeRequest(operation="read_table"))
        assert res["columns"] == ["Time"]
        mock_md.assert_called_once()

    with patch("capstone_mcp.native_loop.manage_display") as mock_md:
        mock_md.return_value = DisplayResult(
            action=DisplayAction.CREATE_DIGITS,
            create_digits=CreateDigitsResult(
                created=True, digits_name="Digits 1",
            ),
        )
        res = desktop.dispatch(NativeRequest(
            operation="create_digits", digits_name="Digits 1",
        ))
        assert res["created"] is True
        mock_md.assert_called_once()


def test_dispatch_graph_toolbox_and_visibility() -> None:
    desktop = NativeDesktop()

    with patch("capstone_mcp.native_loop.toggle_graph_statistics") as mock_tgs:
        mock_tgs.return_value = ToggleGraphStatisticsResult(visible=True)
        res = desktop.dispatch(NativeRequest(
            operation="toggle_graph_statistics", enable=True,
        ))
        assert res["visible"] is True
        mock_tgs.assert_called_once()

    with patch("capstone_mcp.native_loop.measure_graph_area") as mock_mga:
        mock_mga.return_value = MeasureGraphAreaResult(visible=True, area=42.0)
        res = desktop.dispatch(NativeRequest(operation="measure_graph_area"))
        assert res["area"] == 42.0
        mock_mga.assert_called_once()

    with patch("capstone_mcp.native_loop.graph_delta") as mock_gd:
        mock_gd.return_value = GraphDeltaResult(
            active=True, delta_x=1.0, delta_y=2.0,
        )
        res = desktop.dispatch(NativeRequest(operation="graph_delta"))
        assert res["delta_x"] == 1.0
        mock_gd.assert_called_once()

    with patch("capstone_mcp.native_loop.set_run_visibility") as mock_srv:
        mock_srv.return_value = SetRunVisibilityResult(
            visible_runs=["Run #1"], target_displays=[], detail="",
        )
        res = desktop.dispatch(NativeRequest(
            operation="set_run_visibility", runs=["Run #1"],
        ))
        assert res["visible_runs"] == ["Run #1"]
        mock_srv.assert_called_once()


def test_dispatch_signal_generator_and_scope_fft() -> None:
    desktop = NativeDesktop()

    with patch("capstone_mcp.native_loop.manage_instrument") as mock_mi:
        mock_mi.return_value = InstrumentResult(
            action=InstrumentAction.CONFIGURE_SIGNAL_GENERATOR,
            configure_signal_generator=SetSignalGeneratorResult(
                generator_name="Output 1",
                waveform="Sine",
                frequency=1000.0,
                amplitude=1.0,
                enabled=True,
            ),
        )
        res = desktop.dispatch(
            NativeRequest(
                operation="set_signal_generator",
                waveform="Sine",
            ),
        )
        assert res["waveform"] == "Sine"
        mock_mi.assert_called_once()

    with patch("capstone_mcp.native_loop.manage_instrument") as mock_mi:
        mock_mi.return_value = InstrumentResult(
            action=InstrumentAction.CONFIGURE_SIGNAL_GENERATOR,
            configure_signal_generator=SignalGeneratorStatusResult(
                generator_name="Output 1",
                enabled=True,
                waveform="Sine",
                frequency=1000.0,
                amplitude=1.0,
            ),
        )
        res = desktop.dispatch(NativeRequest(operation="read_signal_generator_status"))
        assert res["enabled"] is True
        mock_mi.assert_called_once()

    with patch("capstone_mcp.native_loop.manage_display") as mock_md:
        mock_md.return_value = DisplayResult(
            action=DisplayAction.CREATE_SCOPE,
            create_scope=CreateScopeResult(
                display_id="Scope_1",
                display_type="Scope",
            ),
        )
        res = desktop.dispatch(
            NativeRequest(
                operation="create_scope",
                timebase="10ms",
            ),
        )
        assert res["display_id"] == "Scope_1"
        mock_md.assert_called_once()

    with patch("capstone_mcp.native_loop.manage_display") as mock_md:
        mock_md.return_value = DisplayResult(
            action=DisplayAction.SET_SCOPE_TRIGGER,
            set_scope_trigger=ScopeTriggerResult(
                scope_id="Scope_1",
                trigger_level=0.5,
                trigger_slope="rising",
                trigger_mode="auto",
            ),
        )
        res = desktop.dispatch(
            NativeRequest(
                operation="set_scope_trigger",
                trigger_level=0.5,
            ),
        )
        assert res["trigger_level"] == 0.5
        mock_md.assert_called_once()

    with patch("capstone_mcp.native_loop.manage_display") as mock_md:
        mock_md.return_value = DisplayResult(
            action=DisplayAction.CREATE_FFT,
            create_fft=CreateFftResult(
                display_id="FFT_1",
                display_type="FFT",
            ),
        )
        res = desktop.dispatch(NativeRequest(operation="create_fft"))
        assert res["display_id"] == "FFT_1"
        mock_md.assert_called_once()

    with patch("capstone_mcp.native_loop.manage_display") as mock_md:
        mock_md.return_value = DisplayResult(
            action=DisplayAction.READ_FFT_PEAKS,
            read_fft_peaks=ReadFftPeaksResult(
                fft_id="FFT_1",
                peaks=[],
                peak_count=0,
            ),
        )
        res = desktop.dispatch(
            NativeRequest(
                operation="read_fft_peaks",
                top_k=3,
            ),
        )
        assert res["peak_count"] == 0
        mock_md.assert_called_once()


def test_dispatch_triggers_calibration_and_layout() -> None:
    desktop = NativeDesktop()

    with patch("capstone_mcp.native_loop.manage_instrument") as mock_mi:
        mock_mi.return_value = InstrumentResult(
            action=InstrumentAction.SET_RECORDING_CONDITION,
            set_recording_condition=SetRecordingConditionResult(),
        )
        res = desktop.dispatch(NativeRequest(operation="set_recording_condition"))
        assert res["verified"] is True
        mock_mi.assert_called_once()

    with patch("capstone_mcp.native_loop.manage_instrument") as mock_mi:
        mock_mi.return_value = InstrumentResult(
            action=InstrumentAction.SET_SAMPLING_MODE,
            set_sampling_mode=SetSamplingModeResult(mode="keep_sample"),
        )
        res = desktop.dispatch(
            NativeRequest(
                operation="set_sampling_mode",
                sampling_mode="keep_sample",
            ),
        )
        assert res["mode"] == "keep_sample"
        mock_mi.assert_called_once()

    with patch("capstone_mcp.native_loop.manage_instrument") as mock_mi:
        mock_mi.return_value = InstrumentResult(
            action=InstrumentAction.KEEP_SAMPLE,
            keep_sample=KeepSampleResult(recorded_value=3.14),
        )
        res = desktop.dispatch(
            NativeRequest(
                operation="keep_sample",
                sample_value=3.14,
            ),
        )
        assert res["recorded_value"] == 3.14
        mock_mi.assert_called_once()

    with patch("capstone_mcp.native_loop.manage_instrument") as mock_mi:
        mock_mi.return_value = InstrumentResult(
            action=InstrumentAction.SCAN_WIRELESS,
            scan_wireless=ScanWirelessSensorsResult(sensors=[], count=0),
        )
        res = desktop.dispatch(NativeRequest(operation="scan_wireless_sensors"))
        assert res["count"] == 0
        mock_mi.assert_called_once()

    with patch("capstone_mcp.native_loop.manage_instrument") as mock_mi:
        mock_mi.return_value = InstrumentResult(
            action=InstrumentAction.CONNECT_WIRELESS,
            connect_wireless=ConnectWirelessSensorResult(
                sensor_id="Sensor_1",
                name="Smart Cart",
            ),
        )
        res = desktop.dispatch(
            NativeRequest(
                operation="connect_wireless_sensor",
                sensor_id="Sensor_1",
            ),
        )
        assert res["sensor_id"] == "Sensor_1"
        mock_mi.assert_called_once()

    with patch("capstone_mcp.native_loop.manage_instrument") as mock_mi:
        mock_mi.return_value = InstrumentResult(
            action=InstrumentAction.CALIBRATE_SENSOR,
            calibrate_sensor=CalibrateSensorResult(
                sensor_name="Force",
                measurement_type="Force",
                calibration_type="two_point",
                standard_1=0.0,
            ),
        )
        res = desktop.dispatch(
            NativeRequest(
                operation="calibrate_sensor",
                sensor_name="Force",
            ),
        )
        assert res["sensor_name"] == "Force"
        mock_mi.assert_called_once()

    with patch("capstone_mcp.native_loop.manage_display") as mock_md:
        mock_md.return_value = DisplayResult(
            action=DisplayAction.ADD_PAGE,
            add_page=AddPageResult(page_index=1, title="Page 2"),
        )
        res = desktop.dispatch(NativeRequest(operation="add_page", title="Page 2"))
        assert res["title"] == "Page 2"
        mock_md.assert_called_once()

    with patch("capstone_mcp.native_loop.manage_display") as mock_md:
        mock_md.return_value = DisplayResult(
            action=DisplayAction.SET_PAGE_LAYOUT,
            set_page_layout=SetPageLayoutResult(
                layout="two_vertical", areas_created=2,
            ),
        )
        res = desktop.dispatch(NativeRequest(
            operation="set_page_layout", layout="two_vertical",
        ))
        assert res["areas_created"] == 2
        mock_md.assert_called_once()


@pytest.mark.anyio
async def test_mcp_resources_and_prompts_registered() -> None:
    """Verify standard experiment prompts and status resources are exposed."""
    resources = await MCP.list_resources()
    resource_uris = {str(r.uri) for r in resources}
    assert "capstone://status" in resource_uris
    assert "capstone://guide" in resource_uris

    prompts = await MCP.list_prompts()
    prompt_names = {p.name for p in prompts}
    assert "resonance_experiment_workflow" in prompt_names
    assert "collision_impulse_experiment" in prompt_names
    assert "titration_keep_sample_workflow" in prompt_names
    assert "sensor_calibration_workflow" in prompt_names

