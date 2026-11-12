# Copyright 2026 Capstone MCP contributors.
"""Preserve native success semantics at the bridge response boundary."""

import pytest
from pydantic import JsonValue

from capstone_mcp import bridge


def test_unavailable_value_is_not_reported_as_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the real provider's unavailable-value response shape.
    def unavailable(_port: int, _expression: str) -> JsonValue:
        return {"ReturnValue": 0, "cmdResult": False}

    monkeypatch.setattr(bridge, "evaluate", unavailable)
    # When / Then
    with pytest.raises(bridge.BridgeError):
        _ = bridge.read_measurement(9223, "{measurement}", 0)


def test_successful_zero_remains_a_valid_measurement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    def measured_zero(_port: int, _expression: str) -> JsonValue:
        return {"ReturnValue": 0, "cmdResult": True}

    monkeypatch.setattr(bridge, "evaluate", measured_zero)
    # When
    value = bridge.read_measurement(9223, "{measurement}", 0)
    # Then
    assert value == 0


def test_inventory_accepts_builds_without_codable_interfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the category set observed from Capstone 2.5.0, which reports no
    # codableInterfaces key at all.
    def capstone_2_5(_port: int, _expression: str) -> JsonValue:
        return {
            "accessories": [], "codeNodes": [], "controlNodes": [],
            "measurements": [{"MeasurementName": "Voltage, Ch X1"}],
            "outputs": [], "sensors": [{"SensorID": 20128}],
        }

    monkeypatch.setattr(bridge, "evaluate", capstone_2_5)
    # When
    inventory = bridge.read_inventory(9223)
    # Then: the absent category is reported as absent rather than invented.
    assert inventory.codable_interfaces is None
    assert inventory.outputs == []
    assert inventory.sensors == [{"SensorID": 20128}]


def test_inventory_still_requires_sensors_and_measurements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a reply that is not a sensor inventory at all.
    def unrelated(_port: int, _expression: str) -> JsonValue:
        return {"accessories": []}

    monkeypatch.setattr(bridge, "evaluate", unrelated)
    # When / Then
    with pytest.raises(ValueError, match="measurements"):
        _ = bridge.read_inventory(9223)
