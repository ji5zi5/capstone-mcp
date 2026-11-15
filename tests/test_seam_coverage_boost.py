# Copyright 2026 Capstone MCP contributors.
"""Seam interface and router coverage boost tests for Phase 11 Ticket 6."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.fastmcp import FastMCP, Image

from capstone_mcp.analysis import FitInput, RunSamples
from capstone_mcp.csv_data import CsvColumn, CsvPage
from capstone_mcp.desktop import AutomationError
from capstone_mcp.models import Action, Button, Point
from capstone_mcp.native.runtime import NativeDesktop
from capstone_mcp.plotting import PlotInput
from capstone_mcp.prompts import (
    collision_impulse_experiment,
    data_analysis_workflow,
    display_layout_workflow,
    hardware_setup_workflow,
    register_prompts,
    resonance_experiment_workflow,
    run_comparison_workflow,
    sensor_calibration_workflow,
    titration_keep_sample_workflow,
)
from capstone_mcp.resources import (
    _read_active_displays_doc,
    _read_hardware_inventory_doc,
    _read_live_measurements_doc,
    _read_status_doc,
    _tally_display_controls,
    register_resources,
)
from capstone_mcp.server import MCP, _lifespan
from capstone_mcp.tools.files import register_file_tools
from capstone_mcp.tools.physics import register_physics_tools
from capstone_mcp.tools.ui import (
    capstone_action,
    capstone_click,
    capstone_drag,
    capstone_keys,
    capstone_read_value,
    capstone_scroll,
    capstone_set_value,
    capstone_type_text,
    register_ui_tools,
)

if TYPE_CHECKING:
    from capstone_mcp.automation_models import NativeRequest


def test_all_prompts_invocation_coverage() -> None:
    """Verify all 8 guided prompts produce structured experiment guidelines."""
    p1 = resonance_experiment_workflow(500.0, 3.5)
    assert "500.0 Hz" in p1
    assert "3.5 V" in p1

    p2 = collision_impulse_experiment(1.2)
    assert "1.2 N" in p2

    p3 = titration_keep_sample_workflow(0.5)
    assert "0.5 mL" in p3

    p4 = sensor_calibration_workflow("Photogate")
    assert "Photogate" in p4

    p5 = data_analysis_workflow("Harmonic", "Quadratic")
    assert "Harmonic" in p5
    assert "Quadratic" in p5

    p6 = display_layout_workflow("Custom Page", "three_horizontal", "Force, Accel")
    assert "Custom Page" in p6
    assert "three_horizontal" in p6

    p7 = run_comparison_workflow("Trial A", "Trial B")
    assert "Trial A" in p7
    assert "Trial B" in p7

    p8 = hardware_setup_workflow("550 Interface", "Motion Sensor", "50 Hz")
    assert "550 Interface" in p8
    assert "Motion Sensor" in p8

    # Test registration onto FastMCP
    mcp_dummy = FastMCP("test_prompts")
    register_prompts(mcp_dummy)


def test_tally_display_controls_all_branches() -> None:
    """Exercise all display control branches in _tally_display_controls."""
    doc = {
        "pages": ["Page 1"],
        "displays": [],
        "table_count": 0,
        "graph_count": 0,
        "digits_count": 0,
        "scope_count": 0,
        "fft_count": 0,
    }

    controls = [
        "not_a_dict",
        {"name": "Page 2", "control_type": "TabItem", "automation_id": "page_tab_2"},
        {"name": "My Table", "control_type": "Pane", "automation_id": "table_view_1"},
        {"name": "Voltage Graph", "control_type": "Pane", "automation_id": "graph_1"},
        {"name": "Force Digits", "control_type": "Text", "automation_id": "digits_1"},
        {"name": "Scope Display", "control_type": "Pane", "automation_id": "scope_1"},
        {"name": "Signal Oscilloscope", "control_type": "Pane", "automation_id": "osc_1"},
        {"name": "Frequency FFT", "control_type": "Pane", "automation_id": "fft_1"},
        {"name": "Page 1", "control_type": "TabItem", "automation_id": "page_1"},  # duplicate page
        {"name": "", "control_type": "Button", "automation_id": "other_control"},
    ]

    _tally_display_controls(controls, doc)

    assert "Page 2" in doc["pages"]
    assert doc["table_count"] == 1
    assert doc["graph_count"] == 1
    assert doc["digits_count"] == 1
    assert doc["scope_count"] == 2  # scope + oscilloscope
    assert doc["fft_count"] == 1
    assert len(doc["displays"]) == 6

    # Early exit on invalid pages list
    invalid_doc = {"pages": None}
    _tally_display_controls(controls, invalid_doc)


@pytest.mark.anyio
async def test_read_status_and_hardware_doc_rich_data() -> None:
    """Verify _read_status_doc and _read_hardware_inventory_doc under simulated data."""
    mock_worker = MagicMock()
    mock_worker.retired = False
    mock_worker.process_id = 9999
    mock_worker.last_graph_failure = None

    mock_jobs = MagicMock()
    mock_jobs.jobs = {}

    async def mock_native(req: NativeRequest) -> dict[str, object]:
        if req.operation == "windows":
            return [{"handle": 100, "title": "PASCO Capstone"}]
        if req.operation == "recording_status":
            return {"running": False, "sampling_rate_display": "250 Hz"}
        if req.operation == "manage_instrument":
            return {
                "scan_wireless": {
                    "sensors": [{"name": "Wireless Force", "sensor_id": "WF-01"}],
                },
            }
        return {}

    # 1. Status doc
    status_raw = await _read_status_doc(mock_worker, mock_jobs, mock_native)
    status = json.loads(status_raw)
    assert status["attached"] is True
    assert status["process_id"] == 9999

    # 2. Hardware inventory doc
    hw_raw = await _read_hardware_inventory_doc(mock_worker, mock_native)
    hw = json.loads(hw_raw)
    assert hw["attached"] is True
    assert hw["sampling_rate"] == "250 Hz"
    assert len(hw["wireless_devices"]) == 1
    assert hw["wireless_devices"][0]["name"] == "Wireless Force"

    # 3. FastMCP registration check
    mcp_dummy = FastMCP("test_resources")
    res_dict = register_resources(mcp_dummy, mock_worker, mock_jobs, mock_native)
    assert len(res_dict) == 6


def test_read_live_measurements_doc_rich_data() -> None:
    """Verify _read_live_measurements_doc with simulated sensor inventory."""
    mock_worker = MagicMock()
    mock_worker.process_id = 1234

    with patch("capstone_mcp.resources.UnifiedSessionManager") as mock_mgr_cls:
        mock_mgr = mock_mgr_cls.return_value
        mock_mgr.debug_port = 9222
        mock_inv = MagicMock()
        mock_inv.sensors = ["Sensor A"]
        mock_inv.measurements = [
            {
                "MeasurementEUID": "EUID_FORCE_1",
                "MeasurementName": "Force",
                "Unit": "N",
            },
            "invalid_non_dict_measurement",
        ]
        mock_mgr.read_live_inventory.return_value = mock_inv
        mock_mgr.read_live_measurement.return_value = 4.25

        doc_raw = _read_live_measurements_doc(mock_worker)
        doc = json.loads(doc_raw)
        assert doc["status"] == "connected"
        assert len(doc["measurements"]) == 1
        assert doc["measurements"][0]["value"] == 4.25
        assert doc["measurements"][0]["name"] == "Force"


@pytest.mark.anyio
async def test_read_active_displays_doc_dict_and_list_controls() -> None:
    """Verify _read_active_displays_doc parses controls from dict and list responses."""
    mock_worker = MagicMock()
    mock_worker.retired = False
    mock_worker.process_id = 1234

    async def mock_native_dict(_req: NativeRequest) -> dict[str, object]:
        return {
            "controls": [
                {"name": "Page 1", "control_type": "TabItem", "automation_id": "page_1"},
                {"name": "Table Display", "control_type": "Pane", "automation_id": "table_1"},
            ],
        }

    doc_raw = await _read_active_displays_doc(mock_worker, mock_native_dict)
    doc = json.loads(doc_raw)
    assert doc["active_page"] == "Page 1"
    assert doc["table_count"] == 1

    async def mock_native_list(_req: NativeRequest) -> list[object]:
        return [
            {"name": "Page X", "control_type": "TabItem", "automation_id": "page_x"},
            {"name": "Graph Display", "control_type": "Pane", "automation_id": "graph_x"},
        ]

    doc_raw2 = await _read_active_displays_doc(mock_worker, mock_native_list)
    doc2 = json.loads(doc_raw2)
    assert doc2["active_page"] == "Page X"
    assert doc2["graph_count"] == 1


@pytest.mark.anyio
async def test_files_tools_invocations() -> None:
    """Verify files tools through register_file_tools."""
    mock_native = AsyncMock()
    mock_native.side_effect = [
        {
            "path": "test.cap",
            "format": "cap",
            "size_bytes": 1000,
            "sha256": "abc12345",
            "document_title_before": "Untitled",
            "document_title_after": "test.cap",
            "precision": "native-cache",
        },
        {
            "path": "opened.cap",
            "document_title_before": "Untitled",
            "document_title_after": "opened.cap - PASCO Capstone",
            "discarded_unsaved_changes": True,
        },
        {
            "path": "export.csv",
            "format": "csv",
            "size_bytes": 500,
            "sha256": "def67890",
            "document_title_before": "test.cap",
            "document_title_after": "test.cap",
            "precision": "capstone-export",
        },
    ]

    mcp = FastMCP("test_files")
    tools = register_file_tools(mcp, mock_native)

    # 1. save experiment
    save_fn = tools["capstone_save_experiment"]
    res_save = await save_fn(handle=10, path="test.cap")
    assert res_save.path == "test.cap"

    # 2. open experiment
    open_fn = tools["capstone_open_experiment"]
    res_open = await open_fn(handle=10, path="opened.cap", discard_unsaved=True)
    assert res_open.path == "opened.cap"

    # 3. export data
    with patch("capstone_mcp.tools.files.read_csv_page") as mock_read_csv:
        mock_read_csv.return_value = CsvPage(
            path="export.csv",
            row_count=10,
            offset=0,
            returned_rows=10,
            next_offset=None,
            columns=[
                CsvColumn(
                    index=0,
                    label="Time",
                    values=["0.0", "1.0"],
                    numeric_values=None,
                ),
            ],
        )
        export_fn = tools["capstone_export_data"]
        res_export = await export_fn(handle=10, path="export.csv")
        assert res_export.artifact.path == "export.csv"
        assert res_export.data.row_count == 10


@pytest.mark.anyio
async def test_physics_tools_invocations() -> None:
    """Verify physics tools through register_physics_tools."""
    mock_native = AsyncMock()
    mock_native.return_value = {
        "calculation_name": "KineticEnergy",
        "expression": "0.5*m*v^2",
        "unit": "J",
        "status": "valid",
        "detail": "created",
        "verified": True,
    }

    mcp = FastMCP("test_physics")
    tools = register_physics_tools(mcp, mock_native)

    guide_fn = tools["capstone_guide"]
    assert "workflow" in guide_fn(None)

    calc_fn = tools["capstone_create_calculation"]
    res_calc = await calc_fn("0.5*m*v^2", handle=10, unit="J")
    assert res_calc.calculation_name == "KineticEnergy"

    # Extra physics pure tools
    plot_fn = tools["capstone_plot"]
    img = plot_fn(PlotInput(x=[0.0, 1.0], y=[0.0, 2.0]))
    assert isinstance(img, Image)

    fit_fn = tools["capstone_linear_fit"]
    fit_res = fit_fn(FitInput(x=[0.0, 1.0, 2.0], y=[0.0, 2.0, 4.0]))
    assert fit_res.slope == 2.0

    comp_fn = tools["capstone_compare_runs"]
    res_comp = comp_fn([
        RunSamples(name="R1", values=[1.0, 2.0]),
        RunSamples(name="R2", values=[2.0, 3.0]),
    ])
    assert len(res_comp) == 2


@pytest.mark.anyio
async def test_server_lifespan_execution() -> None:
    """Verify server _lifespan context manager gracefully enters and exits."""
    async with _lifespan(MCP):
        pass


def test_native_runtime_mouse_primitives() -> None:
    """Verify NativeDesktop click, drag, and scroll dispatch paths."""
    native_desktop = NativeDesktop()
    mock_app = MagicMock()
    mock_window = MagicMock()
    mock_rect = MagicMock()
    mock_rect.left = 100
    mock_rect.top = 100
    mock_rect.right = 500
    mock_rect.bottom = 400
    mock_window.rectangle.return_value = mock_rect
    mock_app.focus_window.return_value = mock_window
    mock_app.refs = {}
    native_desktop.app = mock_app

    # 1. Click
    req_click = MagicMock()
    req_click.allow_foreground = True
    req_click.handle = 10
    req_click.point = Point(x=50, y=50)
    req_click.button = Button.LEFT
    req_click.double = False
    res_click = native_desktop._click(req_click)
    assert res_click.delivered is True

    # Click out of bounds
    req_click_oob = MagicMock()
    req_click_oob.allow_foreground = True
    req_click_oob.handle = 10
    req_click_oob.point = Point(x=1000, y=1000)
    with pytest.raises(AutomationError, match="inside the current window"):
        native_desktop._click(req_click_oob)

    # 2. Drag
    req_drag = MagicMock()
    req_drag.allow_foreground = True
    req_drag.handle = 10
    req_drag.point = Point(x=10, y=10)
    req_drag.end = Point(x=20, y=20)
    res_drag = native_desktop._drag(req_drag)
    assert res_drag.delivered is True

    # 3. Scroll
    req_scroll = MagicMock()
    req_scroll.allow_foreground = True
    req_scroll.handle = 10
    req_scroll.point = Point(x=10, y=10)
    req_scroll.notches = 3
    res_scroll = native_desktop._scroll(req_scroll)
    assert res_scroll.delivered is True


@pytest.mark.anyio
async def test_ui_primitives_direct_invocations() -> None:
    """Verify individual low-level UI functions in capstone_mcp.tools.ui."""
    mock_native = AsyncMock()
    mock_native.return_value = {"detail": "ok", "delivered": True}

    # action
    res_action = await capstone_action(mock_native, "ref_1", Action.INVOKE)
    assert res_action.delivered is True

    # read_value
    mock_native.return_value = "read_text_val"
    res_read = await capstone_read_value(mock_native, "ref_2")
    assert res_read == "read_text_val"

    # set_value
    mock_native.return_value = {"detail": "set", "delivered": True}
    res_set = await capstone_set_value(mock_native, "ref_3", "val")
    assert res_set.delivered is True

    # click
    res_click = await capstone_click(mock_native, 10, Point(x=5, y=5), button=Button.RIGHT)
    assert res_click.delivered is True

    # drag
    res_drag = await capstone_drag(mock_native, 10, Point(x=0, y=0), Point(x=10, y=10))
    assert res_drag.delivered is True

    # scroll
    res_scroll = await capstone_scroll(mock_native, 10, Point(x=5, y=5), 3)
    assert res_scroll.delivered is True

    # keys
    res_keys = await capstone_keys(mock_native, 10, "{ENTER}")
    assert res_keys.delivered is True

    # type text
    res_type = await capstone_type_text(mock_native, 10, "Hello+World")
    assert res_type.delivered is True

    # register_ui_tools check
    mcp = FastMCP("test_ui")
    ui_tools = register_ui_tools(mcp, mock_native)
    interact_fn = ui_tools["capstone_interact_ui"]
    with pytest.raises(ValueError, match="Unknown action"):
        await interact_fn("unsupported_action")  # type: ignore[arg-type]
