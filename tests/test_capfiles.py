# Copyright 2026 Capstone MCP contributors.
"""Synthetic coverage for bounded Capstone experiment parsing."""

from __future__ import annotations

import struct
from decimal import Decimal
from typing import TYPE_CHECKING
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from capstone_mcp.capfile_models import CapValueKind
from capstone_mcp.capfiles import (
    CapFileError,
    extract_cap_datasets,
    read_cap_configuration,
    read_cap_file,
)

if TYPE_CHECKING:
    from pathlib import Path


def _payload(values: list[str], *, record_type: int = 2) -> bytes:
    records = bytearray()
    for value in values:
        encoded = value.encode("utf-16-le")
        records.extend(struct.pack("<II", record_type, len(encoded)))
        records.extend(encoded)
    return bytes(records)


def _xml(
    count: int,
    *,
    evaluated_type: str = "1",
    storage_types: tuple[int, int] = (7, 4),
    independent_count: int | None = None,
    file_name: str = r"data\values.tmp",
) -> bytes:
    independent_count = count if independent_count is None else independent_count
    dependent_storage_type, independent_storage_type = storage_types
    return f"""<?xml version="1.0" encoding="utf-8"?>
<DSProExperiment>
  <Header Version="1.12.0" Language="enu" />
  <Hardware Version="1">
    <Interface Type="1029" SubType="2" EUID="{{interface}}">
      <Channel Index="3">
        <Sensor Name="Synthetic Sensor" ID="42" EUID="{{sensor}}"
                SamplePeriod="0.05" UserTurnedSensorOn="TRUE">
          <Measurement Name="Synthetic Measurement" ID="4"
                       EUID="{{measurement}}" />
        </Sensor>
      </Channel>
    </Interface>
  </Hardware>
  <DataRepository>
    <DataSource EUID="{{source}}" LongName="Observed Value"
                MeasurementName="Observed Value" DefaultUnit="2048"
                BaseUnit="2048" UserDataEvaluatedType="{evaluated_type}"
                CustomMetadata="preserved">
      <DataSourceNumberFormatter FixedDecimals="3" />
      <DataSet DataSetID="{{dataset}}" Name="Set" DataGroup="2">
        <DataSegmentElement>
          <DependentStorageElement StorageType="{dependent_storage_type}"
              DataCacheDataSize="{count}" FileName="{file_name}" />
          <IndependentStorageElement StorageType="{independent_storage_type}"
              CacheDataCount="{independent_count}" />
        </DataSegmentElement>
      </DataSet>
    </DataSource>
  </DataRepository>
  <ExperimentControl>
    <ExperimentSettingsCollection>
      <ExperimentSettings SettingsId="1">
        <RecordingMode Value="Continuous" />
        <UseCommonSamplingRate Value="1" />
        <CommonSamplingRate Value="20" Units="7936" />
        <TargetSensor Value="{{sensor}}" />
        <ToolMode Value="Record" />
        <ActiveSensorSettings SensorUid="{{sensor}}" />
        <StartStopConditions>
          <StartCondition Active="0" Behavior="None" />
          <StopCondition Active="1" Behavior="Time" Threshold="5" />
        </StartStopConditions>
        <SensorSettingsCollection>
          <SensorSettings SensorUid="{{sensor}}" SamplingRate="20"
              Units="7936" TrueSamplingRate="0" TrueUnits="-1" />
        </SensorSettingsCollection>
      </ExperimentSettings>
    </ExperimentSettingsCollection>
  </ExperimentControl>
</DSProExperiment>
""".encode()


def _write_cap(
    path: Path,
    *,
    xml: bytes,
    payload: bytes | None = None,
    payload_name: str = "data/values.tmp",
) -> None:
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("main.xml", xml)
        if payload is not None:
            archive.writestr(payload_name, payload)


