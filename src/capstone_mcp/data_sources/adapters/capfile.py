# Copyright 2026 Capstone MCP contributors.
"""Adapter for reading data series from PASCO Capstone .cap archives."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, replace
from math import isfinite
from typing import TYPE_CHECKING

from capstone_mcp.capfiles import list_cap_datasets, read_cap_file
from capstone_mcp.data_sources.models import (
    DataSeries,
    DatasetMetadata,
    ExperimentSeries,
)
from capstone_mcp.experiment_analysis import validate_paired_coordinates

if TYPE_CHECKING:
    from decimal import Decimal
    from pathlib import Path

    from capstone_mcp.capfile_models import CapDataSet, CapDatasetSummary


@dataclass(frozen=True)
class SavedRunData:
    """One saved run's channels and optional paired measurements for a report."""

    series: dict[str, DataSeries]
    channels: dict[str, str]
    run_id: str | None
    pair: tuple[DataSeries, DataSeries] | None


def read_capfile_datasets(path: Path) -> list[DatasetMetadata]:
    """Extract dataset metadata from a .cap archive."""
    metadata: list[DatasetMetadata] = []

    for d in list_cap_datasets(path):
        unit_str = str(d.unit_id) if d.unit_id is not None else ""
        fallback = f"Dataset_{d.dataset_id}" if d.dataset_id else "Unnamed"
        metadata.append(
            DatasetMetadata(
                name=d.name or d.dataset_name or fallback,
                units=unit_str,
                run_id=_run_id(d),
                sample_count=d.count,
            ),
        )
    return metadata


def _dataset_name(dataset: CapDataSet) -> str:
    fallback = f"Dataset_{dataset.data_set_id}" if dataset.data_set_id else "Unnamed"
    return dataset.source_name or dataset.name or fallback


def _run_id(dataset: CapDataSet | CapDatasetSummary) -> str | None:
    if dataset.run_name:
        return dataset.run_name
    return f"Run #{dataset.run_number}" if dataset.run_number is not None else None


def _matches_run(dataset: CapDataSet, run_id: str | None) -> bool:
    return (
        run_id is None or run_id == dataset.run_name
        or (dataset.run_number is not None and run_id == f"Run #{dataset.run_number}")
    )


def _select_series(
    datasets: list[tuple[int, CapDataSet]], name: str,
) -> tuple[int, CapDataSet]:
    target = unicodedata.normalize("NFC", name.strip()).casefold()
    matches = [
        (index, d) for index, d in datasets if target and any(
            target == unicodedata.normalize("NFC", label.strip()).casefold()
            for label in (_dataset_name(d), d.name, d.source_euid) if label
        )
    ]
    if not matches and target:
        matches = [
            (i, d) for i, d in datasets if any(
                target in unicodedata.normalize("NFC", label).casefold()
                for label in (_dataset_name(d), d.name) if label
            )
        ]
    if len(matches) != 1:
        msg = f"Dataset {name!r} must match one saved series; found {len(matches)}."
        if matches:
            msg += " The name is ambiguous; specify a run ID or measurement source."
        else:
            msg += (
                " Dataset not found." if target else " Dataset name must not be empty."
            )
        raise ValueError(msg)
    return matches[0]


def _finite_values(values: list[Decimal | None]) -> list[float | None]:
    converted: list[float | None] = []
    for value in values:
        if value is None:
            converted.append(None)
            continue
        number = float(value)
        if not isfinite(number) or (number == 0.0 and value != 0):
            msg = "Saved numeric value is outside the finite floating-point range."
            raise ValueError(msg)
        converted.append(number)
    return converted


def _dependent_series(dataset: CapDataSet) -> DataSeries:
    if dataset.numeric_values is None:
        msg = f"Dataset {_dataset_name(dataset)!r} has no saved numeric values."
        raise ValueError(msg)
    return DataSeries(
        name=_dataset_name(dataset),
        units="" if dataset.unit_id is None else str(dataset.unit_id),
        values=_finite_values(dataset.numeric_values),
    )


