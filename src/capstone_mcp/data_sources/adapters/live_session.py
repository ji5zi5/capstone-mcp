# Copyright 2026 Capstone MCP contributors.
"""Adapter for reading data series from live Capstone UI table displays."""

from capstone_mcp.data_sources.models import (
    DataSeries,
    DatasetMetadata,
    ExperimentSeries,
)
from capstone_mcp.displays import ReadTableResult


def read_live_table_datasets(result: ReadTableResult) -> list[DatasetMetadata]:
    """Extract dataset metadata from a live table inspection result."""
    return [
        DatasetMetadata(
            name=col,
            units="",
            run_id=None,
            sample_count=len(result.rows),
        )
        for col in result.columns
    ]


def read_live_table_series(
    result: ReadTableResult, x_name: str, y_name: str,
) -> ExperimentSeries:
    """Extract paired x and y DataSeries from a live ReadTableResult."""
    # Find matching column names
    x_col = next(
        (c for c in result.columns if x_name.lower() in c.lower()), None,
    )
    y_col = next(
        (c for c in result.columns if y_name.lower() in c.lower()), None,
    )

    if not x_col and result.columns:
        x_col = result.columns[0]
    if not y_col and len(result.columns) > 1:
        y_col = result.columns[1]
    elif not y_col:
        y_col = x_col

    if not x_col or not y_col:
        msg = (
            f"Cannot find columns matching '{x_name}' and '{y_name}' "
            f"in table columns: {result.columns}"
        )
        raise ValueError(msg)

    x_vals: list[float | None] = []
    y_vals: list[float | None] = []

    for row in result.rows:
        xv = row.get(x_col)
        yv = row.get(y_col)
        x_vals.append(float(xv) if isinstance(xv, (int, float)) else None)
        y_vals.append(float(yv) if isinstance(yv, (int, float)) else None)

    return ExperimentSeries(
        x=DataSeries(name=x_col, units="", values=x_vals),
        y=DataSeries(name=y_col, units="", values=y_vals),
        run_id=None,
        metadata={"source": "live_session", "format": "table_display"},
    )
