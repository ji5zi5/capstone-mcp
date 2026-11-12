# Copyright 2026 Capstone MCP contributors.
"""Adapter for reading data series from CSV table files."""

import contextlib
import csv
import re
from pathlib import Path

from capstone_mcp.data_sources.models import (
    DataSeries,
    DatasetMetadata,
    ExperimentSeries,
)


def _parse_col_header(header: str) -> tuple[str, str]:
    """Parse column header into name and optional unit (e.g. 'Time (s)')."""
    match = re.search(r"^(.+?)\s*\((.*?)\)$", header.strip())
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return header.strip(), ""


def read_csv_datasets(path: Path) -> list[DatasetMetadata]:
    """Inspect CSV file and return dataset metadata for each column."""
    with path.open("r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header:
            return []
        rows = list(reader)

    metadata: list[DatasetMetadata] = []
    for col_idx, col_name in enumerate(header):
        name, unit = _parse_col_header(col_name)
        count = sum(
            1 for r in rows if col_idx < len(r) and r[col_idx].strip()
        )
        metadata.append(
            DatasetMetadata(
                name=name,
                units=unit,
                run_id=None,
                sample_count=count,
            ),
        )
    return metadata


def read_csv_series(
    path: Path, x_name: str, y_name: str,
) -> ExperimentSeries:
    """Read paired x and y series from a CSV table."""
    with path.open("r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header:
            msg = f"Empty CSV file: {path}"
            raise ValueError(msg)
        rows = list(reader)

    parsed_cols = [_parse_col_header(h) for h in header]

    x_idx: int | None = None
    y_idx: int | None = None

    for i, (name, _) in enumerate(parsed_cols):
        if x_name.lower() in name.lower() and x_idx is None:
            x_idx = i
        if y_name.lower() in name.lower() and y_idx is None:
            y_idx = i

    if x_idx is None:
        x_idx = 0
    if y_idx is None:
        y_idx = 1 if len(parsed_cols) > 1 else 0

    x_col_name, x_unit = parsed_cols[x_idx]
    y_col_name, y_unit = parsed_cols[y_idx]

    x_vals: list[float | None] = []
    y_vals: list[float | None] = []

    for r in rows:
        xv = float(r[x_idx]) if x_idx < len(r) and r[x_idx].strip() else None
        yv = float(r[y_idx]) if y_idx < len(r) and r[y_idx].strip() else None
        x_vals.append(xv)
        y_vals.append(yv)

    return ExperimentSeries(
        x=DataSeries(name=x_col_name, units=x_unit, values=x_vals),
        y=DataSeries(name=y_col_name, units=y_unit, values=y_vals),
        metadata={"source": str(path), "format": "csv"},
    )


def read_csv_all_columns(path: Path) -> dict[str, list[float]]:
    """Read all numeric columns from a CSV table."""
    series: dict[str, list[float]] = {}
    with path.open("r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        headers = next(reader, None)
        if headers:
            cols: list[list[float]] = [[] for _ in headers]
            for row in reader:
                for i, val in enumerate(row):
                    if i < len(cols):
                        with contextlib.suppress(ValueError):
                            cols[i].append(float(val.strip()))
            for h, col_data in zip(headers, cols, strict=False):
                if col_data:
                    series[h.strip()] = col_data
    return series

