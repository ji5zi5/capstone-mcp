# Copyright 2026 Capstone MCP contributors.
"""Unit tests verifying decomposed session sub-components: Lifecycle, CDP, Telemetry, Watcher."""

from __future__ import annotations

import pytest

from capstone_mcp import bridge
from capstone_mcp.bridge import NativeInventory
from capstone_mcp.session.cdp_client import SessionCdpClient
from capstone_mcp.session.lifecycle import SessionLifecycleManager
from capstone_mcp.session.telemetry import TelemetryBuffer
from capstone_mcp.session.watcher import (
    ConditionWatcher,
    StopCondition,
    StopConditionTrigger,
)


def test_session_lifecycle_manager_state() -> None:
    """Verify lifecycle manager activation, termination, and info reporting."""
    lifecycle = SessionLifecycleManager(debug_port=9222)
    assert lifecycle.is_active is True
    assert lifecycle.debug_port == 9222
    assert lifecycle.worker is None

    info = lifecycle.get_session_info()
    assert info["active"] is True
    assert info["debug_port"] == 9222
    assert info["worker_attached"] is False

    lifecycle.terminate()
    assert lifecycle.is_active is False
    assert lifecycle.get_session_info()["active"] is False


def test_session_cdp_client_delegation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify SessionCdpClient delegates to bridge functions."""
    client = SessionCdpClient(debug_port=9222)

    def mock_inv(port: int = 9222) -> NativeInventory:
        assert port == 9222
        return NativeInventory.model_validate({
            "sensors": [{"SensorID": 2002, "SensorName": "Wireless Acceleration"}],
            "measurements": [
                {"MeasurementEUID": "accel_x", "MeasurementName": "Acceleration X", "Unit": "m/s^2"},
            ],
        })

    def mock_val(port: int, euid: str, unit: int) -> float:
        assert port == 9222
        assert euid == "accel_x"
        assert unit == 0
        return 9.80665

    monkeypatch.setattr(bridge, "read_inventory", mock_inv)
    monkeypatch.setattr(bridge, "read_measurement", mock_val)

    inv = client.read_live_inventory()
    assert len(inv.sensors) == 1
    assert inv.sensors[0]["SensorName"] == "Wireless Acceleration"

    val = client.read_live_measurement("accel_x")
    assert val == pytest.approx(9.80665)


def test_telemetry_buffer_ring_and_stats() -> None:
    """Verify TelemetryBuffer sample buffering, windowing, and statistics."""
    buf = TelemetryBuffer(capacity=5)
    euid = "force_1"

    # Push 6 samples to trigger ring-buffer overflow (capacity=5)
    for i in range(1, 7):
        buf.push_sample(euid, float(i), timestamp=100.0 + float(i))

    samples = buf.get_samples(euid)
    assert len(samples) == 5
    assert samples[0][1] == 2.0  # sample 1 was dropped
    assert samples[-1][1] == 6.0
    assert buf.get_latest(euid) == 6.0

    # Limit parameter
    recent_two = buf.get_samples(euid, limit=2)
    assert len(recent_two) == 2
    assert recent_two[0][1] == 5.0
    assert recent_two[1][1] == 6.0

    # Stats computation
    stats = buf.compute_stats(euid)
    assert stats["count"] == 5.0
    assert stats["mean"] == pytest.approx(4.0)
    assert stats["min"] == 2.0
    assert stats["max"] == 6.0

    # Empty stats
    assert buf.compute_stats("nonexistent")["count"] == 0.0

    # Clear
    buf.clear(euid)
    assert buf.get_samples(euid) == []
    assert buf.get_latest(euid) is None


def test_condition_watcher_evaluation_and_monitoring() -> None:
    """Verify ConditionWatcher threshold evaluation and monitor loop."""
    watcher = ConditionWatcher()

    # Evaluation
    assert watcher.evaluate(15.0, ">", 10.0) is True
    assert watcher.evaluate(5.0, "<=", 5.0) is True
    assert watcher.evaluate(2.0, "below", 3.0) is True

    # Monitor loop
    stream = [1.0, 2.0, 3.5, 5.5]
    idx = 0

    def sampler() -> float:
        nonlocal idx
        v = stream[min(idx, len(stream) - 1)]
        idx += 1
        return v

    halted = False

    def on_halt() -> None:
        nonlocal halted
        halted = True

    cond = StopCondition(
        measurement_euid="force_1",
        operator=">",
        threshold=5.0,
        poll_interval=0.001,
        timeout=1.0,
    )

    trigger: StopConditionTrigger = watcher.monitor(
        cond,
        sampler,
        halt_callback=on_halt,
    )

    assert trigger.triggered is True
    assert trigger.current_value == 5.5
    assert halted is True