def test_reads_numeric_values_and_complete_configuration(tmp_path: Path) -> None:
    cap_path = tmp_path / "numeric.cap"
    raw_values = ["0.260", "0.61", "1.22"]
    _write_cap(
        cap_path,
        xml=_xml(count=len(raw_values)),
        payload=_payload(raw_values) + b"fixed-buffer-padding",
    )

    parsed = read_cap_file(cap_path)

    assert parsed.root_tag == "DSProExperiment"
    assert parsed.header is not None
    assert parsed.header.attributes["Version"] == "1.12.0"
    assert parsed.hardware is not None
    interface = parsed.hardware_interfaces[0]
    assert interface.euid == "{interface}"
    sensor = interface.sensors[0]
    assert sensor.sample_period == Decimal("0.05")
    assert sensor.channel_index == 3
    assert sensor.measurements[0].euid == "{measurement}"
    setting = parsed.experiment_settings[0]
    assert setting.recording_mode == "Continuous"
    assert setting.use_common_sampling_rate is True
    assert setting.common_sampling_rate == Decimal(20)
    assert setting.common_sampling_rate_unit_id == 7936
    assert setting.stop_condition == {
        "Active": "1",
        "Behavior": "Time",
        "Threshold": "5",
    }
    assert setting.sensor_settings[0].sampling_rate == Decimal(20)
    source = parsed.data_sources[0]
    assert source.value_kind is CapValueKind.NUMERIC
    assert source.default_unit_id == 2048
    assert source.attributes["CustomMetadata"] == "preserved"
    dataset = parsed.datasets[0]
    assert dataset.raw_values == raw_values
    assert dataset.numeric_values == [
        Decimal("0.260"),
        Decimal("0.61"),
        Decimal("1.22"),
    ]
    assert dataset.text_values is None
    assert dataset.sample_indices == [0, 1, 2]
    assert dataset.unit_id == 2048
    assert parsed.unconnected_sensors == []


@pytest.mark.parametrize("with_interface", [False, True])
def test_unconnected_sensor_metadata_is_separate_and_complete(
    tmp_path: Path, *, with_interface: bool,
) -> None:
    interface = (
        """<Interface EUID="{interface}"><Channel Index="2">
        <Sensor Name="Attached" EUID="{attached}" />
        </Channel></Interface>"""
        if with_interface else ""
    )
    xml = f"""<DSProExperiment><Hardware>
      {interface}
      <UnconnectedSensor>
        <Sensor Name="Stored Sensor" ID="42" EUID="{{stored}}"
                SamplePeriod="0.05" SensorZeroOnStart="TRUE">
          <Measurement Name="Angle" ID="1" EUID="{{angle}}" />
        </Sensor>
        <Sensor Name="Second Sensor" EUID="{{second}}" />
      </UnconnectedSensor>
    </Hardware></DSProExperiment>""".encode()
    path = tmp_path / "unconnected.cap"
    _write_cap(path, xml=xml)
    parsed = read_cap_file(path)
    config = read_cap_configuration(path)
    assert config.unconnected_sensors == parsed.unconnected_sensors
    assert len(config.unconnected_sensors) == 2
    sensor = config.unconnected_sensors[0]
    assert (sensor.name, sensor.euid, sensor.sensor_id) == (
        "Stored Sensor", "{stored}", "42",
    )
    assert sensor.sample_period == Decimal("0.05")
    assert sensor.interface_euid is None
    assert sensor.channel_index is None
    assert sensor.attributes["SensorZeroOnStart"] == "TRUE"
    assert sensor.measurements[0].name == "Angle"
    assert sensor.measurements[0].euid == "{angle}"
    attached = [s for i in config.hardware_interfaces for s in i.sensors]
    assert [s.euid for s in attached] == (["{attached}"] if with_interface else [])
    assert config.hardware is not None
    assert any(n.tag == "UnconnectedSensor" for n in config.hardware.children)


def test_missing_hardware_has_no_unconnected_sensors(tmp_path: Path) -> None:
    path = tmp_path / "empty.cap"
    _write_cap(path, xml=b"<DSProExperiment />")
    assert read_cap_configuration(path).unconnected_sensors == []


