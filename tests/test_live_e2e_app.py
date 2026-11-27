# Copyright 2026 Capstone MCP contributors.
"""Live sensorless E2E verification against installed PASCO Capstone desktop."""

from __future__ import annotations

import os
import shutil
import sys
import time
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Final

import anyio
import psutil
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import ImageContent

from capstone_mcp.calculator import CreateCalculationRequest, create_calculation
from capstone_mcp.capfiles import read_cap_file
from capstone_mcp.data_sources.adapters.csv_file import read_csv_all_columns
from capstone_mcp.desktop import (
    EXECUTABLE,
    AutomationError,
    Capstone,
    capstone_processes,
)
from capstone_mcp.displays.digits import create_digits
from capstone_mcp.displays.models import (
    AddPageRequest,
    CreateDigitsRequest,
    CreateTableRequest,
    ReadTableRequest,
)
from capstone_mcp.displays.table import create_table, read_table
from capstone_mcp.displays.workbook import add_page
from capstone_mcp.file_workflows import export_data, open_experiment, save_experiment
from capstone_mcp.graphs import read_saved_graph
from capstone_mcp.graphs.inspection import read_graph
from capstone_mcp.models import Action
from capstone_mcp.reports import generate_report
from capstone_mcp.runs import DeleteRunRequest, delete_run

if TYPE_CHECKING:
    from collections.abc import Iterator

    from capstone_mcp.models import Window

QUICKSTART_DIR: Final = Path(
    r"C:\Program Files\PASCO scientific\Capstone\Resources\Templates\QuickStart",
)
MOMENTUM_TEMPLATE: Final = QUICKSTART_DIR / "Conservation of Momentum.cap"
NEWTON_TEMPLATE: Final = QUICKSTART_DIR / "Newton's Second Law.cap"
ROOT: Final = str(Path(__file__).resolve().parents[1])
MIN_WORKBOOK_WIDTH_PX: Final = 600
STARTUP_TIMEOUT_S: Final = 35.0

pytestmark = pytest.mark.skipif(
    sys.platform != "win32"
    or os.environ.get("CAPSTONE_RUN_LIVE_TESTS") != "1"
    or not EXECUTABLE.is_file(),
    reason=(
        "live E2E suite requires installed PASCO Capstone on Windows "
        "and CAPSTONE_RUN_LIVE_TESTS=1"
    ),
)


def _skip_if_capstone_running() -> None:
    installed, other = capstone_processes()
    if installed or other:
        pytest.skip(
            "close running Capstone processes first so E2E does not touch user work",
        )


def _requires_interactive_desktop() -> None:
    """Skip pointer/keyboard tests when running in a non-input/locked desktop."""
    import win32gui  # noqa: PLC0415

    if not win32gui.GetForegroundWindow():
        pytest.skip("requires active foreground window on WinSta0\\Default desktop")


def _terminate_process(pid: int) -> None:
    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    with suppress(psutil.Error):
        proc.terminate()
    try:
        proc.wait(timeout=10)
    except psutil.TimeoutExpired:
        with suppress(psutil.Error):
            proc.kill()
        with suppress(psutil.Error):
            proc.wait(timeout=5)


def _window_size(win: Window) -> tuple[int, int]:
    return win.bounds.right - win.bounds.left, win.bounds.bottom - win.bounds.top


def _dismiss_update_dialogs(app: Capstone) -> bool:
    dismissed = False
    for win in app.windows():
        if "update" in win.title.casefold():
            snap = app.snapshot(win.handle, 8, 500)
            for ctrl in snap.controls:
                if ctrl.control_type == "Button" and ctrl.enabled and ctrl.visible:
                    cname = ctrl.name.casefold()
                    if any(
                        tok in cname
                        for tok in (
                            "remind me later",
                            "later",
                            "close",
                            "닫기",
                            "cancel",
                            "no",
                            "skip",
                        )
                    ):
                        with suppress(AutomationError):
                            app.act(ctrl.ref, Action.INVOKE)
                            dismissed = True
                            break
    return dismissed


