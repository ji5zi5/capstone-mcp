# Copyright 2026 Capstone MCP contributors.
"""Live end-to-end smoke test suite guarded by local Capstone executable availability."""

from __future__ import annotations

import json
import os
import subprocess
import time
from typing import TYPE_CHECKING

import psutil
import pytest

from capstone_mcp import server
from capstone_mcp.desktop import DEFAULT_DEBUG_PORT, EXECUTABLE, Capstone
from capstone_mcp.session import UnifiedSessionManager

if TYPE_CHECKING:
    from collections.abc import Generator

HAS_CAPSTONE = EXECUTABLE.exists()
pytestmark = pytest.mark.skipif(
    not HAS_CAPSTONE,
    reason="Live Capstone installation required for E2E smoke tests",
)


def _cleanup_dangling_processes() -> None:
    """Terminate any lingering Capstone processes."""
    for proc in psutil.process_iter():
        try:
            if proc.name().lower() == EXECUTABLE.name.lower():
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except psutil.TimeoutExpired:
                    proc.kill()
        except psutil.Error:
            pass


@pytest.fixture(scope="module")
def live_capstone_process() -> Generator[int, None, None]:
    """Launch Capstone with debugging flags and guarantee clean termination after tests."""
    _cleanup_dangling_processes()

    env = os.environ.copy()
    env["QTWEBENGINE_REMOTE_DEBUGGING"] = str(DEFAULT_DEBUG_PORT)
    cmd = [
        str(EXECUTABLE),
        f"--remote-debugging-port={DEFAULT_DEBUG_PORT}",
        "--remote-allow-origins=*",
    ]

    process = subprocess.Popen(  # noqa: S603
        cmd, env=env, cwd=str(EXECUTABLE.parent),
    )
    pid = process.pid

    # Wait up to 15s for Capstone to expose CDP discovery endpoint
    mgr = UnifiedSessionManager(debug_port=DEFAULT_DEBUG_PORT)
    ready = False
    for _ in range(15):
        time.sleep(1)
        try:
            inv = mgr.read_live_inventory()
            if inv is not None:
                ready = True
                break
        except (RuntimeError, OSError, ValueError, TimeoutError):
            pass

    if not ready:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        pytest.fail("Capstone did not open CDP debug port within 15 seconds.")

    try:
        yield pid
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


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


def test_live_capstone_cdp_inventory_and_telemetry(
    live_capstone_process: int,
) -> None:
    # Given: live Capstone CDP port
    del live_capstone_process
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
async def test_live_capstone_mcp_resource(
    live_capstone_process: int,
) -> None:
    # Given: live Capstone process
    del live_capstone_process

    # When: reading dynamic MCP resource capstone://measurements/live
    raw_json = await server.capstone_live_measurements_resource()
    data = json.loads(raw_json)

    # Then
    assert data["status"] == "connected"
    assert data["debug_port"] == DEFAULT_DEBUG_PORT
    assert isinstance(data["sensors"], list)
    assert isinstance(data["measurements"], list)
