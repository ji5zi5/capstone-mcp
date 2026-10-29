# Copyright 2026 Capstone MCP contributors.
"""Bounded, read-only parsing for PASCO Capstone `.cap` experiment archives."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Final, Literal
from xml.etree.ElementTree import Element, ParseError
from zipfile import BadZipFile, LargeZipFile, ZipFile, ZipInfo

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring

from capstone_mcp.capfile_models import (
    CapConfiguration,
    CapDataSet,
    CapDataSource,
    CapExperimentSetting,
    CapFile,
    CapHardwareInterface,
    CapHardwareMeasurement,
    CapHardwareSensor,
    CapSensorSetting,
    CapValueKind,
    CapXmlNode,
)
from capstone_mcp.numeric_storage import (
    NumericStorageError,
    decode_numeric_records,
    interval_values,
)

MAX_ARCHIVE_BYTES: Final = 64 * 1024 * 1024
MAX_ARCHIVE_ENTRIES: Final = 4096
MAX_TOTAL_UNCOMPRESSED_BYTES: Final = 64 * 1024 * 1024
MAX_XML_BYTES: Final = 8 * 1024 * 1024
MAX_PAYLOAD_BYTES: Final = 16 * 1024 * 1024
MAX_XML_NODES: Final = 100_000
MAX_XML_DEPTH: Final = 128
MAX_RECORDS: Final = 1_000_000
MAX_VALUE_BYTES: Final = 1024 * 1024
RECORD_HEADER_SIZE: Final = 8
TEXT_RECORD_TYPE: Final = 2
DEPENDENT_STORAGE_TYPE: Final = 7
INDEPENDENT_STORAGE_TYPE: Final = 4
NUMERIC_STORAGE_TYPE: Final = 0
INTERVAL_STORAGE_TYPE: Final = 1


class CapFileError(ValueError):
    """Raised when a `.cap` archive is invalid, ambiguous, or unsupported."""


def _normalize_member_name(name: str) -> str:
    normalized = name.replace("\\", "/")
    if (
        not normalized
        or "\x00" in normalized
        or normalized.startswith("/")
    ):
        msg = f"Unsafe archive member path: {name!r}."
        raise CapFileError(msg)
    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    if not parts or ".." in parts or ":" in parts[0]:
        msg = f"Unsafe archive member path: {name!r}."
        raise CapFileError(msg)
    return "/".join(parts)


def _archive_members(archive: ZipFile) -> dict[str, ZipInfo]:
    infos = archive.infolist()
    if len(infos) > MAX_ARCHIVE_ENTRIES:
        msg = f"Archive contains more than {MAX_ARCHIVE_ENTRIES} entries."
        raise CapFileError(msg)
    total_size = 0
    members: dict[str, ZipInfo] = {}
    for info in infos:
        if info.flag_bits & 0x1:
            msg = f"Encrypted archive member is unsupported: {info.filename!r}."
            raise CapFileError(msg)
        total_size += info.file_size
        if total_size > MAX_TOTAL_UNCOMPRESSED_BYTES:
            msg = "Archive uncompressed size exceeds the safety limit."
            raise CapFileError(msg)
        if info.is_dir():
            continue
        normalized = _normalize_member_name(info.filename)
        if normalized in members:
            msg = f"Ambiguous duplicate archive member: {normalized!r}."
            raise CapFileError(msg)
        members[normalized] = info
    return members


def _read_member(
    archive: ZipFile,
    info: ZipInfo,
    *,
    maximum_size: int,
) -> bytes:
    if info.file_size > maximum_size:
        msg = f"Archive member {info.filename!r} exceeds the safety limit."
        raise CapFileError(msg)
    try:
        data = archive.read(info)
    except (BadZipFile, NotImplementedError, RuntimeError, OSError) as exc:
        msg = f"Unable to read archive member {info.filename!r}."
        raise CapFileError(msg) from exc
    if len(data) != info.file_size or len(data) > maximum_size:
        msg = f"Archive member {info.filename!r} has an invalid size."
        raise CapFileError(msg)
    return data


def _single_child(element: Element, tag: str) -> Element | None:
    matches = [child for child in element if child.tag == tag]
    if len(matches) > 1:
        msg = f"Ambiguous repeated <{tag}> inside <{element.tag}>."
        raise CapFileError(msg)
    return matches[0] if matches else None


def _required_single_child(element: Element, tag: str) -> Element:
    child = _single_child(element, tag)
    if child is None:
        msg = f"Missing <{tag}> inside <{element.tag}>."
        raise CapFileError(msg)
    return child


def _optional_attribute(element: Element | None, name: str) -> str | None:
    return None if element is None else element.attrib.get(name)


def _decimal(
    raw: str | None,
    *,
    context: str,
) -> Decimal | None:
    if raw is None:
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        msg = f"Invalid decimal {raw!r} in {context}."
        raise CapFileError(msg) from exc
    if not value.is_finite():
        msg = f"Non-finite decimal {raw!r} in {context}."
        raise CapFileError(msg)
    return value


def _integer(
    raw: str | None,
    *,
    context: str,
) -> int | None:
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        msg = f"Invalid integer {raw!r} in {context}."
        raise CapFileError(msg) from exc


def _boolean(raw: str | None, *, context: str) -> bool | None:
    if raw is None:
        return None
    if raw in {"1", "TRUE", "true"}:
        return True
    if raw in {"0", "FALSE", "false"}:
        return False
    msg = f"Invalid boolean {raw!r} in {context}."
    raise CapFileError(msg)


def _xml_node(element: Element, *, depth: int = 0) -> CapXmlNode:
    if depth > MAX_XML_DEPTH:
        msg = f"XML metadata exceeds maximum depth {MAX_XML_DEPTH}."
        raise CapFileError(msg)
    stripped = (element.text or "").strip()
    return CapXmlNode(
        tag=element.tag,
        attributes=dict(element.attrib),
        text=stripped or None,
        children=[_xml_node(child, depth=depth + 1) for child in element],
    )


def _value_kind(element: Element) -> CapValueKind:
    evaluated_type = element.attrib.get("UserDataEvaluatedType")
    if evaluated_type == "1":
        return CapValueKind.NUMERIC
    if evaluated_type == "2":
        return CapValueKind.TEXT
    return CapValueKind.UNKNOWN


def _source_name(element: Element) -> str | None:
    for attribute in ("LongName", "MeasurementName", "ShortName", "SymbolName"):
        value = element.attrib.get(attribute)
        if value:
            return value
    return None


def _data_source(element: Element) -> CapDataSource:
    return CapDataSource(
        euid=element.attrib.get("EUID"),
        measurement_name=element.attrib.get("MeasurementName"),
        long_name=element.attrib.get("LongName"),
        short_name=element.attrib.get("ShortName"),
        symbol_name=element.attrib.get("SymbolName"),
        default_unit_id=_integer(
            element.attrib.get("DefaultUnit"),
            context="DataSource.DefaultUnit",
        ),
        base_unit_id=_integer(
            element.attrib.get("BaseUnit"),
            context="DataSource.BaseUnit",
        ),
        value_kind=_value_kind(element),
        attributes=dict(element.attrib),
        metadata=_xml_node(element),
    )


def _sensor_setting(element: Element) -> CapSensorSetting:
    sensor_euid = element.attrib.get("SensorUid")
    if sensor_euid is None:
        msg = "SensorSettings is missing SensorUid."
        raise CapFileError(msg)
    return CapSensorSetting(
        sensor_euid=sensor_euid,
        sampling_rate=_decimal(
            element.attrib.get("SamplingRate"),
            context="SensorSettings.SamplingRate",
        ),
        sampling_rate_unit_id=_integer(
            element.attrib.get("Units"),
            context="SensorSettings.Units",
        ),
        true_sampling_rate=_decimal(
            element.attrib.get("TrueSamplingRate"),
            context="SensorSettings.TrueSamplingRate",
        ),
        true_unit_id=_integer(
            element.attrib.get("TrueUnits"),
            context="SensorSettings.TrueUnits",
        ),
        attributes=dict(element.attrib),
    )


def _experiment_setting(element: Element) -> CapExperimentSetting:
    recording_mode = _single_child(element, "RecordingMode")
    use_common_rate = _single_child(element, "UseCommonSamplingRate")
    common_rate = _single_child(element, "CommonSamplingRate")
    target_sensor = _single_child(element, "TargetSensor")
    tool_mode = _single_child(element, "ToolMode")
    active_sensor = _single_child(element, "ActiveSensorSettings")
    conditions = _single_child(element, "StartStopConditions")
    start = None if conditions is None else _single_child(conditions, "StartCondition")
    stop = None if conditions is None else _single_child(conditions, "StopCondition")
    collection = _single_child(element, "SensorSettingsCollection")
    sensor_settings = (
        []
        if collection is None
        else [
            _sensor_setting(child)
            for child in collection
            if child.tag == "SensorSettings"
        ]
    )
    return CapExperimentSetting(
        settings_id=element.attrib.get("SettingsId"),
        recording_mode=_optional_attribute(recording_mode, "Value"),
        use_common_sampling_rate=_boolean(
            _optional_attribute(use_common_rate, "Value"),
            context="UseCommonSamplingRate.Value",
        ),
        common_sampling_rate=_decimal(
            _optional_attribute(common_rate, "Value"),
            context="CommonSamplingRate.Value",
        ),
        common_sampling_rate_unit_id=_integer(
            _optional_attribute(common_rate, "Units"),
            context="CommonSamplingRate.Units",
        ),
        target_sensor_euid=_optional_attribute(target_sensor, "Value"),
        tool_mode=_optional_attribute(tool_mode, "Value"),
        active_sensor_euid=_optional_attribute(active_sensor, "SensorUid"),
        start_condition=None if start is None else dict(start.attrib),
        stop_condition=None if stop is None else dict(stop.attrib),
        sensor_settings=sensor_settings,
        metadata=_xml_node(element),
    )


def _ancestor(
    element: Element,
    parent_by_child: dict[Element, Element],
    tag: str,
) -> Element | None:
    current = element
    while current in parent_by_child:
        current = parent_by_child[current]
        if current.tag == tag:
            return current
    return None


def _hardware_sensor(
    sensor: Element, *, interface_euid: str | None,
    channel: Element | None,
) -> CapHardwareSensor:
    return CapHardwareSensor(
        euid=sensor.attrib.get("EUID"),
        sensor_id=sensor.attrib.get("ID"),
        name=sensor.attrib.get("Name"),
        sample_period=_decimal(
            sensor.attrib.get("SamplePeriod"), context="Sensor.SamplePeriod",
        ),
        interface_euid=interface_euid,
        channel_index=_integer(
            None if channel is None else channel.attrib.get("Index"),
            context="Channel.Index",
        ),
        attributes=dict(sensor.attrib),
        measurements=[
            CapHardwareMeasurement(
                euid=measurement.attrib.get("EUID"),
                measurement_id=measurement.attrib.get("ID"),
                name=measurement.attrib.get("Name"),
                attributes=dict(measurement.attrib),
            )
            for measurement in sensor.iter("Measurement")
        ],
    )


def _unconnected_sensors(hardware: Element | None) -> list[CapHardwareSensor]:
    if hardware is None:
        return []
    return [
        _hardware_sensor(sensor, interface_euid=None, channel=None)
        for group in hardware.iter("UnconnectedSensor")
        for sensor in group.findall("Sensor")
    ]


def _hardware_interfaces(
    hardware: Element | None,
    parent_by_child: dict[Element, Element],
) -> list[CapHardwareInterface]:
    if hardware is None:
        return []
    interfaces: list[CapHardwareInterface] = []
    for interface in hardware.iter("Interface"):
        sensors: list[CapHardwareSensor] = []
        for sensor in interface.iter("Sensor"):
            nearest_interface = _ancestor(sensor, parent_by_child, "Interface")
            if nearest_interface is not interface:
                continue
            channel = _ancestor(sensor, parent_by_child, "Channel")
            sensors.append(
                _hardware_sensor(
                    sensor, interface_euid=interface.attrib.get("EUID"),
                    channel=channel,
                ),
            )
        interfaces.append(
            CapHardwareInterface(
                euid=interface.attrib.get("EUID"),
                interface_type=interface.attrib.get("Type"),
                subtype=interface.attrib.get("SubType"),
                attributes=dict(interface.attrib),
                sensors=sensors,
            ),
        )
    return interfaces


def _records(payload: bytes, count: int, *, member_name: str) -> list[str]:
    values: list[str] = []
    offset = 0
    for record_index in range(count):
        if len(payload) - offset < RECORD_HEADER_SIZE:
            msg = (
                f"Truncated record header {record_index} in "
                f"{member_name!r}."
            )
            raise CapFileError(msg)
        record_type = int.from_bytes(payload[offset : offset + 4], "little")
        value_size = int.from_bytes(payload[offset + 4 : offset + 8], "little")
        offset += RECORD_HEADER_SIZE
        if record_type != TEXT_RECORD_TYPE:
            msg = (
                f"Unsupported record type {record_type} in "
                f"{member_name!r}."
            )
            raise CapFileError(msg)
        if value_size > MAX_VALUE_BYTES or value_size % 2:
            msg = f"Invalid UTF-16 value size in {member_name!r}."
            raise CapFileError(msg)
        end = offset + value_size
        if end > len(payload):
            msg = f"Truncated UTF-16 value {record_index} in {member_name!r}."
            raise CapFileError(msg)
        try:
            value = payload[offset:end].decode("utf-16-le")
        except UnicodeDecodeError as exc:
            msg = f"Invalid UTF-16 value {record_index} in {member_name!r}."
            raise CapFileError(msg) from exc
        values.append(value)
        offset = end
    return values


def _dataset_storage(element: Element) -> tuple[int, int, int, str]:
    segments = [child for child in element if child.tag == "DataSegmentElement"]
    if len(segments) != 1:
        msg = "Each DataSet must contain exactly one DataSegmentElement."
        raise CapFileError(msg)
    segment = segments[0]
    dependent = _required_single_child(segment, "DependentStorageElement")
    independent = _required_single_child(segment, "IndependentStorageElement")
    dependent_type = _integer(
        dependent.attrib.get("StorageType"),
        context="DependentStorageElement.StorageType",
    )
    independent_type = _integer(
        independent.attrib.get("StorageType"),
        context="IndependentStorageElement.StorageType",
    )
    if dependent_type not in (DEPENDENT_STORAGE_TYPE, NUMERIC_STORAGE_TYPE):
        msg = f"Unsupported dependent storage type: {dependent_type!r}."
        raise CapFileError(msg)
    if independent_type not in (
        INDEPENDENT_STORAGE_TYPE, NUMERIC_STORAGE_TYPE, INTERVAL_STORAGE_TYPE,
    ):
        msg = f"Unsupported independent storage type: {independent_type!r}."
        raise CapFileError(msg)
    count = _integer(
        dependent.attrib.get("DataCacheDataSize"),
        context="DependentStorageElement.DataCacheDataSize",
    )
    independent_count = _integer(
        independent.attrib.get(
            "DataCacheDataSize" if independent_type == NUMERIC_STORAGE_TYPE
            else "CacheDataCount",
        ),
        context="IndependentStorageElement.CacheDataCount",
    )
    if count is None or count < 0 or count > MAX_RECORDS:
        msg = "Dependent record count is missing or outside the safety limit."
        raise CapFileError(msg)
    if independent_count != count:
        msg = "Dependent and independent dataset counts do not match."
        raise CapFileError(msg)
    member_name_raw = dependent.attrib.get("FileName")
    if member_name_raw is None:
        msg = "DependentStorageElement is missing FileName."
        raise CapFileError(msg)
    member_name = _normalize_member_name(member_name_raw)
    return dependent_type, independent_type, count, member_name


def _numeric_payload(
    element: Element, count: int, archive: ZipFile, members: dict[str, ZipInfo],
) -> tuple[list[str], list[Decimal | None], list[int]]:
    if element.get("DataCacheStorageType") == "-1":
        msg = "Legacy string caches marked StorageType=0 are not numeric caches."
        raise CapFileError(msg)
    offset = _decimal(element.get("DataOffsetValue", "0"), context="DataOffsetValue")
    if offset is None:
        msg = "Numeric cache offset is missing."
        raise CapFileError(msg)
    payload = b""
    if count:
        name = _normalize_member_name(element.get("FileName", ""))
        if name not in members:
            msg = f"Dataset payload is missing: {name!r}."
            raise CapFileError(msg)
        payload = _read_member(archive, members[name], maximum_size=MAX_PAYLOAD_BYTES)
    try:
        decoded = decode_numeric_records(payload, count, offset)
    except NumericStorageError as exc:
        raise CapFileError(str(exc)) from exc
    return decoded.text, decoded.values, decoded.attributes


def _independent_coordinates(
    element: Element, count: int, storage_type: int,
    archive: ZipFile, members: dict[str, ZipInfo],
) -> tuple[list[Decimal | None], Literal["index", "interval", "stored"]]:
    if storage_type == NUMERIC_STORAGE_TYPE:
        _, values, _ = _numeric_payload(element, count, archive, members)
        return values, "stored"
    if storage_type == INTERVAL_STORAGE_TYPE:
        exceptions = element.find("AttributeExceptionList")
        if exceptions is not None and len(exceptions):
            msg = "Interval attribute exceptions require an unsupported decoder."
            raise CapFileError(msg)
        start = _decimal(
            element.get("IntervalCacheStartValue"), context="IntervalCacheStartValue",
        )
        interval = _decimal(
            element.get("IntervalCacheInterval"), context="IntervalCacheInterval",
        )
        if start is None or interval is None:
            msg = "Interval cache requires explicit start and interval."
            raise CapFileError(msg)
        try:
            coordinates: list[Decimal | None] = list(
                interval_values(start, interval, count),
            )
        except NumericStorageError as exc:
            raise CapFileError(str(exc)) from exc
        return coordinates, "interval"
    return [Decimal(index) for index in range(count)], "index"


def _dataset(
    element: Element,
    *,
    source_element: Element,
    source: CapDataSource,
    archive: ZipFile,
    members: dict[str, ZipInfo],
) -> CapDataSet:
    dependent_type, independent_type, count, member_name = _dataset_storage(
        element,
    )
    segment = _required_single_child(element, "DataSegmentElement")
    dependent = _required_single_child(segment, "DependentStorageElement")
    independent = _required_single_child(segment, "IndependentStorageElement")
    values: list[str] = []
    numeric_values: list[Decimal | None] | None = None
    scalar_attributes: list[int] | None = None
    value_kind = source.value_kind
    if dependent_type == NUMERIC_STORAGE_TYPE:
        values, numeric_values, scalar_attributes = _numeric_payload(
            dependent, count, archive, members,
        )
        value_kind = CapValueKind.NUMERIC
    elif count:
        info = members.get(member_name)
        if info is None:
            msg = f"Dataset payload is missing: {member_name!r}."
            raise CapFileError(msg)
        values = _records(
            _read_member(archive, info, maximum_size=MAX_PAYLOAD_BYTES),
            count,
            member_name=member_name,
        )
    text_values: list[str] | None = None
    if (
        dependent_type != NUMERIC_STORAGE_TYPE
        and source.value_kind is CapValueKind.NUMERIC
    ):
        numeric_values = []
        for index, raw in enumerate(values):
            numeric = _decimal(raw, context=f"{member_name} record {index}")
            if numeric is None:
                msg = f"Numeric dataset value {index} is missing."
                raise CapFileError(msg)
            numeric_values.append(numeric)
    elif (
        dependent_type != NUMERIC_STORAGE_TYPE
        and source.value_kind is CapValueKind.TEXT
    ):
        text_values = list(values)
    independent_values, independent_kind = _independent_coordinates(
        independent, count, independent_type, archive, members,
    )
    return CapDataSet(
        data_set_id=element.attrib.get("DataSetID"),
        name=element.attrib.get("Name"),
        source_euid=source.euid,
        source_name=_source_name(source_element),
        unit_id=source.default_unit_id,
        value_kind=value_kind,
        raw_values=values,
        numeric_values=numeric_values,
        text_values=text_values,
        sample_indices=list(range(count)),
        independent_values=independent_values,
        independent_kind=independent_kind,
        scalar_attributes=scalar_attributes,
        dependent_storage_type=dependent_type,
        independent_storage_type=independent_type,
        attributes=dict(element.attrib),
        metadata=_xml_node(element),
    )


def _parse_archive(
    archive: ZipFile,
    *,
    file_name: str,
    include_data: bool,
) -> CapFile:
    members = _archive_members(archive)
    main_info = members.get("main.xml")
    if main_info is None:
        msg = "Archive is missing main.xml."
        raise CapFileError(msg)
    xml_bytes = _read_member(archive, main_info, maximum_size=MAX_XML_BYTES)
    try:
        root = fromstring(xml_bytes)
    except (DefusedXmlException, ParseError, ValueError) as exc:
        msg = "main.xml is malformed or contains forbidden XML constructs."
        raise CapFileError(msg) from exc
    if root.tag != "DSProExperiment":
        msg = f"Unsupported main.xml root element: {root.tag!r}."
        raise CapFileError(msg)
    nodes = list(root.iter())
    if len(nodes) > MAX_XML_NODES:
        msg = f"main.xml contains more than {MAX_XML_NODES} elements."
        raise CapFileError(msg)
    parent_by_child = {child: parent for parent in nodes for child in parent}
    header = _single_child(root, "Header")
    hardware = _single_child(root, "Hardware")
    workspace = _single_child(root, "Workspace")
    calculations = _single_child(root, "CalculationManager")
    source_elements = list(root.iter("DataSource"))
    source_models = [_data_source(element) for element in source_elements]
    source_by_element = dict(zip(source_elements, source_models, strict=True))
    datasets: list[CapDataSet] = []
    for element in root.iter("DataSet") if include_data else ():
        source_element = _ancestor(element, parent_by_child, "DataSource")
        if source_element is None:
            msg = "DataSet is not linked to a DataSource."
            raise CapFileError(msg)
        datasets.append(
            _dataset(
                element,
                source_element=source_element,
                source=source_by_element[source_element],
                archive=archive,
                members=members,
            ),
        )
    return CapFile(
        file_name=file_name,
        root_tag=root.tag,
        header=None if header is None else _xml_node(header),
        hardware=None if hardware is None else _xml_node(hardware),
        hardware_interfaces=_hardware_interfaces(hardware, parent_by_child),
        unconnected_sensors=_unconnected_sensors(hardware),
        experiment_settings=[
            _experiment_setting(element)
            for element in root.iter("ExperimentSettings")
        ],
        data_sources=source_models,
        workspace=None if workspace is None else _xml_node(workspace),
        calculations=None if calculations is None else _xml_node(calculations),
        datasets=datasets,
    )


def read_cap_file(path: str | Path, *, include_data: bool = True) -> CapFile:
    """Read one bounded Capstone archive without extracting it to disk."""
    archive_path = Path(path)
    try:
        file_size = archive_path.stat().st_size
    except OSError as exc:
        msg = f"Unable to access Capstone archive: {archive_path}."
        raise CapFileError(msg) from exc
    if file_size > MAX_ARCHIVE_BYTES:
        msg = f"Archive exceeds the {MAX_ARCHIVE_BYTES}-byte safety limit."
        raise CapFileError(msg)
    try:
        with ZipFile(archive_path, mode="r", allowZip64=False) as archive:
            return _parse_archive(
                archive, file_name=archive_path.name, include_data=include_data,
            )
    except CapFileError:
        raise
    except (BadZipFile, LargeZipFile, OSError) as exc:
        msg = f"Invalid Capstone archive: {archive_path}."
        raise CapFileError(msg) from exc


def extract_cap_datasets(path: str | Path) -> list[CapDataSet]:
    """Read all dataset arrays and source semantics from one `.cap` file."""
    return read_cap_file(path).datasets


def read_cap_configuration(path: str | Path) -> CapConfiguration:
    """Inspect saved settings without requiring a supported dataset encoding."""
    parsed = read_cap_file(path, include_data=False)
    return CapConfiguration(
        file_name=parsed.file_name, root_tag=parsed.root_tag,
        header=parsed.header, hardware=parsed.hardware,
        hardware_interfaces=parsed.hardware_interfaces,
        unconnected_sensors=parsed.unconnected_sensors,
        experiment_settings=parsed.experiment_settings,
        data_sources=parsed.data_sources,
        workspace=parsed.workspace, calculations=parsed.calculations,
    )
