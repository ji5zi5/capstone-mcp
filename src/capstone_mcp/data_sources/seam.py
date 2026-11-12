# Copyright 2026 Capstone MCP contributors.
"""Unified experiment data source seam for file archives, tables, and sessions."""

from pathlib import Path

from capstone_mcp.data_sources.adapters.capfile import (
    read_capfile_datasets,
    read_capfile_series,
)
from capstone_mcp.data_sources.adapters.csv_file import (
    read_csv_datasets,
    read_csv_series,
)
from capstone_mcp.data_sources.models import DatasetMetadata, ExperimentSeries


def list_source_datasets(source: str | Path) -> list[DatasetMetadata]:
    """List all available datasets and their metadata from any experiment source.

    Args:
        source: Path to experiment archive (.cap) or table (.csv).

    Returns:
        List of DatasetMetadata objects.

    Raises:
        FileNotFoundError: If source path does not exist.
        ValueError: If file format is unsupported.
    """
    path = Path(source)
    if not path.exists():
        msg = f"Data source file does not exist: {path}"
        raise FileNotFoundError(msg)

    suffix = path.suffix.lower()
    if suffix == ".cap":
        return read_capfile_datasets(path)
    if suffix in [".csv", ".tsv", ".txt"]:
        return read_csv_datasets(path)

    msg = f"Unsupported data source format: {suffix} for {path}"
    raise ValueError(msg)


def get_experiment_series(
    source: str | Path,
    x_name: str,
    y_name: str,
    run_id: str | None = None,
) -> ExperimentSeries:
    """Retrieve paired X and Y series from any supported experiment source.

    Args:
        source: Path to experiment source file (.cap or .csv).
        x_name: Target independent variable column/signal name.
        y_name: Target dependent variable column/signal name.
        run_id: Optional specific Run ID filter (e.g. 'Run #1').

    Returns:
        ExperimentSeries containing paired x and y DataSeries.

    Raises:
        FileNotFoundError: If source does not exist.
        ValueError: If format is unsupported or series cannot be extracted.
    """
    path = Path(source)
    if not path.exists():
        msg = f"Data source file does not exist: {path}"
        raise FileNotFoundError(msg)

    suffix = path.suffix.lower()
    if suffix == ".cap":
        return read_capfile_series(path, x_name, y_name, run_id=run_id)
    if suffix in [".csv", ".tsv", ".txt"]:
        return read_csv_series(path, x_name, y_name)

    msg = f"Unsupported data source format '{suffix}' for {path}"
    raise ValueError(msg)
