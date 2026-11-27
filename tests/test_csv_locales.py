# Copyright 2026 Capstone MCP contributors.
"""CSV locale, channel identity, and sample alignment regression tests."""

import math
import unicodedata
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

import pytest

from capstone_mcp.bridge import NativeInventory
from capstone_mcp.csv_data import CsvDataError, parse_csv_number, read_csv_page
from capstone_mcp.data_sources.adapters.csv_file import (
    read_csv_all_columns,
    read_csv_datasets,
    read_csv_series,
)
from capstone_mcp.data_sources.adapters.live_telemetry import LiveMeasurementAdapter
from capstone_mcp.session.telemetry import TelemetryBuffer, TelemetryClock


def test_numeric_cell_accepts_a_leading_bom_and_unicode_minus() -> None:
    assert parse_csv_number(" \ufeff\u22120,75 ") == Decimal("-0.75")
    with pytest.raises(CsvDataError, match="Invalid numeric CSV value"):
        _ = parse_csv_number("1\ufeff2")


@pytest.mark.parametrize("encoding", ["utf-8-sig", "cp949", "utf-16"])
@pytest.mark.parametrize("delimiter", [",", ";", "\t"])
def test_localized_csv_consistent_across_consumers(
    tmp_path: Path, encoding: str, delimiter: str,
) -> None:
    path = tmp_path / "locale.csv"
    text = delimiter.join(["시간 (s)", "전압 (V)"]) + "\n"
    text += delimiter.join(['"0,750"', '"1,500"']) + "\n"
    path.write_text(text, encoding=encoding)
    page = read_csv_page(str(path))
    assert page.columns[0].numeric_values == [Decimal("0.750")]
    assert page.columns[1].values == ["1,500"]
    assert [dataset.name for dataset in read_csv_datasets(path)] == ["시간", "전압"]
    result = read_csv_series(path, unicodedata.normalize("NFD", "시간"), "전압")
    assert result.x.values == [0.75]
    assert result.y.values == [1.5]
    assert read_csv_all_columns(path) == {"시간 (s)": [0.75], "전압 (V)": [1.5]}


def test_delimiter_inside_quoted_header_is_not_ambiguous(tmp_path: Path) -> None:
    path = tmp_path / "quoted.csv"
    path.write_text('"Voltage, rms";Time\n1,25;0,5\n', encoding="utf-8")
    assert read_csv_page(str(path)).columns[0].numeric_values == [Decimal("1.25")]


@pytest.mark.parametrize("text", ["a,b;c\n1,2;3\n", 'a,b\n"unterminated,2', "a;b\n1\n", "a\tb\n1\n"])
def test_ambiguous_or_malformed_csv_fails(tmp_path: Path, text: str) -> None:
    path = tmp_path / "bad.csv"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(CsvDataError):
        read_csv_page(str(path))


def test_invalid_encoding_has_domain_error(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_bytes(b"a,b\n\xff,1")
    with pytest.raises(CsvDataError, match="UTF-8"):
        read_csv_page(str(path))


def test_unknown_and_ambiguous_columns_are_not_substituted(tmp_path: Path) -> None:
    path = tmp_path / "channels.csv"
    path.write_text("Voltage A,Voltage B,Time\n1,2,0\n", encoding="utf-8")
    with pytest.raises(CsvDataError, match="not found"):
        read_csv_series(path, "Time", "Force")
    with pytest.raises(CsvDataError, match="ambiguous"):
        read_csv_series(path, "Time", "Voltage")
    assert read_csv_series(path, "Time", "Voltage B").y.values == [2]


def test_sparse_columns_keep_missing_sample_positions(tmp_path: Path) -> None:
    path = tmp_path / "sparse.csv"
    path.write_text("x,y\n,2\n1,\n3,4\n", encoding="utf-8")
    series = read_csv_series(path, "x", "y")
    assert series.x.values == [None, 1, 3]
    assert series.y.values == [2, None, 4]
    columns = read_csv_all_columns(path)
    assert math.isnan(columns["x"][0])
    assert math.isnan(columns["y"][1])
    assert columns["x"][1:] == [1, 3]
    assert columns["y"][::2] == [2, 4]


def test_duplicate_columns_do_not_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "duplicates.csv"
    path.write_text("x,x\n1,2\n", encoding="utf-8")
    with pytest.raises(CsvDataError, match="Duplicate"):
        read_csv_all_columns(path)


@pytest.mark.parametrize(("offset", "limit"), [(-1, 1), (0, 0), (0, -1)])
def test_invalid_page_bounds_rejected_before_io(offset: int, limit: int) -> None:
    with pytest.raises(CsvDataError, match="offset"):
        read_csv_page("does-not-exist.csv", offset, limit)


def test_live_adapter_reads_native_inventory_fields_without_invented_time() -> None:
    session = Mock()
    session.read_live_inventory.return_value = NativeInventory(
        sensors=[], measurements=[{
            "MeasurementName": "전압", "MeasurementEUID": "native-voltage", "Unit": "V",
        }],
    )
    session.debug_port = 9222
    session.telemetry = Mock(wraps=TelemetryBuffer())
    clock = TelemetryClock(clock_id="fixture", unit="seconds", origin="test-zero")
    session.telemetry.push_sample("native-voltage", 1.25, 10.0, clock=clock)
    session.telemetry.push_sample("native-voltage", 1.5, 10.5, clock=clock)
    adapter = LiveMeasurementAdapter(session=session)
    metadata = adapter.list_datasets()[0]
    assert (metadata.name, metadata.units, metadata.sample_count) == ("전압", "V", 2)
    session.telemetry.get_samples.assert_not_called()
    session.telemetry.get_snapshot.assert_not_called()
    series = adapter.get_series("인덱스", unicodedata.normalize("NFD", "전압"))
    assert series.x.values == [0, 1]
    assert series.y.values == [1.25, 1.5]
    timed = adapter.get_series("시간", "전압")
    assert timed.x.values == [0.0, 0.5]
    assert timed.metadata["x_basis"] == "declared_clock_elapsed"
    session.read_live_measurement.assert_not_called()
