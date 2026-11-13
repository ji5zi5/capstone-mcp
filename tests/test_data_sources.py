# Copyright 2026 Capstone MCP contributors.
"""Tests for the unified ExperimentDataSource seam and adapters."""

from pathlib import Path

import pytest

from capstone_mcp.data_sources import (
    CapArchiveAdapter,
    CsvTableAdapter,
    DataSeries,
    ExperimentSeries,
    LiveSessionAdapter,
    get_experiment_series,
    list_source_datasets,
)
from capstone_mcp.data_sources.adapters.csv_file import read_csv_all_columns
from capstone_mcp.displays import ReadTableResult


def test_data_series_creation() -> None:
    """Ensure DataSeries model validates and stores values cleanly."""
    series = DataSeries(name="Time", units="s", values=[0.0, 1.0, 2.0, None])
    assert series.name == "Time"
    assert series.units == "s"
    assert len(series.values) == 4
    assert series.clean_floats() == [0.0, 1.0, 2.0]


def test_csv_adapter_extracts_experiment_series(tmp_path: Path) -> None:
    """Verify CSV adapter reads and maps columns into ExperimentSeries."""
    csv_file = tmp_path / "test_data.csv"
    csv_content = (
        "Time (s),Voltage (V)\n"
        "0.0,1.2\n"
        "0.1,1.5\n"
        "0.2,1.8\n"
    )
    csv_file.write_text(csv_content, encoding="utf-8")

    result = get_experiment_series(csv_file, "Time", "Voltage")
    assert isinstance(result, ExperimentSeries)
    assert result.x.name == "Time"
    assert result.x.clean_floats() == [0.0, 0.1, 0.2]
    assert result.y.clean_floats() == [1.2, 1.5, 1.8]


def test_csv_adapter_list_datasets(tmp_path: Path) -> None:
    """Verify CSV adapter lists column metadata."""
    csv_file = tmp_path / "test_data.csv"
    csv_content = "Time (s),Force (N)\n0.0,5.0\n1.0,10.0\n"
    csv_file.write_text(csv_content, encoding="utf-8")

    datasets = list_source_datasets(csv_file)
    assert len(datasets) == 2
    names = {d.name for d in datasets}
    assert "Time" in names
    assert "Force" in names


def test_unsupported_source_raises(tmp_path: Path) -> None:
    """Ensure unknown file extensions raise ValueError."""
    unknown = tmp_path / "data.unsupported_ext"
    unknown.write_text("hello", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported data source"):
        get_experiment_series(unknown, "x", "y")


def test_csv_table_adapter_class(tmp_path: Path) -> None:
    """Verify CsvTableAdapter class interface."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("x,y\n1.0,2.0\n3.0,4.0\n", encoding="utf-8")

    adapter = CsvTableAdapter(csv_file)
    datasets = adapter.list_datasets()
    assert len(datasets) == 2

    series = adapter.get_series("x", "y")
    assert series.x.clean_floats() == [1.0, 3.0]
    assert series.y.clean_floats() == [2.0, 4.0]


def test_read_csv_all_columns(tmp_path: Path) -> None:
    """Verify reading all columns into dict."""
    csv_file = tmp_path / "all_cols.csv"
    csv_file.write_text("colA,colB\n10.5,20.5\n30.5,40.5\n", encoding="utf-8")

    cols = read_csv_all_columns(csv_file)
    assert cols["colA"] == [10.5, 30.5]
    assert cols["colB"] == [20.5, 40.5]


def test_live_session_adapter() -> None:
    """Verify LiveSessionAdapter reads from ReadTableResult."""
    result = ReadTableResult(
        columns=["Time", "Force"],
        rows=[{"Time": 0.0, "Force": 10.0}, {"Time": 0.5, "Force": 15.0}],
        total_rows=2,
        page=1,
        page_size=50,
        total_pages=1,
    )
    adapter = LiveSessionAdapter(result)
    metadata = adapter.list_datasets()
    assert len(metadata) == 2
    assert metadata[0].name == "Time"

    series = adapter.get_series("Time", "Force")
    assert series.x.name == "Time"
    assert series.x.clean_floats() == [0.0, 0.5]
    assert series.y.clean_floats() == [10.0, 15.0]


def test_cap_file_adapter_real_download_if_present() -> None:
    """Test reading series from a real .cap file if available."""
    dl_dir = Path(r"C:\Users\Jio\Downloads\(2026)캡스톤 실험별 파일")
    sample_cap = dl_dir / "[열역학]단열 기체 법칙(TD-8565, 850)[13].cap"
    if sample_cap.exists():
        adapter = CapArchiveAdapter(sample_cap)
        datasets = adapter.list_datasets()
        assert len(datasets) > 0
        series = adapter.get_series("부피", "압력")
        assert series.x is not None

