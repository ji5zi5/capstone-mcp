# Copyright 2026 Capstone MCP contributors.
"""Live end-to-end smoke test suite guarded by local Capstone executable availability."""

from __future__ import annotations

import json
import os
import subprocess
import time
from typing import TYPE_CHECKING

import httpx2
import psutil
import pytest
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import TypeAdapter

from capstone_mcp import server
from capstone_mcp.automation_models import NativeRequest
from capstone_mcp.automation_worker import AutomationWorker
from capstone_mcp.data_sources import get_experiment_series, list_source_datasets
from capstone_mcp.desktop import (
    DEFAULT_DEBUG_PORT,
    EXECUTABLE,
    AutomationError,
    Capstone,
)
from capstone_mcp.models import Window
from capstone_mcp.session import UnifiedSessionManager
from tests.test_protocol import exercise_protocol

if TYPE_CHECKING:
    from collections.abc import Generator

HAS_CAPSTONE = EXECUTABLE.exists()
pytestmark = pytest.mark.skipif(
    not HAS_CAPSTONE or os.environ.get("CAPSTONE_RUN_LIVE_TESTS") != "1",
    reason="Installed Capstone and CAPSTONE_RUN_LIVE_TESTS=1 required",
)


def _skip_if_capstone_running() -> None:
    """Leave existing user processes and their unsaved experiments untouched."""
    for proc in psutil.process_iter():
        try:
            if proc.name().lower() == EXECUTABLE.name.lower():
                pytest.skip("An existing Capstone process must remain untouched")
        except psutil.Error:
            pass


@pytest.mark.anyio
async def test_real_capstone_observation_over_stdio(live_capstone_process: int) -> None:
    """Exercise the wire against the exact application process owned by these tests."""
    await exercise_protocol(process_id=live_capstone_process)


@pytest.fixture(scope="module")
def live_capstone_process() -> Generator[int, None, None]:
    """Launch Capstone with debugging flags and guarantee clean termination after tests."""
    _skip_if_capstone_running()

    env = os.environ.copy()
    env["QTWEBENGINE_REMOTE_DEBUGGING"] = str(DEFAULT_DEBUG_PORT)
    cmd = [
        str(EXECUTABLE),
        f"--remote-debugging-port={DEFAULT_DEBUG_PORT}",
    ]

    process = subprocess.Popen(  # noqa: S603
        cmd, env=env, cwd=str(EXECUTABLE.parent),
    )
    try:
        app = Capstone()
        titles: list[str] = []
        for _attempt in range(15):
            if process.poll() is not None:
                pytest.fail(f"Capstone exited before opening a window ({process.returncode})")
            try:
                windows = app.attach(process_id=process.pid)
                titles = [window.title for window in windows]
                if any(".cap" in title.casefold() for title in titles):
                    break
            except (AutomationError, OSError):
                pass
            time.sleep(1)
        else:
            pytest.fail(f"Capstone experiment window not ready; observed: {titles}")
        yield process.pid
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


@pytest.fixture(scope="module")
def live_capstone_cdp(live_capstone_process: int) -> None:
    """Wait for CDP independently of the GUI attachment test."""
    manager = UnifiedSessionManager(debug_port=DEFAULT_DEBUG_PORT)
    deadline = time.monotonic() + 15
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            _ = manager.read_live_inventory()
        except (httpx2.HTTPError, RuntimeError, OSError, ValueError) as exc:
            last_error = exc
            time.sleep(1)
        else:
            return
    pytest.fail(f"Capstone PID {live_capstone_process} CDP not ready: {last_error}")


def test_live_capstone_attaches_and_lists_windows(
    live_capstone_process: int,
) -> None:
    # Given: Capstone is launched with debug port
    app = Capstone()
    windows = app.attach(process_id=live_capstone_process)

    # Then: at least one top-level window must be discovered belonging to the process
    assert len(windows) >= 1
    assert all(w.process_id == live_capstone_process for w in windows)
    assert any(w.handle > 0 for w in windows)


@pytest.mark.anyio
async def test_live_capstone_reattaches_after_native_worker_timeout(
    live_capstone_process: int, monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = AutomationWorker(timeout=15)
    monkeypatch.setattr(server, "WORKER", worker)
    attach_args = {"process_id": live_capstone_process}
    try:
        _ = await server.MCP.call_tool("capstone_attach", attach_args)
        window_list = TypeAdapter(list[Window])
        before = window_list.validate_python(
            await server._native(NativeRequest(operation="windows")),
        )
        assert before
        previous = worker.process
        assert previous is not None
        # Expire a read-only request while connected to the real application.
        worker.timeout = 0
        with pytest.raises(ToolError) as failure:
            _ = await server.MCP.call_tool(
                "capstone_snapshot", {"handle": before[0].handle},
            )
        assert json.loads(str(failure.value))["error_code"] == "TIMEOUT_ERROR"
        assert previous.poll() is not None
        assert psutil.pid_exists(live_capstone_process)

        worker.timeout = 15
        _ = await server.MCP.call_tool("capstone_attach", attach_args)
        assert worker.process_id != previous.pid
        windows = window_list.validate_python(
            await server._native(NativeRequest(operation="windows")),
        )
        assert windows
        assert {w.process_id for w in windows} == {live_capstone_process}
    finally:
        worker.close()


@pytest.mark.usefixtures("live_capstone_cdp")
def test_live_capstone_cdp_inventory_and_telemetry() -> None:
    # Given: live Capstone CDP port
    mgr = UnifiedSessionManager(debug_port=DEFAULT_DEBUG_PORT)

    # When: querying live inventory
    start_time = time.monotonic()
    inventory = mgr.read_live_inventory()
    latency_ms = (time.monotonic() - start_time) * 1000

    # Then: fast-path latency must be under 100ms and inventory shapes validated
    assert latency_ms < 100.0, f"CDP read latency exceeded threshold: {latency_ms:.1f}ms"
    assert isinstance(inventory.sensors, list)
    assert isinstance(inventory.measurements, list)


@pytest.mark.anyio
@pytest.mark.usefixtures("live_capstone_cdp")
async def test_live_capstone_mcp_resource() -> None:

    # When: reading dynamic MCP resource capstone://measurements/live
    raw_json = await server.capstone_live_measurements_resource()
    data = json.loads(raw_json)

    # Then
    assert data["status"] == "connected"
    assert data["debug_port"] == DEFAULT_DEBUG_PORT
    assert isinstance(data["sensors"], list)
    assert isinstance(data["measurements"], list)


@pytest.mark.usefixtures("live_capstone_cdp")
def test_live_capstone_polymorphic_seam() -> None:
    # Given: live Capstone process with exposed CDP port

    # When: querying polymorphic data source seam
    datasets = list_source_datasets("live://measurements")

    # Then: datasets list must be accessible without raising
    assert isinstance(datasets, list)
    if datasets:
        target = datasets[0].name
        assert datasets[0].sample_count == 0
        with pytest.raises(ValueError, match="at least two"):
            get_experiment_series("live://measurements", "time", target)

