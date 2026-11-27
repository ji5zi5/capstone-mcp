# Copyright 2026 Capstone MCP contributors.
"""Timestamp domains cannot silently mix even when numeric times increase."""
import pytest
from pydantic import ValidationError

from capstone_mcp.session.telemetry import TelemetryBuffer, TelemetryClock

CLOCK = TelemetryClock(clock_id="device:fixture:run1", unit="milliseconds", origin="run-start")


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_invalid_value_cannot_create_a_channel_or_evict_samples(value: float) -> None:
    buffer = TelemetryBuffer(capacity=1)
    buffer.push_sample("force", 2.0)
    before = buffer.get_snapshot("force")
    with pytest.raises(ValueError, match="sample value must be finite"):
        buffer.push_sample("force", value)
    assert buffer.get_snapshot("force") == before
    with pytest.raises(ValueError, match="sample value must be finite"):
        buffer.push_sample("new", value)
    assert buffer.get_clock("new") is None


def test_mean_of_large_finite_observations_is_finite() -> None:
    buffer = TelemetryBuffer()
    buffer.push_sample("force", 1e308)
    buffer.push_sample("force", 1e308)
    assert buffer.compute_stats("force")["mean"] == 1e308

def test_explicit_timestamp_requires_provenance() -> None:
    buffer = TelemetryBuffer()
    with pytest.raises(ValueError, match="require a clock"):
        buffer.push_sample("x", 1, 1)
    with pytest.raises(ValueError, match="requires an explicit timestamp"):
        buffer.push_sample("x", 1, clock=CLOCK)
    assert buffer.sample_count("x") == 0


@pytest.mark.parametrize("change", [
    {"clock_id": "device:other"}, {"unit": "seconds"}, {"origin": "boot"},
])
def test_domain_change_rejected_before_append(change: dict[str, str]) -> None:
    buffer = TelemetryBuffer(capacity=1)
    buffer.push_sample("x", 1, 100, clock=CLOCK)
    other = TelemetryClock.model_validate({**CLOCK.model_dump(), **change})
    with pytest.raises(ValueError, match="clock domain"):
        buffer.push_sample("x", 2, 200, clock=other)
    assert buffer.get_snapshot("x").model_dump() == {"clock": CLOCK.model_dump(), "first_timestamp": 100.0, "first_sample_index": 0, "samples": [(100.0, 1.0)]}


def test_automatic_host_timestamps_cannot_mix_with_device_times() -> None:
    buffer = TelemetryBuffer()
    buffer.push_sample("x", 1, 0, clock=CLOCK)
    with pytest.raises(ValueError, match="clock domain"):
        buffer.push_sample("x", 2)
    buffer.clear("x")
    buffer.push_sample("x", 3)
    clock = buffer.get_clock("x")
    assert clock is not None
    assert clock.unit == "seconds"
    assert clock.clock_id.startswith("host-monotonic:")
    with pytest.raises(ValueError, match="clock domain"):
        buffer.push_sample("x", 4, 1e30, clock=CLOCK)


def test_eviction_preserves_origin_and_clear_resets_provenance() -> None:
    buffer = TelemetryBuffer(capacity=1)
    buffer.push_sample("x", 1, 100, clock=CLOCK)
    old = buffer.get_snapshot("x")
    buffer.push_sample("x", 2, 200, clock=CLOCK)
    assert buffer.get_snapshot("x").samples == [(200.0, 2.0)]
    assert buffer.get_clock("x") == CLOCK
    buffer.clear()
    assert buffer.get_snapshot("x").clock is None
    assert old.samples == [(100.0, 1.0)]
    with pytest.raises(ValidationError):
        CLOCK.origin = "changed"