def test_preserves_text_values_that_look_numeric(tmp_path: Path) -> None:
    cap_path = tmp_path / "text.cap"
    values = ["Equal Mass Explosion", "0.500"]
    _write_cap(
        cap_path,
        xml=_xml(count=2, evaluated_type="2"),
        payload=_payload(values),
    )

    dataset = extract_cap_datasets(cap_path)[0]

    assert dataset.value_kind is CapValueKind.TEXT
    assert dataset.raw_values == values
    assert dataset.text_values == values
    assert dataset.numeric_values is None


def test_unknown_source_type_does_not_guess_numeric_values(tmp_path: Path) -> None:
    cap_path = tmp_path / "unknown.cap"
    _write_cap(
        cap_path,
        xml=_xml(count=1, evaluated_type="0"),
        payload=_payload(["12.5"]),
    )

    dataset = extract_cap_datasets(cap_path)[0]

    assert dataset.value_kind is CapValueKind.UNKNOWN
    assert dataset.raw_values == ["12.5"]
    assert dataset.numeric_values is None
    assert dataset.text_values is None


def test_rejects_truncated_declared_record_count(tmp_path: Path) -> None:
    cap_path = tmp_path / "truncated.cap"
    _write_cap(
        cap_path,
        xml=_xml(count=2),
        payload=_payload(["1.0"]),
    )

    with pytest.raises(CapFileError, match="Truncated record header 1"):
        _ = read_cap_file(cap_path)


def test_rejects_mismatched_implicit_index_count(tmp_path: Path) -> None:
    cap_path = tmp_path / "count-mismatch.cap"
    _write_cap(
        cap_path,
        xml=_xml(count=2, independent_count=1),
        payload=_payload(["1", "2"]),
    )

    with pytest.raises(CapFileError, match="counts do not match"):
        _ = read_cap_file(cap_path)


@pytest.mark.parametrize(
    ("dependent_type", "independent_type", "message"),
    [
        (6, 4, "Unsupported dependent storage type"),
        (7, 3, "Unsupported independent storage type"),
    ],
)
def test_rejects_unsupported_storage(
    tmp_path: Path,
    dependent_type: int,
    independent_type: int,
    message: str,
) -> None:
    cap_path = tmp_path / "unsupported.cap"
    _write_cap(
        cap_path,
        xml=_xml(
            count=1,
            storage_types=(dependent_type, independent_type),
        ),
        payload=_payload(["1"]),
    )

    with pytest.raises(CapFileError, match=message):
        _ = read_cap_file(cap_path)


def test_rejects_unsupported_payload_record_type(tmp_path: Path) -> None:
    cap_path = tmp_path / "record-type.cap"
    _write_cap(
        cap_path,
        xml=_xml(count=1),
        payload=_payload(["1"], record_type=3),
    )

    with pytest.raises(CapFileError, match="Unsupported record type 3"):
        _ = read_cap_file(cap_path)


def test_rejects_nonnumeric_value_from_numeric_source(tmp_path: Path) -> None:
    cap_path = tmp_path / "not-numeric.cap"
    _write_cap(
        cap_path,
        xml=_xml(count=1),
        payload=_payload(["not a number"]),
    )

    with pytest.raises(CapFileError, match="Invalid decimal"):
        _ = read_cap_file(cap_path)


def test_zero_record_dataset_does_not_require_payload(tmp_path: Path) -> None:
    cap_path = tmp_path / "empty.cap"
    _write_cap(cap_path, xml=_xml(count=0))

    dataset = extract_cap_datasets(cap_path)[0]

    assert dataset.raw_values == []
    assert dataset.numeric_values == []
    assert dataset.sample_indices == []


def test_rejects_non_zip_input(tmp_path: Path) -> None:
    cap_path = tmp_path / "not-a-zip.cap"
    _ = cap_path.write_bytes(b"not a ZIP archive")

    with pytest.raises(CapFileError, match="Invalid Capstone archive"):
        _ = read_cap_file(cap_path)


