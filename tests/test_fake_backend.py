# Copyright 2026 Capstone MCP contributors.
"""Unit tests verifying ICapstoneBackend protocol conformance and InMemoryFakeBackend RPC emulation."""

import base64

from capstone_mcp.automation_models import NativeRequest
from capstone_mcp.backend_protocol import ICapstoneBackend
from capstone_mcp.displays.models import (
    DisplayAction,
    DisplayRequest,
    DisplayResult,
    ReadTableRequest,
)
from capstone_mcp.fake_backend import InMemoryFakeBackend
from capstone_mcp.graphs.models import (
    GraphAction,
    GraphRequest,
    GraphResult,
)
from capstone_mcp.instruments.models import (
    InstrumentAction,
    InstrumentRequest,
    InstrumentResult,
    SetSignalGeneratorRequest,
)
from capstone_mcp.models import Action
from capstone_mcp.runs.models import (
    RenameRunRequest,
    RunAction,
    RunRequest,
    RunResult,
    SetRunVisibilityRequest,
)


def test_fake_backend_satisfies_protocol() -> None:
    """Verify InMemoryFakeBackend is an instance of ICapstoneBackend runtime protocol."""
    backend = InMemoryFakeBackend()
    assert isinstance(backend, ICapstoneBackend)
    assert backend.process_id == 4242


def test_fake_backend_attach_and_windows() -> None:
    """Verify attach and windows listing."""
    backend = InMemoryFakeBackend()
    windows = backend.windows()
    assert len(windows) == 1
    assert windows[0].process_id == 4242
    assert "Capstone" in windows[0].title

    attached = backend.attach(process_id=9999)
    assert len(attached) == 1
    assert backend.process_id == 9999


def test_fake_backend_snapshot_filtering() -> None:
    """Verify snapshot query and control type filtering."""
    backend = InMemoryFakeBackend()
    snap_all = backend.snapshot(10001)
    assert len(snap_all.controls) >= 5

    snap_rec = backend.snapshot(10001, query="Record")
    assert any("Record" in c.name for c in snap_rec.controls)

    snap_chk = backend.snapshot(10001, control_types=["CheckBox"])
    assert all(c.control_type == "CheckBox" for c in snap_chk.controls)


def test_fake_backend_act_and_screenshot() -> None:
    """Verify act, click, type_text, and screenshot execution."""
    backend = InMemoryFakeBackend()
    res_act = backend.act("ref:btn_rec", Action.INVOKE)
    assert "Record" in res_act.detail or "ref:btn_rec" in res_act.detail

    res_click = backend.click(10001, "ref:btn_stop")
    assert "Action" in res_click.detail or "ref:btn_stop" in res_click.detail

    backend.type_text("123.45")
    assert backend._control_values.get("focused") == "123.45"

    png_bytes = backend.screenshot(10001)
    assert png_bytes.startswith(b"\x89PNG")


def test_fake_backend_manage_graph_seam() -> None:
    """Verify graph compound seam execution in memory."""
    backend = InMemoryFakeBackend()

    # Read Graph
    res_read = backend.manage_graph(GraphRequest(action=GraphAction.READ))
    assert isinstance(res_read, GraphResult)
    assert res_read.read is not None
    assert res_read.read.verified is True

    # Fit Graph
    res_fit = backend.manage_graph(GraphRequest(action=GraphAction.FIT))
    assert res_fit.fit is not None
    assert res_fit.fit.mode == "scale_to_fit"
    assert res_fit.fit.target_ref == "ref:graph"
    assert res_fit.fit.verified is True

    # Delta
    res_delta = backend.manage_graph(GraphRequest(action=GraphAction.TOOLBOX_DELTA))
    assert res_delta.toolbox_delta is not None
    assert res_delta.toolbox_delta.dx == 0.5
    assert res_delta.toolbox_delta.dy == 1.2


def test_fake_backend_manage_instrument_seam() -> None:
    """Verify instrument compound seam execution and state retention in memory."""
    backend = InMemoryFakeBackend()

    # Configure Signal Generator
    sig_req = InstrumentRequest(
        action=InstrumentAction.CONFIGURE_SIGNAL_GENERATOR,
        configure_signal_generator=SetSignalGeneratorRequest(
            waveform="square",
            frequency=440.0,
            amplitude=3.3,
            enabled=True,
        ),
    )
    res_sig = backend.manage_instrument(sig_req)
    assert isinstance(res_sig, InstrumentResult)
    assert res_sig.configure_signal_generator is not None
    assert res_sig.configure_signal_generator.frequency == 440.0
    assert res_sig.configure_signal_generator.enabled is True

    # Scan Wireless
    res_scan = backend.manage_instrument(InstrumentRequest(action=InstrumentAction.SCAN_WIRELESS))
    assert res_scan.scan_wireless is not None
    assert res_scan.scan_wireless.count == 2


def test_fake_backend_manage_display_seam() -> None:
    """Verify display layout compound seam execution in memory."""
    backend = InMemoryFakeBackend()

    # Read Table
    res_tbl = backend.manage_display(
        DisplayRequest(
            action=DisplayAction.READ_TABLE,
            read_table=ReadTableRequest(table_name="Table 1"),
        ),
    )
    assert isinstance(res_tbl, DisplayResult)
    assert res_tbl.read_table is not None
    assert len(res_tbl.read_table.rows) == 10
    assert "Time (s)" in res_tbl.read_table.columns


def test_fake_backend_manage_run_seam() -> None:
    """Verify run management compound seam state mutation in memory."""
    backend = InMemoryFakeBackend()

    # Rename
    res_ren = backend.manage_run(
        RunRequest(
            action=RunAction.RENAME,
            rename=RenameRunRequest(old_name="Run 1", new_name="Velocity Calibration"),
        ),
    )
    assert isinstance(res_ren, RunResult)
    assert res_ren.rename is not None
    assert res_ren.rename.verified is True
    assert "Velocity Calibration" in backend._runs
    assert "Run 1" not in backend._runs

    # Visibility
    res_vis = backend.manage_run(
        RunRequest(
            action=RunAction.SET_VISIBILITY,
            visibility=SetRunVisibilityRequest(runs=["Velocity Calibration"], visible=False),
        ),
    )
    assert res_vis.visibility is not None
    assert backend._runs["Velocity Calibration"]["visible"] is False


def test_fake_backend_low_level_rpc_dispatch() -> None:
    """Verify low-level NativeRequest call() dispatch emulation."""
    backend = InMemoryFakeBackend()

    # Recording Status & Toggle
    status = backend.call(NativeRequest(operation="recording_status"))
    assert status["recording"] is False  # pyright: ignore[reportIndexIssue]

    started = backend.call(NativeRequest(operation="set_recording", recording=True))
    assert started["recording"] is True  # pyright: ignore[reportIndexIssue]

    # Sampling rate stepping
    stepped = backend.call(NativeRequest(operation="step_sampling_rate", direction="increase"))
    assert stepped["sampling_rate"] == "200 Hz"  # pyright: ignore[reportIndexIssue]

    # Screenshot base64
    shot_b64 = backend.call(NativeRequest(operation="screenshot", handle=10001))
    assert isinstance(shot_b64, str)
    assert base64.b64decode(shot_b64).startswith(b"\x89PNG")
