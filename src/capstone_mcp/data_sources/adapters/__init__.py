# Copyright 2026 Capstone MCP contributors.
"""Adapters for various experiment data source formats."""

from pathlib import Path
from typing import Protocol

from capstone_mcp.data_sources.adapters.capfile import (
    read_capfile_datasets,
    read_capfile_series,
)
from capstone_mcp.data_sources.adapters.csv_file import (
    read_csv_datasets,
    read_csv_series,
)
from capstone_mcp.data_sources.adapters.live_session import (
    read_live_table_datasets,
    read_live_table_series,
)
from capstone_mcp.data_sources.models import DatasetMetadata, ExperimentSeries
from capstone_mcp.table_display import ReadTableResult


class DataSourceAdapter(Protocol):
    """Protocol for experiment data source adapters."""

    def list_datasets(self) -> list[DatasetMetadata]:
        """List metadata for all available datasets in source."""
        ...

    def get_series(
        self,
        x_name: str,
        y_name: str,
        run_id: str | None = None,
    ) -> ExperimentSeries:
        """Extract paired x and y data series."""
        ...


class CapArchiveAdapter:
    """Adapter wrapping PASCO .cap archive files."""

    def __init__(self, path: Path | str) -> None:
        """Initialize adapter with path to .cap archive."""
        self.path = Path(path)

    def list_datasets(self) -> list[DatasetMetadata]:
        """List all datasets in .cap archive."""
        return read_capfile_datasets(self.path)

    def get_series(
        self,
        x_name: str,
        y_name: str,
        run_id: str | None = None,
    ) -> ExperimentSeries:
        """Extract paired x and y series from .cap archive."""
        return read_capfile_series(self.path, x_name, y_name, run_id=run_id)


class CsvTableAdapter:
    """Adapter wrapping CSV table data files."""

    def __init__(self, path: Path | str) -> None:
        """Initialize adapter with path to CSV table."""
        self.path = Path(path)

    def list_datasets(self) -> list[DatasetMetadata]:
        """List all column datasets in CSV table."""
        return read_csv_datasets(self.path)

    def get_series(
        self,
        x_name: str,
        y_name: str,
        run_id: str | None = None,
    ) -> ExperimentSeries:
        """Extract paired x and y series from CSV table."""
        del run_id
        return read_csv_series(self.path, x_name, y_name)


class LiveSessionAdapter:
    """Adapter wrapping live Capstone desktop table displays."""

    def __init__(self, result: ReadTableResult) -> None:
        """Initialize adapter with live ReadTableResult."""
        self.result = result

    def list_datasets(self) -> list[DatasetMetadata]:
        """List all column datasets in live table display."""
        return read_live_table_datasets(self.result)

    def get_series(
        self,
        x_name: str,
        y_name: str,
        run_id: str | None = None,
    ) -> ExperimentSeries:
        """Extract paired x and y series from live table display."""
        del run_id
        return read_live_table_series(self.result, x_name, y_name)


__all__ = [
    "CapArchiveAdapter",
    "CsvTableAdapter",
    "DataSourceAdapter",
    "LiveSessionAdapter",
]
