# Copyright 2026 Capstone MCP contributors.
"""Pure, provenance-preserving summaries of native graph fit results."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import TYPE_CHECKING, Final, override

from capstone_mcp.graph_state import FIT_TYPES, FitModel
from capstone_mcp.models import Model

if TYPE_CHECKING:
    from capstone_mcp.graph_state import GraphSeries, GraphState, NativeFit

MIN_MODELS_FOR_COMPARISON: Final = 2


class LimitationCode(StrEnum):
    """Machine-readable reasons that restrict native fit interpretation."""

    SAMPLE_COUNT_UNAVAILABLE = "SAMPLE_COUNT_UNAVAILABLE"
    RESIDUALS_UNAVAILABLE = "RESIDUALS_UNAVAILABLE"
    NO_AUTOMATIC_MODEL_SELECTION = "NO_AUTOMATIC_MODEL_SELECTION"
    DIFFERENT_BINDINGS_NOT_COMPARED = "DIFFERENT_BINDINGS_NOT_COMPARED"
    NATIVE_FIT_FAILURE = "NATIVE_FIT_FAILURE"
    INVALID_NATIVE_METRIC = "INVALID_NATIVE_METRIC"
    NONFINITE_NATIVE_METRIC = "NONFINITE_NATIVE_METRIC"
    AMBIGUOUS_NATIVE_METRIC = "AMBIGUOUS_NATIVE_METRIC"
    EMPTY_GRAPH = "EMPTY_GRAPH"
    NO_NATIVE_FITS = "NO_NATIVE_FITS"


class NativeMetricValue(Model):
    """One valid, finite native metric with its original displayed value."""

    name: str
    abbreviation: str
    value: str


class MetricIdentity(Model):
    """Exact native metric identity; names and abbreviations are not aliases."""

    name: str
    abbreviation: str


class MetricMinimum(Model):
    """Descriptive minimum for a common native MSE or RMSE metric."""

    metric: MetricIdentity
    smallest_value: str
    tied_model_ids: list[str]


class ParameterValue(Model):
    """One native parameter, including whether it was excluded from fitting."""

    name: str
    value: str | None
    uncertainty: str | None
    locked: bool


class GraphInputProvenance(Model):
    """One renderer input in native bundle-index order."""

    source_id: str
    dataset_id: str
    unit_id: int | None
    index: int


class ModelAnalysisRow(Model):
    """One native fit result without derived or invented statistics."""

    model_id: str
    native_type: int
    request_model: FitModel | None
    name: str
    status: str
    successful: bool
    parameter_count: int
    free_parameter_count: int
    metrics: list[NativeMetricValue]
    parameters: list[ParameterValue]
    limitations: list[LimitationCode]


class RendererAnalysisGroup(Model):
    """Fits sharing one renderer and its exact ordered input provenance."""

    renderer_id: str
    provenance: list[GraphInputProvenance]
    rows: list[ModelAnalysisRow]
    common_metrics: list[MetricIdentity]
    descriptive_minima: list[MetricMinimum]
    limitations: list[LimitationCode]


class GraphAnalysisReport(Model):
    """Native graph fit summary that never selects an overall best model."""

    fit_enabled: bool
    data_signature: str
    selected_types: list[int]
    groups: list[RendererAnalysisGroup]
    limitations: list[LimitationCode]


@dataclass(frozen=True, slots=True)
class DuplicateNativeModelError(ValueError):
    """A renderer contains multiple entries for one native model type."""

    renderer_id: str
    native_type: int

    @override
    def __str__(self) -> str:
        """Describe the ambiguous renderer and native model type."""
        return f"duplicate native type {self.native_type} in {self.renderer_id!r}"


type MetricKey = tuple[str, str]
type ParsedMetric = tuple[Decimal, str]


@dataclass(frozen=True, slots=True)
class _PreparedRow:
    row: ModelAnalysisRow
    parsed_metrics: dict[MetricKey, list[ParsedMetric]]


def _unique_codes(codes: list[LimitationCode]) -> list[LimitationCode]:
    return list(dict.fromkeys(codes))


def _prepare_row(fit: NativeFit, model_id: str) -> _PreparedRow:
    metrics: list[NativeMetricValue] = []
    parsed: dict[MetricKey, list[ParsedMetric]] = {}
    limitations: list[LimitationCode] = []
    for metric in fit.metrics:
        value = metric.value
        if not metric.valid or value is None:
            limitations.append(LimitationCode.INVALID_NATIVE_METRIC)
            continue
        try:
            number = Decimal(value)
        except InvalidOperation:
            limitations.append(LimitationCode.INVALID_NATIVE_METRIC)
            continue
        if not number.is_finite():
            limitations.append(LimitationCode.NONFINITE_NATIVE_METRIC)
            continue
        metrics.append(NativeMetricValue(
            name=metric.name,
            abbreviation=metric.abbreviation,
            value=value,
        ))
        parsed.setdefault(
            (metric.name, metric.abbreviation),
            [],
        ).append((number, value))
    if not fit.successful:
        limitations.append(LimitationCode.NATIVE_FIT_FAILURE)
    return _PreparedRow(
        row=ModelAnalysisRow(
            model_id=model_id,
            native_type=fit.native_type,
            request_model=next((
                model for model, native_type in FIT_TYPES.items()
                if native_type == fit.native_type
            ), None),
            name=fit.name,
            status=fit.status,
            successful=fit.successful,
            parameter_count=len(fit.parameters),
            free_parameter_count=sum(
                not parameter.locked for parameter in fit.parameters
            ),
            metrics=metrics,
            parameters=[
                ParameterValue(
                    name=parameter.name,
                    value=parameter.value,
                    uncertainty=parameter.uncertainty,
                    locked=parameter.locked,
                )
                for parameter in fit.parameters
            ],
            limitations=_unique_codes(limitations),
        ),
        parsed_metrics=parsed,
    )


def _build_group(series: GraphSeries) -> RendererAnalysisGroup:
    native_types: set[int] = set()
    for fit in series.fits:
        if fit.native_type in native_types:
            raise DuplicateNativeModelError(
                renderer_id=series.renderer_id,
                native_type=fit.native_type,
            )
        native_types.add(fit.native_type)
    prepared = [
        _prepare_row(fit, f"{series.renderer_id}:{fit.native_type}")
        for fit in sorted(series.fits, key=lambda item: (item.native_type, item.name))
    ]
    successful = [item for item in prepared if item.row.successful]
    common_keys: set[MetricKey] = set()
    if len(successful) >= MIN_MODELS_FOR_COMPARISON:
        common_keys = set(successful[0].parsed_metrics)
        for item in successful[1:]:
            common_keys &= item.parsed_metrics.keys()
    common = [
        MetricIdentity(name=name, abbreviation=abbreviation)
        for name, abbreviation in sorted(common_keys)
    ]
    minima: list[MetricMinimum] = []
    limitations = [code for item in prepared for code in item.row.limitations]
    if series.fits:
        limitations.extend((
            LimitationCode.SAMPLE_COUNT_UNAVAILABLE,
            LimitationCode.RESIDUALS_UNAVAILABLE,
        ))
    else:
        limitations.append(LimitationCode.NO_NATIVE_FITS)
    if len(successful) >= MIN_MODELS_FOR_COMPARISON:
        limitations.append(LimitationCode.NO_AUTOMATIC_MODEL_SELECTION)
    for metric in common:
        key = (metric.name, metric.abbreviation)
        if metric.abbreviation.upper() not in {"MSE", "RMSE"}:
            continue
        values = [item.parsed_metrics[key] for item in successful]
        if any(len(value) != 1 for value in values):
            limitations.append(LimitationCode.AMBIGUOUS_NATIVE_METRIC)
            continue
        minimum = min(value[0][0] for value in values)
        ties = [
            item.row.model_id
            for item, value in zip(successful, values, strict=True)
            if value[0][0] == minimum
        ]
        displayed = next(value[0][1] for value in values if value[0][0] == minimum)
        minima.append(MetricMinimum(
            metric=metric,
            smallest_value=displayed,
            tied_model_ids=ties,
        ))
    return RendererAnalysisGroup(
        renderer_id=series.renderer_id,
        provenance=[
            GraphInputProvenance(
                source_id=item.source_id,
                dataset_id=item.dataset_id,
                unit_id=item.unit_id,
                index=item.index,
            )
            for item in sorted(series.inputs, key=lambda item: item.index)
        ],
        rows=[item.row for item in prepared],
        common_metrics=common,
        descriptive_minima=minima,
        limitations=_unique_codes(limitations),
    )


def summarize_graph(state: GraphState) -> GraphAnalysisReport:
    """Summarize native fits within renderer boundaries only."""
    groups = [
        _build_group(series)
        for series in sorted(state.series, key=lambda item: item.renderer_id)
    ]
    limitations = [code for group in groups for code in group.limitations]
    if not state.series:
        limitations.append(LimitationCode.EMPTY_GRAPH)
    if not any(group.rows for group in groups):
        limitations.append(LimitationCode.NO_NATIVE_FITS)
    bindings = {
        tuple(
            (item.source_id, item.dataset_id, item.unit_id, item.index)
            for item in group.provenance
        )
        for group in groups
    }
    if len(bindings) > 1:
        limitations.append(LimitationCode.DIFFERENT_BINDINGS_NOT_COMPARED)
    return GraphAnalysisReport(
        fit_enabled=state.fit_enabled,
        data_signature=state.data_signature,
        selected_types=state.selected_types,
        groups=groups,
        limitations=_unique_codes(limitations),
    )
