# Copyright 2026 Capstone MCP contributors.
"""Page extraction preserves native values with bounded decoded allocations."""

import gc
import struct
import tracemalloc
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock
from xml.etree.ElementTree import tostring

import pytest
from defusedxml.ElementTree import fromstring

from capstone_mcp.capfiles import (
    CapFileError,
    list_cap_datasets,
    read_cap_dataset_page,
    read_cap_file,
)
from capstone_mcp.capfiles import archive as archive_parser
from capstone_mcp.data_sources import list_source_datasets
from tests.test_capfiles import _payload, _write_cap, _xml


@pytest.mark.parametrize("numeric", [False, True])
@pytest.mark.parametrize(("offset", "limit"), [(0, 2), (2, 2), (4, 3), (10, 2)])
def test_pages_match_complete_native_decode(
    tmp_path: Path, offset: int, limit: int, *, numeric: bool,
) -> None:
    path = tmp_path / "values.cap"
    xml = fromstring(_xml(5, storage_types=(0 if numeric else 7, 1)))
    independent = xml.find(".//IndependentStorageElement")
    assert independent is not None
    independent.set("IntervalCacheStartValue", "0.1")
    independent.set("IntervalCacheInterval", "0.03")
    values = ["1.5", "2.5", "3.5", "4.5", "5.5"]
    payload = b"".join(struct.pack("<Id", 1, float(v)) for v in values) if numeric else _payload(values)
    _write_cap(path, xml=tostring(xml), payload=payload)
    full = read_cap_file(path).datasets[0]
    page = read_cap_dataset_page(path, 0, offset, limit)
    assert page.dataset.count == 5
    assert page.raw_values == full.raw_values[offset:offset + limit]
    assert page.numeric_values == full.numeric_values[offset:offset + limit]
    assert page.independent_values == full.independent_values[offset:offset + limit]
    assert page.sample_indices == full.sample_indices[offset:offset + limit]


def test_metadata_listing_does_not_read_payloads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "metadata.cap"
    _write_cap(path, xml=_xml(2), payload=_payload(["1", "2"]))
    original = archive_parser._read_member
    read = Mock(wraps=original)
    monkeypatch.setattr(archive_parser, "_read_member", read)
    summaries = list_cap_datasets(path)
    assert summaries[0].count == 2
    assert [call.args[1].filename for call in read.call_args_list] == ["main.xml"]
    read.reset_mock()
    inventory = list_source_datasets(str(path))
    assert inventory[0].sample_count == 2
    assert inventory[0].name == summaries[0].name
    assert [call.args[1].filename for call in read.call_args_list] == ["main.xml"]


def test_large_numeric_page_allocates_less_than_full_decode(tmp_path: Path) -> None:
    path = tmp_path / "large.cap"
    count = 50_000
    _write_cap(path, xml=_xml(count, storage_types=(0, 4)), payload=struct.pack("<Id", 1, 1.25) * count)
    gc.collect()
    tracemalloc.start()
    try:
        page = read_cap_dataset_page(path, 0, count - 2, 2)
        _, page_peak = tracemalloc.get_traced_memory()
        tracemalloc.reset_peak()
        full = read_cap_file(path)
        _, full_peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert page.numeric_values == [Decimal("1.25"), Decimal("1.25")]
    assert page.sample_indices == [count - 2, count - 1]
    assert len(full.datasets[0].raw_values) == count
    assert full_peak > page_peak * 3


def test_empty_dataset_needs_no_payload_filename(tmp_path: Path) -> None:
    path = tmp_path / "empty.cap"
    xml = fromstring(_xml(0))
    dependent = xml.find(".//DependentStorageElement")
    assert dependent is not None
    del dependent.attrib["FileName"]
    _write_cap(path, xml=tostring(xml))
    assert read_cap_dataset_page(path, 0).raw_values == []


def test_nonfinite_text_values_remain_raw_and_numeric_missing(tmp_path: Path) -> None:
    path = tmp_path / "missing.cap"
    _write_cap(path, xml=_xml(4), payload=_payload(["NaN", "Infinity", "-Infinity", "1.25"]))
    page = read_cap_dataset_page(path, 0)
    assert page.raw_values == ["NaN", "Infinity", "-Infinity", "1.25"]
    assert page.numeric_values == [None, None, None, Decimal("1.25")]


@pytest.mark.parametrize("name", ["data/value:stream", "data/C:/value"])
def test_nested_windows_drive_or_stream_names_rejected(tmp_path: Path, name: str) -> None:
    path = tmp_path / "path.cap"
    _write_cap(path, xml=_xml(1, file_name=name), payload=_payload(["1"]), payload_name=name)
    with pytest.raises(CapFileError, match="Unsafe archive member"):
        read_cap_dataset_page(path, 0)


@pytest.mark.parametrize(("offset", "limit"), [(-1, 2), (0, 0), (0, 10_001)])
def test_page_bounds_checked_before_file_io(offset: int, limit: int) -> None:
    with pytest.raises(CapFileError, match="Dataset page"):
        read_cap_dataset_page("missing.cap", 0, offset, limit)