def _pair_measurements(
    x: tuple[int, CapDataSet], y: tuple[int, CapDataSet],
) -> tuple[DataSeries, DataSeries]:
    x_index, x_ds = x
    y_index, y_ds = y
    x_series, y_series = _dependent_series(x_ds), _dependent_series(y_ds)
    if x_index == y_index:
        msg = "Select distinct measurements for x and y."
        raise ValueError(msg)
    if (x_ds.run_number, _run_id(x_ds)) != (y_ds.run_number, _run_id(y_ds)) or (
        _run_id(y_ds) is not None and x_ds.data_set_id != y_ds.data_set_id
    ):
        msg = "Selected measurements belong to different runs."
        raise ValueError(msg)
    if (
        _run_id(y_ds) is None
        or x_ds.independent_kind == "index"
        or x_ds.independent_kind != y_ds.independent_kind
        or x_ds.independent_values == y_ds.independent_values
    ):
        if len(x_series.values) != len(y_series.values):
            msg = "Selected measurements have different sample counts."
            raise ValueError(msg)
        validate_paired_coordinates(x_ds, y_ds, x_index=x_index, y_index=y_index)
        return x_series, y_series

    x_by_coordinate = dict(zip(x_ds.independent_values, x_series.values, strict=True))
    y_by_coordinate = dict(zip(y_ds.independent_values, y_series.values, strict=True))
    if (
        None in x_by_coordinate or None in y_by_coordinate
        or len(x_by_coordinate) != len(x_series.values)
        or len(y_by_coordinate) != len(y_series.values)
    ):
        msg = "Saved coordinates must be present and unique to align two measurements."
        raise ValueError(msg)
    shared = [c for c in x_by_coordinate if c in y_by_coordinate]
    if not shared:
        msg = "Selected measurements have no shared saved coordinates."
        raise ValueError(msg)
    return (
        replace(x_series, values=[x_by_coordinate[c] for c in shared]),
        replace(y_series, values=[y_by_coordinate[c] for c in shared]),
    )


def read_capfile_series(
    path: Path, x_name: str, y_name: str, run_id: str | None = None,
) -> ExperimentSeries:
    """Read saved columns without substituting missing names or mixing runs."""
    datasets = [
        (index, d) for index, d in enumerate(read_cap_file(path).datasets)
        if _matches_run(d, run_id)
    ]
    return _saved_series(path, datasets, x_name, y_name)


def _saved_series(
    path: Path, datasets: list[tuple[int, CapDataSet]], x_name: str, y_name: str,
) -> ExperimentSeries:
    y = _select_series(datasets, y_name)
    _, y_ds = y
    x_kind = x_name.strip().casefold()
    if x_kind == "sample_index":
        indices: list[float | None] = [float(i) for i in y_ds.sample_indices]
        x_series = DataSeries(x_kind, "", indices)
        y_series = _dependent_series(y_ds)
    elif x_kind in {"independent_coordinate", "@independent"}:
        x_series = DataSeries(x_kind, "", _finite_values(y_ds.independent_values))
        y_series = _dependent_series(y_ds)
    else:
        x_series, y_series = _pair_measurements(_select_series(datasets, x_name), y)
    if len(x_series.values) != len(y_series.values):
        msg = "Selected series have different sample counts."
        raise ValueError(msg)

    return ExperimentSeries(
        x=x_series,
        y=y_series,
        run_id=_run_id(y_ds),
        metadata={"source": str(path), "format": "cap",
                  "independent_kind": y_ds.independent_kind},
    )


def read_saved_run_data(
    path: Path, *, run_id: str | None, axes: tuple[str, str] | None,
) -> SavedRunData:
    """Load one unambiguous run and keep its saved row positions."""
    archive = read_cap_file(path)
    datasets = [
        (i, d) for i, d in enumerate(archive.datasets)
        if d.numeric_values and _matches_run(d, run_id)
    ]
    runs = {(d.run_number, _run_id(d)) for _, d in datasets if _run_id(d) is not None}
    if len(runs) > 1:
        choices = ", ".join(sorted(
            f"Run #{number}" if number is not None else str(name)
            for number, name in runs
        ))
        msg = f"Archive contains multiple saved runs. Specify run_id from: {choices}."
        raise ValueError(msg)
    if run_id is not None and not runs:
        msg = f"No numeric data found for saved run {run_id!r}."
        raise ValueError(msg)

    selected = next(iter(runs), None)
    if selected is not None:
        datasets = [
            (i, d) for i, d in datasets if (d.run_number, _run_id(d)) == selected
        ]
    series = {}
    for _, dataset in datasets:
        channel = _dependent_series(dataset)
        if not any(value is not None for value in channel.values):
            continue
        if channel.name in series:
            msg = f"Duplicate saved channel {channel.name!r} in the selected data."
            raise ValueError(msg)
        series[channel.name] = channel
    paired = _saved_series(path, datasets, *axes) if axes is not None else None
    return SavedRunData(
        series=series,
        channels={
            f"Interface_{iface.euid}": (
                iface.interface_type or iface.subtype or "PASCO Interface"
            )
            for iface in archive.hardware_interfaces
        },
        run_id=None if selected is None else selected[1],
        pair=None if paired is None else (paired.x, paired.y),
    )