def _wait_for_workbook_window(
    app: Capstone,
    *,
    dismiss_modals: bool,
    timeout_s: float = STARTUP_TIMEOUT_S,
) -> Window:
    """Wait for the real .cap workbook window (ignoring startup splash screen)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if dismiss_modals:
            _dismiss_update_dialogs(app)
        candidates = [
            w for w in app.windows()
            if ".cap" in w.title.casefold()
            and _window_size(w)[0] >= MIN_WORKBOOK_WIDTH_PX
            and "update" not in w.title.casefold()
        ]
        if candidates:
            return max(
                candidates,
                key=lambda w: _window_size(w)[0] * _window_size(w)[1],
            )
        time.sleep(0.4)
    msg = f"Expected .cap Capstone window within {timeout_s}s, found {app.windows()}"
    raise AssertionError(msg)


@pytest.fixture
def live_capstone() -> Iterator[tuple[Capstone, int]]:
    _skip_if_capstone_running()
    app = Capstone()
    app.attach(launch=True)
    assert app.pid is not None
    try:
        win = _wait_for_workbook_window(app, dismiss_modals=False)
        yield app, win.handle
    finally:
        pid = app.pid
        if pid is not None:
            _terminate_process(pid)


@pytest.fixture
def interactive_capstone() -> Iterator[tuple[Capstone, int]]:
    _requires_interactive_desktop()
    _skip_if_capstone_running()
    app = Capstone()
    app.attach(launch=True)
    assert app.pid is not None
    try:
        deadline = time.monotonic() + STARTUP_TIMEOUT_S
        while time.monotonic() < deadline:
            win = _wait_for_workbook_window(app, dismiss_modals=True)
            if not any("update" in w.title.casefold() for w in app.windows()):
                app.require_input_ready(win.handle)
                yield app, win.handle
                return
            time.sleep(0.5)
        msg = "Capstone remained modal-blocked during interactive startup."
        raise AssertionError(msg)
    finally:
        pid = app.pid
        if pid is not None:
            _terminate_process(pid)


def test_live_e2e_launch_uia_modals_guards_and_leak_stability(
    live_capstone: tuple[Capstone, int],
) -> None:
    app, handle = live_capstone
    snap = app.snapshot(handle, 16, 2_000)
    names = {c.name for c in snap.controls if c.name}
    aids = {c.automation_id for c in snap.controls if c.automation_id}
    assert "File" in names
    assert "Display" in names
    assert "mMainMenuBar" in aids
    assert "Workbook" in aids

    png = app.screenshot(handle)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")

    # Verify update dialog (if spawned) or modal block raises clear AutomationError
    with pytest.raises(AutomationError):
        app.focus_window(handle)

    with pytest.raises(AutomationError, match="by name"):
        delete_run(app, DeleteRunRequest(handle=handle, run_name="Run #1"))

    assert app.pid is not None
    proc = psutil.Process(app.pid)
    base_handles = proc.num_handles()
    base_rss = proc.memory_info().rss
    for _ in range(10):
        loop_snap = app.snapshot(handle, 8, 1_000)
        assert loop_snap.controls
    assert proc.num_handles() - base_handles < 500
    assert proc.memory_info().rss - base_rss < 80 * 1024 * 1024


def test_live_e2e_official_cap_corpus_and_stdio_mcp_roundtrip(
    live_capstone: tuple[Capstone, int],
    tmp_path: Path,
) -> None:
    app, handle = live_capstone
    assert app.pid is not None
    populated_caps = [f for f in sorted(QUICKSTART_DIR.glob("*.cap")) if read_cap_file(f).datasets]
    assert len(populated_caps) >= 5
    for src in populated_caps:
        parsed = read_cap_file(src)
        assert parsed.datasets
        _ = read_saved_graph(str(src), 0)

    cap_copy = tmp_path / "momentum_mcp.cap"
    shutil.copyfile(MOMENTUM_TEMPLATE, cap_copy)

    async def _run() -> None:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "capstone_mcp.server"],
            cwd=ROOT,
            env={"PYTHONPATH": str(Path(ROOT) / "src")},
        )
        with anyio.fail_after(60):
            async with (
                stdio_client(params) as (reader, writer),
                ClientSession(reader, writer) as session,
            ):
                await session.initialize()
                attached = await session.call_tool(
                    "capstone_attach", {"process_id": app.pid},
                )
                assert not attached.isError, attached.content
                shot = await session.call_tool("capstone_screenshot", {"handle": handle})
                assert not shot.isError, shot.content
                images = [c for c in shot.content if isinstance(c, ImageContent)]
                assert len(images) == 1
                saved_graph = await session.call_tool(
                    "capstone_manage_graph",
                    {"request": {"action": "read", "read": {"cap_file": str(cap_copy)}}},
                )
                assert not saved_graph.isError, saved_graph.content
                pol = await session.call_tool(
                    "capstone_run_experiment_macro",
                    {
                        "experiment_id": "polarization",
                        "action": "analyze",
                        "parameters": {
                            "angles_deg": [0, 30, 60, 90, 120, 150],
                            "intensities": [100, 75, 25, 0, 25, 75],
                        },
                    },
                )
                assert not pol.isError, pol.content
                report = await session.call_tool(
                    "capstone_generate_lab_report",
                    {"file_path_or_run": str(cap_copy), "experiment_id": "generic"},
                )
                assert not report.isError, report.content

    anyio.run(_run)
    sample_rep = generate_report("sample", "polarization")
    assert sample_rep.regression is not None


def test_live_e2e_interactive_file_roundtrip_and_export(
    interactive_capstone: tuple[Capstone, int],
    tmp_path: Path,
) -> None:
    app, handle = interactive_capstone
    assert MOMENTUM_TEMPLATE.is_file()
    work_cap = tmp_path / "momentum_work.cap"
    saved_cap = tmp_path / "momentum_saved.cap"
    exported_csv = tmp_path / "momentum_export.csv"
    shutil.copyfile(MOMENTUM_TEMPLATE, work_cap)

    opened = open_experiment(app, handle, str(work_cap), discard_unsaved=True)
    assert "momentum_work" in opened.document_title_after.casefold()

    artifact = save_experiment(app, handle, str(saved_cap))
    assert artifact.format == "cap"
    assert saved_cap.is_file()
    assert len(read_cap_file(saved_cap).datasets) >= 5

    csv_artifact = export_data(app, handle, str(exported_csv))
    assert csv_artifact.format == "csv"
    assert exported_csv.is_file()
    assert read_csv_all_columns(exported_csv)


@pytest.mark.skipif(
    os.environ.get("CAPSTONE_TEST_DISPOSABLE_CLIPBOARD") != "1",
    reason="Copy Display touches clipboard; requires CAPSTONE_TEST_DISPOSABLE_CLIPBOARD=1",
)
def test_live_e2e_interactive_graph_copy_display_and_screenshot(
    interactive_capstone: tuple[Capstone, int],
    tmp_path: Path,
) -> None:
    app, handle = interactive_capstone
    work_cap = tmp_path / "momentum_graph.cap"
    shutil.copyfile(MOMENTUM_TEMPLATE, work_cap)
    open_experiment(app, handle, str(work_cap), discard_unsaved=True)

    state = read_graph(app, handle, allow_foreground=True)
    assert len(state.data_signature) == 64

    png = app.graph_screenshot(handle, activate=True)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")


def test_live_e2e_interactive_displays_and_calculator(
    interactive_capstone: tuple[Capstone, int],
    tmp_path: Path,
) -> None:
    app, handle = interactive_capstone
    work_cap = tmp_path / "newton_e2e.cap"
    shutil.copyfile(NEWTON_TEMPLATE, work_cap)
    open_experiment(app, handle, str(work_cap), discard_unsaved=True)

    page = add_page(app, AddPageRequest(handle=handle, title="E2E Page", allow_foreground=True))
    assert page.verified

    table = create_table(app, CreateTableRequest(handle=handle, allow_foreground=True))
    assert table.created
    read_res = read_table(app, ReadTableRequest(handle=handle, allow_foreground=True))
    assert read_res.table_name

    digits = create_digits(app, CreateDigitsRequest(handle=handle, allow_foreground=True))
    assert digits.created

    with pytest.raises(AutomationError, match="unbalanced"):
        create_calculation(
            app,
            CreateCalculationRequest(
                handle=handle, expression="bad = (1 + 2", allow_foreground=True,
            ),
        )
    calc = create_calculation(
        app,
        CreateCalculationRequest(
            handle=handle, expression="e2e_val = 2 * 3 + 1", allow_foreground=True,
        ),
    )
    assert calc.calculation_name == "e2e_val"