def test_rejects_forbidden_xml_entities(tmp_path: Path) -> None:
    cap_path = tmp_path / "entity.cap"
    xml = b"""<?xml version="1.0"?>
<!DOCTYPE DSProExperiment [<!ENTITY hidden "unsafe">]>
<DSProExperiment><Header Version="&hidden;" /></DSProExperiment>
"""
    _write_cap(cap_path, xml=xml)

    with pytest.raises(CapFileError, match="forbidden XML constructs"):
        _ = read_cap_file(cap_path)


def test_rejects_missing_payload_after_slash_normalization(
    tmp_path: Path,
) -> None:
    cap_path = tmp_path / "missing.cap"
    _write_cap(
        cap_path,
        xml=_xml(count=1, file_name=r"data\missing.tmp"),
        payload=_payload(["1"]),
        payload_name="data/values.tmp",
    )

    with pytest.raises(CapFileError, match="Dataset payload is missing"):
        _ = read_cap_file(cap_path)


def test_configuration_does_not_require_supported_arrays(tmp_path: Path) -> None:
    # Given: valid settings with an unsupported measured-data storage encoding.
    cap_path = tmp_path / "settings-only.cap"
    _write_cap(cap_path, xml=_xml(count=1, storage_types=(6, 3)))
    # When
    configuration = read_cap_configuration(cap_path)
    # Then: settings stay available; no array contents are fabricated.
    assert configuration.experiment_settings[0].common_sampling_rate == Decimal(20)
    assert configuration.data_sources[0].euid == "{source}"
    assert "datasets" not in configuration.model_dump()


def test_numeric_cache_applies_offset_and_reconstructs_interval_axis(
    tmp_path: Path,
) -> None:
    # Given: the type-0/type-1 layout found in the native reader.
    cap_path = tmp_path / "numeric-cache.cap"
    xml = _xml(count=3, storage_types=(0, 1)).replace(
        b'StorageType="0"', b'StorageType="0" DataOffsetValue="0.5"',
    ).replace(
        b'CacheDataCount="3"',
        b'CacheDataCount="3" IntervalCacheStartValue="1" IntervalCacheInterval="0.25"',
    )
    payload = b"".join(struct.pack("<Id", 1, value) for value in (-1.25, 0, 2.5))
    _write_cap(cap_path, xml=xml, payload=payload)
    # When
    dataset = extract_cap_datasets(cap_path)[0]
    # Then
    assert dataset.numeric_values == [Decimal("-0.75"), Decimal("0.5"), Decimal(3)]
    assert dataset.independent_values == [Decimal(1), Decimal("1.25"), Decimal("1.5")]
    assert dataset.independent_kind == "interval"
    assert dataset.scalar_attributes == [1, 1, 1]


def test_numeric_cache_preserves_missing_samples_and_attribute_bits(
    tmp_path: Path,
) -> None:
    # Given
    cap_path = tmp_path / "invalid-values.cap"
    payload = (
        struct.pack("<Id", 0x101, 12.5)
        + struct.pack("<Id", 0, 99)
        + struct.pack("<Id", 3, 99)
    )
    _write_cap(cap_path, xml=_xml(count=3, storage_types=(0, 4)), payload=payload)
    # When
    dataset = extract_cap_datasets(cap_path)[0]
    # Then
    assert dataset.numeric_values == [Decimal("12.5"), None, None]
    assert dataset.scalar_attributes == [0x101, 0, 3]
    assert dataset.sample_indices == [0, 1, 2]


def test_numeric_cache_rejects_short_payload(tmp_path: Path) -> None:
    # Given
    cap_path = tmp_path / "short-numeric.cap"
    _write_cap(
        cap_path, xml=_xml(count=2, storage_types=(0, 4)),
        payload=struct.pack("<Id", 1, 1.0),
    )
    # When / Then
    with pytest.raises(CapFileError):
        _ = extract_cap_datasets(cap_path)
