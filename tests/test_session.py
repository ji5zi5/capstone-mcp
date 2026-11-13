# Copyright 2026 Capstone MCP contributors.
"""Unit tests for UnifiedSessionManager and stop condition triggers."""

import pytest

from capstone_mcp import bridge
from capstone_mcp.bridge import NativeInventory
from capstone_mcp.session import StopCondition, UnifiedSessionManager


def test_unified_session_reads_inventory_via_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    def mock_inv(port: int = 9222) -> NativeInventory:
        assert port == 9222
        return NativeInventory.model_validate({
            "sensors": [{"SensorID": 1001, "SensorName": "Wireless Force"}],
            "measurements": [{"MeasurementEUID": "force_1", "MeasurementName": "Force", "Unit": "N"}],
        })

    monkeypatch.setattr(bridge, "read_inventory", mock_inv)
    mgr = UnifiedSessionManager()

    # When
    inv = mgr.read_live_inventory()

    # Then
    assert len(inv.sensors) == 1
    assert inv.sensors[0]["SensorName"] == "Wireless Force"


def test_unified_session_reads_live_measurement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    def mock_val(port: int, euid: str, unit: int) -> float:
        assert port == 9222
        assert euid == "force_1"
        assert unit == 0
        return 9.81

    monkeypatch.setattr(bridge, "read_measurement", mock_val)
    mgr = UnifiedSessionManager()

    # When
    val = mgr.read_live_measurement("force_1")

    # Then
    assert val == 9.81


def test_evaluate_stop_condition_operators() -> None:
    mgr = UnifiedSessionManager()
    assert mgr.evaluate_stop_condition(10.5, ">", 10.0) is True
    assert mgr.evaluate_stop_condition(9.5, ">", 10.0) is False
    assert mgr.evaluate_stop_condition(10.0, ">=", 10.0) is True
    assert mgr.evaluate_stop_condition(5.0, "<", 10.0) is True
    assert mgr.evaluate_stop_condition(10.0, "<=", 10.0) is True
    assert mgr.evaluate_stop_condition(10.0, "==", 10.0) is True
    assert mgr.evaluate_stop_condition(10.0, "!=", 5.0) is True
    assert mgr.evaluate_stop_condition(15.0, "above", 10.0) is True
    assert mgr.evaluate_stop_condition(5.0, "below", 10.0) is True
    assert mgr.evaluate_stop_condition(10.0, "reaches", 10.0) is True

    with pytest.raises(ValueError, match="Unsupported threshold operator"):
        _ = mgr.evaluate_stop_condition(10.0, "unknown_op", 10.0)


def test_monitor_until_stop_halts_when_threshold_met(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: simulated series: 2.0 -> 4.5 -> 7.8 (threshold > 5.0)
    values = [2.0, 4.5, 7.8]
    call_idx = 0

    def mock_stream(_port: int, _euid: str, _unit: int) -> float:
        nonlocal call_idx
        v = values[min(call_idx, len(values) - 1)]
        call_idx += 1
        return v

    monkeypatch.setattr(bridge, "read_measurement", mock_stream)
    halt_called = False

    def on_halt() -> None:
        nonlocal halt_called
        halt_called = True

    mgr = UnifiedSessionManager()

    # When
    result = mgr.monitor_until_stop(
        StopCondition(
            measurement_euid="force_1",
            operator=">",
            threshold=5.0,
            poll_interval=0.001,
            timeout=1.0,
        ),
        halt_callback=on_halt,
    )

    # Then
    assert result.triggered is True
    assert result.current_value == 7.8
    assert halt_called is True
    assert "Stop condition triggered" in result.detail


def test_monitor_until_stop_times_out_safely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: value never reaches 100.0
    monkeypatch.setattr(bridge, "read_measurement", lambda _p, _e, _u: 1.0)
    mgr = UnifiedSessionManager()

    # When
    result = mgr.monitor_until_stop(
        StopCondition(
            measurement_euid="force_1",
            operator=">",
            threshold=100.0,
            poll_interval=0.01,
            timeout=0.05,
        ),
    )

    # Then
    assert result.triggered is False
    assert result.current_value == 1.0
    assert "Timeout" in result.detail
