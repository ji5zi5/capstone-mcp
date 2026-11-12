# Copyright 2026 Capstone MCP contributors.
"""Numerical analysis selected directly from saved Capstone experiments."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from capstone_mcp.analysis import (
    AnalysisError,
    FitInput,
    LinearFit,
    RunComparison,
    RunSamples,
    compare_runs,
    linear_fit,
)
from capstone_mcp.capfile_models import CapDataSet, CapValueKind
from capstone_mcp.capfiles import read_cap_file
from capstone_mcp.models import Model


class ExperimentAnalysisError(AnalysisError):
    """A saved experiment cannot support the requested analysis."""


class CapDatasetSelection(Model):
    """Select one dataset by zero-based index or exact saved dataset ID."""

    index: Annotated[int | None, Field(ge=0)] = None
    dataset_id: Annotated[str | None, Field(min_length=1)] = None

    @model_validator(mode="after")
    def require_exactly_one_selector(self) -> Self:
        """Reject missing or competing dataset selectors."""
        if (self.index is None) == (self.dataset_id is None):
            msg = "Provide exactly one of index or dataset_id."
            raise ValueError(msg)
        return self


class CapLinearFitRequest(Model):
    """Two distinct saved series sampled at identical coordinates."""

    x: CapDatasetSelection
    y: CapDatasetSelection


class CapRunComparisonRequest(Model):
    """Explicit saved datasets to compare in their shared declared unit."""

    datasets: Annotated[
        list[CapDatasetSelection],
        Field(min_length=2, max_length=1_000),
    ]


class CapDatasetProvenance(Model):
    """Exact saved-file, source, dataset, unit, and sampling identity."""

    file_path: str
    file_name: str
    dataset_index: int
    dataset_id: str | None
    dataset_name: str | None
    run_name: str | None = None
    run_number: int | None = None
    source_euid: str | None
    source_name: str | None
    unit_id: int | None
    value_kind: CapValueKind
    sample_count: int
    independent_kind: Literal["index", "interval", "stored"]


class CapLinearFitResult(Model):
    """A fitted pair and the exact provenance of both selected series."""

    x: CapDatasetProvenance
    y: CapDatasetProvenance
    fit: LinearFit


class CapRunComparisonResult(Model):
    """Run summaries aligned with the provenance of explicit selections."""

    datasets: list[CapDatasetProvenance]
    comparison: list[RunComparison]


def _select_dataset(
    datasets: list[CapDataSet],
    selection: CapDatasetSelection,
) -> tuple[int, CapDataSet]:
    if selection.index is not None:
        if selection.index >= len(datasets):
            msg = (
                f"Dataset index {selection.index} is outside the available "
                f"range 0..{len(datasets) - 1}."
            )
            raise ExperimentAnalysisError(msg)
        return selection.index, datasets[selection.index]

    dataset_id = selection.dataset_id
    matches = [
        (index, dataset)
        for index, dataset in enumerate(datasets)
        if dataset.data_set_id == dataset_id
    ]
    if not matches:
        msg = f"No dataset has the exact ID {dataset_id!r}."
        raise ExperimentAnalysisError(msg)
    if len(matches) > 1:
        msg = f"Dataset ID {dataset_id!r} is ambiguous in this file."
        raise ExperimentAnalysisError(msg)
    return matches[0]


def _provenance(
    *,
    file_path: Path,
    file_name: str,
    index: int,
    dataset: CapDataSet,
) -> CapDatasetProvenance:
    return CapDatasetProvenance(
        file_path=str(file_path),
        file_name=file_name,
        dataset_index=index,
        dataset_id=dataset.data_set_id,
        dataset_name=dataset.name,
        run_name=dataset.run_name,
        run_number=dataset.run_number,
        source_euid=dataset.source_euid,
        source_name=dataset.source_name,
        unit_id=dataset.unit_id,
        value_kind=dataset.value_kind,
        sample_count=len(dataset.sample_indices),
        independent_kind=dataset.independent_kind,
    )


def _finite_numeric_values(dataset: CapDataSet, *, index: int) -> list[float]:
    if (
        dataset.value_kind is not CapValueKind.NUMERIC
        or dataset.numeric_values is None
    ):
        msg = f"Dataset index {index} does not provide declared numeric samples."
        raise ExperimentAnalysisError(msg)
    values: list[float] = []
    for sample_index, value in enumerate(dataset.numeric_values):
        if value is None or not value.is_finite():
            msg = (
                f"Dataset index {index} has a missing or non-finite numeric "
                f"sample at position {sample_index}."
            )
            raise ExperimentAnalysisError(msg)
        converted = float(value)
        if not math.isfinite(converted):
            msg = (
                f"Dataset index {index} sample {sample_index} exceeds finite "
                "floating-point precision."
            )
            raise ExperimentAnalysisError(msg)
        values.append(converted)
    return values


def _validate_paired_coordinates(
    x_dataset: CapDataSet,
    y_dataset: CapDataSet,
    *,
    x_index: int,
    y_index: int,
) -> None:
    if len(x_dataset.independent_values) != len(y_dataset.independent_values):
        msg = "Selected fit datasets have different independent-coordinate lengths."
        raise ExperimentAnalysisError(msg)
    if x_dataset.independent_kind != y_dataset.independent_kind:
        msg = "Selected fit datasets use different independent-coordinate kinds."
        raise ExperimentAnalysisError(msg)
    for sample_index, (x_coordinate, y_coordinate) in enumerate(
        zip(
            x_dataset.independent_values,
            y_dataset.independent_values,
            strict=True,
        ),
    ):
        if (
            x_coordinate is None
            or y_coordinate is None
            or not x_coordinate.is_finite()
            or not y_coordinate.is_finite()
        ):
            msg = (
                "Selected fit datasets have a missing or non-finite independent "
                f"coordinate at position {sample_index}."
            )
            raise ExperimentAnalysisError(msg)
        if x_coordinate != y_coordinate:
            msg = (
                f"Selected fit datasets {x_index} and {y_index} have different "
                f"independent coordinates at position {sample_index}."
            )
            raise ExperimentAnalysisError(msg)


def fit_cap_datasets(
    path: str | Path,
    request: CapLinearFitRequest,
) -> CapLinearFitResult:
    """Fit two explicit saved datasets without copying their arrays."""
    file_path = Path(path).resolve()
    parsed = read_cap_file(file_path)
    x_index, x_dataset = _select_dataset(parsed.datasets, request.x)
    y_index, y_dataset = _select_dataset(parsed.datasets, request.y)
    if x_index == y_index:
        msg = "Select two distinct datasets for a paired fit."
        raise ExperimentAnalysisError(msg)
    x_values = _finite_numeric_values(x_dataset, index=x_index)
    y_values = _finite_numeric_values(y_dataset, index=y_index)
    if len(x_values) != len(y_values):
        msg = "Selected fit datasets contain different numbers of samples."
        raise ExperimentAnalysisError(msg)
    _validate_paired_coordinates(
        x_dataset,
        y_dataset,
        x_index=x_index,
        y_index=y_index,
    )
    fit = linear_fit(FitInput(x=x_values, y=y_values))
    return CapLinearFitResult(
        x=_provenance(
            file_path=file_path,
            file_name=parsed.file_name,
            index=x_index,
            dataset=x_dataset,
        ),
        y=_provenance(
            file_path=file_path,
            file_name=parsed.file_name,
            index=y_index,
            dataset=y_dataset,
        ),
        fit=fit,
    )


def compare_cap_datasets(
    path: str | Path,
    request: CapRunComparisonRequest,
) -> CapRunComparisonResult:
    """Compare explicit saved datasets only when declared units match."""
    file_path = Path(path).resolve()
    parsed = read_cap_file(file_path)
    selected = [
        _select_dataset(parsed.datasets, selection)
        for selection in request.datasets
    ]
    indices = [index for index, _dataset in selected]
    if len(set(indices)) != len(indices):
        msg = "Select distinct datasets for run comparison."
        raise ExperimentAnalysisError(msg)
    unit_ids = [dataset.unit_id for _index, dataset in selected]
    if any(unit_id is None for unit_id in unit_ids):
        msg = "Every compared dataset must declare a unit ID."
        raise ExperimentAnalysisError(msg)
    if len(set(unit_ids)) != 1:
        msg = "Compared datasets must have matching declared unit IDs."
        raise ExperimentAnalysisError(msg)

    provenances = [
        _provenance(
            file_path=file_path,
            file_name=parsed.file_name,
            index=index,
            dataset=dataset,
        )
        for index, dataset in selected
    ]
    runs = [
        RunSamples(
            name=f"dataset[{index}]",
            values=_finite_numeric_values(dataset, index=index),
        )
        for index, dataset in selected
    ]
    return CapRunComparisonResult(
        datasets=provenances,
        comparison=compare_runs(runs),
    )
