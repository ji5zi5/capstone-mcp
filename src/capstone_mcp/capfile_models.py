# Copyright 2026 Capstone MCP contributors.
"""Typed, immutable observations from PASCO Capstone experiment archives."""

from __future__ import annotations

import decimal
from enum import StrEnum
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

type DecimalValue = decimal.Decimal


class CapFileModel(BaseModel):
    """Immutable data read from a Capstone experiment archive."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)


class CapValueKind(StrEnum):
    """Value semantics explicitly declared by a Capstone data source."""

    NUMERIC = "numeric"
    TEXT = "text"
    UNKNOWN = "unknown"


class CapXmlNode(CapFileModel):
    """Lossless metadata subtree for sections without a stable public schema."""

    tag: str
    attributes: dict[str, str]
    text: str | None
    children: list[CapXmlNode]


class CapSensorSetting(CapFileModel):
    """Per-sensor sampling configuration within one experiment setting."""

    sensor_euid: str
    sampling_rate: DecimalValue | None
    sampling_rate_unit_id: int | None
    true_sampling_rate: DecimalValue | None
    true_unit_id: int | None
    attributes: dict[str, str]


class CapExperimentSetting(CapFileModel):
    """One saved recording configuration and its complete XML metadata."""

    settings_id: str | None
    recording_mode: str | None
    use_common_sampling_rate: bool | None
    common_sampling_rate: DecimalValue | None
    common_sampling_rate_unit_id: int | None
    target_sensor_euid: str | None
    tool_mode: str | None
    active_sensor_euid: str | None
    start_condition: dict[str, str] | None
    stop_condition: dict[str, str] | None
    sensor_settings: list[CapSensorSetting]
    metadata: CapXmlNode


class CapHardwareMeasurement(CapFileModel):
    """Measurement exposed by a configured hardware sensor."""

    euid: str | None
    measurement_id: str | None
    name: str | None
    attributes: dict[str, str]


class CapHardwareSensor(CapFileModel):
    """Configured hardware sensor with sample period and measurements."""

    euid: str | None
    sensor_id: str | None
    name: str | None
    sample_period: DecimalValue | None
    interface_euid: str | None
    channel_index: int | None
    attributes: dict[str, str]
    measurements: list[CapHardwareMeasurement]


class CapHardwareInterface(CapFileModel):
    """Configured hardware interface and all sensors below it."""

    euid: str | None
    interface_type: str | None
    subtype: str | None
    attributes: dict[str, str]
    sensors: list[CapHardwareSensor]


class CapDataSource(CapFileModel):
    """Data source metadata, preserving every source attribute and child."""

    euid: str | None
    measurement_name: str | None
    long_name: str | None
    short_name: str | None
    symbol_name: str | None
    default_unit_id: int | None
    base_unit_id: int | None
    value_kind: CapValueKind
    attributes: dict[str, str]
    metadata: CapXmlNode


class CapDataSet(CapFileModel):
    """One dependent value array and its implicit zero-based sample indices."""

    data_set_id: str | None
    name: str | None
    source_euid: str | None
    source_name: str | None
    unit_id: int | None
    value_kind: CapValueKind
    raw_values: list[str]
    numeric_values: list[DecimalValue | None] | None
    text_values: list[str] | None
    sample_indices: list[int]
    independent_values: list[DecimalValue | None]
    independent_kind: Literal["index", "interval", "stored"]
    scalar_attributes: list[int] | None
    dependent_storage_type: int
    independent_storage_type: int
    attributes: dict[str, str]
    metadata: CapXmlNode


class CapConfiguration(CapFileModel):
    """Saved experiment settings, independent of support for its array encoding."""

    file_name: str
    root_tag: str
    header: CapXmlNode | None
    hardware: CapXmlNode | None
    hardware_interfaces: list[CapHardwareInterface]
    unconnected_sensors: list[CapHardwareSensor] = Field(default_factory=list)
    experiment_settings: list[CapExperimentSetting]
    data_sources: list[CapDataSource]
    workspace: CapXmlNode | None
    calculations: CapXmlNode | None


class CapFile(CapConfiguration):
    """Parsed configuration and decoded datasets from one `.cap` archive."""

    datasets: list[CapDataSet]


class CapDatasetSummary(CapFileModel):
    """Index and provenance for one decoded dataset in a saved file."""

    index: int
    dataset_id: str | None
    source_euid: str | None
    name: str | None
    unit_id: int | None
    value_kind: CapValueKind
    count: int


class CapDatasetPage(CapFileModel):
    """A bounded sample page; indices are not asserted to be timestamps."""

    dataset: CapDatasetSummary
    offset: int
    sample_indices: list[int]
    raw_values: list[str]
    numeric_values: list[DecimalValue | None] | None
    independent_values: list[DecimalValue | None]
    independent_kind: Literal["index", "interval", "stored"]
