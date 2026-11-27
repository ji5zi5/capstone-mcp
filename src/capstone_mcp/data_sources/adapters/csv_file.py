# Copyright 2026 Capstone MCP contributors.
"""Read validated CSV data without inventing channels or shifting missing rows."""

import math
import re
import unicodedata
from decimal import Decimal
from pathlib import Path

from capstone_mcp.csv_data import (
    CsvDataError,
    CsvTimestampAxis,
    parse_csv_iso_column,
    parse_csv_number,
    read_csv_table,
)
from capstone_mcp.data_sources.models import (
    DataSeries,
    DatasetMetadata,
    ExperimentSeries,
)


def _parse_col_header(header: str) -> tuple[str, str]:
    match = re.search(r"^(.+?)\s*\((.*?)\)$", header.strip())
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return header.strip(), ""


def _normalized(name: str) -> str:
    return unicodedata.normalize("NFC", name.strip()).casefold()


def _column_index(columns: list[tuple[str, str]], query: str) -> int:
    target = _normalized(query)
    exact = [i for i, (name, _) in enumerate(columns) if _normalized(name) == target]
    partial = [i for i, (name, _) in enumerate(columns) if target in _normalized(name)]
    matches = exact or partial
    if not target or not matches:
        msg = f"CSV column {query!r} was not found."
        raise CsvDataError(msg)
    if len(matches) != 1:
        msg = f"CSV column {query!r} is ambiguous; use a unique header."
        raise CsvDataError(msg)
    return matches[0]


class CsvNumberRangeError(CsvDataError):
    """A numeric cell cannot be represented without overflow or zero underflow."""


def _decimal_to_finite_float(number: Decimal) -> float:
    result = float(number)
    if not math.isfinite(result) or (result == 0.0 and number != 0):
        msg = "CSV number is outside the nonzero finite floating-point range."
        raise CsvNumberRangeError(msg)
    return result


def _numeric_cell(value: str) -> float | None:
    number = parse_csv_number(value)
    if number is None:
        if value.strip():
            msg = "CSV number must be finite."
            raise CsvNumberRangeError(msg)
        return None
    return _decimal_to_finite_float(number)


def _column_samples(
    raw_cells: list[str],
) -> tuple[list[float | None], CsvTimestampAxis | None]:
    """Decode numeric samples or elapsed seconds from a validated ISO-8601 column."""
    ts_axis = parse_csv_iso_column(raw_cells)
    if ts_axis is not None:
        values = [
            None if elapsed is None else _decimal_to_finite_float(elapsed)
            for elapsed in ts_axis.elapsed_seconds
        ]
        return values, ts_axis
    return [_numeric_cell(cell) for cell in raw_cells], None


def read_csv_datasets(path: Path) -> list[DatasetMetadata]:
    """Inspect bounded CSV metadata without claiming text cells are numeric."""
    table = read_csv_table(path)
    return [
        DatasetMetadata(
            name=_parse_col_header(header)[0],
            units=_parse_col_header(header)[1],
            run_id=None,
            sample_count=sum(bool(row[index].strip()) for row in table.rows),
        )
        for index, header in enumerate(table.header)
    ]


def _attach_timestamp_metadata(
    metadata: dict[str, str],
    axis_role: str,
    axis: CsvTimestampAxis,
) -> None:
    prefix = "" if axis_role == "x" else "y_"
    metadata[f"{axis_role}_basis"] = "csv_iso_wall_clock_elapsed"
    metadata[f"{prefix}timestamp_origin_iso"] = axis.origin_iso
    metadata[f"{prefix}timestamp_timezone_status"] = axis.timezone_status
    metadata[f"{prefix}timestamp_observed_offsets"] = ",".join(axis.observed_offsets)


def read_csv_series(path: Path, x_name: str, y_name: str) -> ExperimentSeries:
    """Select unique columns and retain blanks in their original sample positions."""
    table = read_csv_table(path)
    columns = [_parse_col_header(header) for header in table.header]
    x_index = _column_index(columns, x_name)
    y_index = _column_index(columns, y_name)
    x_label, x_unit = columns[x_index]
    y_label, y_unit = columns[y_index]
    x_values, x_ts = _column_samples([row[x_index] for row in table.rows])
    y_values, y_ts = _column_samples([row[y_index] for row in table.rows])
    metadata: dict[str, str] = {"source": str(path), "format": "csv"}
    if x_ts is not None:
        _attach_timestamp_metadata(metadata, "x", x_ts)
        x_unit = x_unit or "s"
    if y_ts is not None:
        _attach_timestamp_metadata(metadata, "y", y_ts)
        y_unit = y_unit or "s"
    return ExperimentSeries(
        x=DataSeries(
            name=x_label,
            units=x_unit,
            values=x_values,
        ),
        y=DataSeries(
            name=y_label,
            units=y_unit,
            values=y_values,
        ),
        metadata=metadata,
    )


def read_csv_all_columns(path: Path) -> dict[str, list[float]]:
    """Read numeric and validated ISO-8601 timestamp columns with NaN blanks."""
    table = read_csv_table(path)
    series: dict[str, list[float]] = {}
    names: set[str] = set()
    for index, header in enumerate(table.header):
        raw_cells = [row[index] for row in table.rows]
        ts_axis = parse_csv_iso_column(raw_cells)
        if ts_axis is not None:
            values: list[float | None] = [
                None if elapsed is None else _decimal_to_finite_float(elapsed)
                for elapsed in ts_axis.elapsed_seconds
            ]
        else:
            values = []
            invalid = False
            for cell in raw_cells:
                try:
                    values.append(_numeric_cell(cell))
                except CsvNumberRangeError:
                    raise
                except CsvDataError:
                    invalid = True
            if not any(value is not None for value in values):
                continue
            if invalid:
                msg = f"CSV column {header!r} contains invalid samples."
                raise CsvDataError(msg)
        name = header.strip()
        if _normalized(name) in names:
            msg = f"Duplicate numeric CSV column: {name!r}."
            raise CsvDataError(msg)
        names.add(_normalized(name))
        series[name] = [math.nan if value is None else value for value in values]
    return series
