# Copyright 2026 Capstone MCP contributors.
"""Data models, request schemas, and typed outcomes for Capstone graphs."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, ClassVar, Final, Literal, Self

from pydantic import ConfigDict, Field, computed_field, model_validator

from capstone_mcp.models import Bounds, Model, Point

if TYPE_CHECKING:
    from collections.abc import Mapping

# ---------------------------------------------------------------------------
# 1. Action Enumeration & General Seam Models
# ---------------------------------------------------------------------------


class GraphAction(StrEnum):
    """Supported operations on Capstone graph displays."""

    CREATE = "create"
    READ = "read"
    FIT = "fit"
    SELECT_MEASUREMENT = "select_measurement"
    TOOLBOX_DELTA = "toolbox_delta"
    TOOLBOX_AREA = "toolbox_area"
    TOOLBOX_STATISTICS = "toolbox_statistics"
    ANALYZE = "analyze"


DEFAULT_SCALE_TO_FIT_OFFSET: Final = Point(x=20, y=20)
SUPPORTED_FIT_MODES: Final = ("scale_to_fit", "manual_bounds")


# ---------------------------------------------------------------------------
# 2. Fit Models & Status Codes
# ---------------------------------------------------------------------------

FIT_SUCCESS_STATUSES: Final = frozenset((0, 1, 2, 3))
USER_DEFINED_FIT: Final = 16
FIT_STATUS_NAMES: Final = (
    "SUCCESS_CONVERGENCE",
    "SUCCESS_SUM_SQUARES_SMALL",
    "SUCCESS_ERROR_SMALL",
    "SUCCESS_SUM_AND_ERROR_SMALL",
    "FAIL_ORTHO",
    "FAIL_MAX_ITERATONS",
    "FAIL_SUM_SQUARES_UNDERFLOW",
    "FAIL_ERROR_UNDERFLOW",
    "FAIL_ORTHO_UNDERFLOW",
    "FAIL_MEMORY",
    "INVALID_INPUT",
    "USER_CANCELED",
    "IN_PROGRESS",
)


class FitModel(StrEnum):
    """Settable built-in curve fit models in native fit-menu row order."""

    PROPORTIONAL = "proportional"
    LINEAR = "linear"
    WEIGHTED_LINEAR = "weighted_linear"
    QUADRATIC = "quadratic"
    CUBIC = "cubic"
    POLYNOMIAL = "polynomial"
    POWER = "power"
    INVERSE_NO_OFFSET = "inverse_no_offset"
    INVERSE = "inverse"
    INVERSE_SQUARE_NO_OFFSET = "inverse_square_no_offset"
    INVERSE_SQUARE = "inverse_square"
    INVERSE_POWER = "inverse_power"
    NATURAL_EXPONENTIAL = "natural_exponential"
    NATURAL_LOGARITHM = "natural_logarithm"
    BASE10_EXPONENTIAL = "base10_exponential"
    BASE10_LOGARITHM = "base10_logarithm"
    INVERSE_EXPONENTIAL = "inverse_exponential"
    SINE = "sine"
    SINE_SERIES = "sine_series"
    DAMPED_SINE = "damped_sine"
    COSINE_SQUARED = "cosine_squared"
    GAUSSIAN = "gaussian"
    NORMALIZED_GAUSSIAN = "normalized_gaussian"


_NATIVE_TYPES_BY_ROW: Final[tuple[int, ...]] = (
    0, 1, 21, 2, 18, 3, 4, 23, 5, 24, 6, 7,
    8, 9, 10, 11, 12, 13, 14, 20, 22, 15, 19, 16,
)

FIT_TYPES: Final[Mapping[FitModel, int]] = MappingProxyType(
    dict(zip(FitModel, _NATIVE_TYPES_BY_ROW[:-1], strict=True)),
)
FIT_ROWS: Final[Mapping[int, int]] = MappingProxyType(
    {native_type: row for row, native_type in enumerate(_NATIVE_TYPES_BY_ROW)},
)


# ---------------------------------------------------------------------------
# 3. Native Fit & Graph State Inspection Models
# ---------------------------------------------------------------------------


class FitParameter(Model):
    """One native fit parameter with its displayed uncertainty."""

    name: str
    value: str | None
    uncertainty: str | None
    locked: bool


class FitMetric(Model):
    """One native goodness-of-fit metric."""

    name: str
    abbreviation: str
    value: str | None
    valid: bool


class NativeFit(Model):
    """One native model attached to a rendered graph series."""

    native_type: int
    name: str
    expression: str
    error_status: int
    parameters: list[FitParameter]
    metrics: list[FitMetric]

    @computed_field
    @property
    def status(self) -> str:
        """Expose observed native solver status."""
        if self.error_status < 0:
            return "USER_CANCELED"
        if self.error_status < len(FIT_STATUS_NAMES):
            return FIT_STATUS_NAMES[self.error_status]
        return "UNDEFINED"

    @computed_field
    @property
    def successful(self) -> bool:
        """Native convergence statuses 0 through 3 are successful."""
        return self.error_status in FIT_SUCCESS_STATUSES


class GraphInput(Model):
    """One direct renderer input and its native identifiers."""

    index: int
    source_id: str
    dataset_id: str
    unit_id: int | None


class GraphSeries(Model):
    """Inputs and native fits owned by one renderer."""

    renderer_id: str
    inputs: list[GraphInput]
    fits: list[NativeFit]


class GraphState(Model):
    """Fit selection state and every renderer-owned series."""

    fit_enabled: bool
    selected_types: list[int]
    series: list[GraphSeries]

    @computed_field
    @property
    def data_signature(self) -> str:
        """Fingerprint data bindings, not fit selections or unobserved sample values."""
        normalized = [
            (
                s.renderer_id,
                [
                    (inp.index, inp.source_id, inp.dataset_id, inp.unit_id)
                    for inp in sorted(s.inputs, key=lambda i: i.index)
                ],
            )
            for s in sorted(self.series, key=lambda s: s.renderer_id)
        ]
        return hashlib.sha256(
            json.dumps(normalized, sort_keys=True).encode("utf-8"),
        ).hexdigest()


# ---------------------------------------------------------------------------
# 4. Toolbox Extraction Models
# ---------------------------------------------------------------------------


class GraphStatistics(Model):
    """Extracted summary statistics from graph statistics box."""

    mean: float | None = None
    std_dev: float | None = None
    min: float | None = None
    max: float | None = None
    count: int | None = None
    raw_values: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# 5. Analysis Reporting Models & Limitation Codes
# ---------------------------------------------------------------------------


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
    """Exact native metric identity."""

    name: str
    abbreviation: str


class MetricMinimum(Model):
    """Descriptive minimum for a common native MSE or RMSE metric."""

    metric: MetricIdentity
    smallest_value: str
    tied_model_ids: list[str]


class ParameterValue(Model):
    """One native parameter value."""

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
    """One native fit result."""

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
    """Structured report of native fits and summary metrics."""

    renderers: list[RendererAnalysisGroup]
    overall_limitations: list[LimitationCode]


# ---------------------------------------------------------------------------
# 6. Execution Tracking & Failure Envelopes
# ---------------------------------------------------------------------------

GRAPH_INPUT_OPERATIONS: Final = frozenset({
    "select_graph_measurement", "set_graph_fits", "analyze_graph",
})


class GraphFrame(Model):
    """A worker-issued screenshot receipt, valid for one graph input request."""

    frame_id: str
    handle: int
    bounds: Bounds
    width: int
    height: int


class GraphCapture(Model):
    """Private worker envelope containing screenshot and frame metadata."""

    frame: GraphFrame
    png_base64: str


class GraphFailure(Model):
    """Observed progress and recovery instructions."""

    code: str
    request_id: str = ""
    operation: str
    stage: str
    completed_steps: list[str] = Field(default_factory=list)
    graph_input_may_have_been_sent: bool
    next_action: Literal[
        "observe_graph", "inspect_windows", "read_graph", "reattach_and_inspect",
    ]
    detail: str


class GraphOperationError(RuntimeError):
    """Carry a machine-readable graph failure across the worker channel."""

    def __init__(self, failure: GraphFailure) -> None:
        """Initialize GraphOperationError with machine-readable failure details."""
        self.failure = failure
        message = f"{failure.code}: {failure.detail}"
        super().__init__(message + " Call capstone_graph_recovery before retrying.")


class GraphProgress:
    """Track attempted input separately from verified outcomes."""

    def __init__(self) -> None:
        """Initialize GraphProgress tracker."""
        self.stage: str = "inspect_graph"
        self.completed_steps: list[str] = []
        self.input_attempted: bool = False

    def begin_input(self, stage: str) -> None:
        """Mark stage input as attempted."""
        self.stage = stage
        self.input_attempted = True

    def confirmed(self, stage: str) -> None:
        """Record stage as successfully confirmed."""
        self.completed_steps.append(stage)


# ---------------------------------------------------------------------------
# 7. Action-Specific Request & Result Models
# ---------------------------------------------------------------------------


class CreateGraphRequest(Model):
    """Specification for inserting a graph display onto the active page."""

    handle: int = 0
    allow_foreground: bool = True


class CreateGraphResult(Model):
    """Outcome of graph insertion."""

    detail: str
    verified: bool = True


class ReadGraphRequest(Model):
    """Specification for reading graph state via native clipboard."""

    handle: int = 0
    allow_foreground: bool = True


class ReadGraphResult(Model):
    """Outcome of reading graph state."""

    state: GraphState
    verified: bool = True


class FitGraphRequest(Model):
    """Specification of target graph and scaling mode (Scale to Fit)."""

    handle: int = 0
    mode: str = "scale_to_fit"
    graph_name: str | None = None
    offset: Point = DEFAULT_SCALE_TO_FIT_OFFSET
    allow_foreground: bool = True


class FitGraphResult(Model):
    """Outcome of graph scale-to-fit operation."""

    mode: str
    target_ref: str
    clicked_point: tuple[int, int]
    verified: bool = True
    detail: str


class SelectMeasurementRequest(Model):
    """Specification for selecting an axis measurement via popup menu."""

    handle: int = 0
    point: Point = Field(default_factory=lambda: Point(x=0, y=0))
    path: list[str] = Field(default_factory=list)
    allow_foreground: bool = True


class SelectMeasurementResult(Model):
    """Outcome of selecting an axis measurement."""

    detail: str
    verified: bool = True


class GraphFitRequest(Model):
    """Set the exact model set on the currently selected native graph."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    menu_point: Point = Field(description="Dropdown arrow in fresh screenshot.")
    frame_id: str = Field(min_length=1, description="Frame ID from observe_graph.")
    models: list[FitModel] = Field(description="Exact desired model set.")
    master_point: Point | None = Field(default=None, description="Fit icon anchor.")
    allow_foreground: bool = True
    expected_data_signature: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
        description="Signature from read_graph.",
    )

    @model_validator(mode="after")
    def unique_models(self) -> Self:
        """Validate that all requested fit models are unique."""
        if len(self.models) != len(set(self.models)):
            msg = "Choose each fitting model only once."
            raise ValueError(msg)
        return self


# Unified and backward-compatible alias
SetGraphFitsRequest = GraphFitRequest


class GraphFitOutcome(Model):
    """Native configuration confirmation and state transition."""

    changed: bool
    requested_models: list[FitModel]
    fits_successful: bool
    before: GraphState
    after: GraphState

    @computed_field
    @property
    def next_action(self) -> Literal["read_graph", "capstone_summarize_graph"]:
        """Compute recommended follow-up action based on fitting success."""
        return "capstone_summarize_graph" if self.fits_successful else "read_graph"


class AxisSelection(Model):
    """Selection path for an axis measurement."""

    point: Point
    menu_path: list[str] = Field(min_length=1)


class AnalyzeGraphRequest(Model):
    """Specification for setting axes and fits together."""

    handle: int = 0
    fitting: SetGraphFitsRequest
    x: AxisSelection | None = None
    y: AxisSelection | None = None


# Backward-compatible alias
GraphAnalysisRequest = AnalyzeGraphRequest


class AnalyzeGraphResult(Model):
    """Outcome of analyzing graph with fits and axes."""

    outcome: GraphFitOutcome
    report: GraphAnalysisReport | None = None


class GraphDeltaRequest(Model):
    """Specification for activating delta tool and reading coordinate differences."""

    handle: int = 0
    graph_name: str | None = None
    point: Point | None = None
    point1: Point | None = None
    point2: Point | None = None
    allow_foreground: bool = True


class GraphDeltaResult(Model):
    """Outcome of delta crosshair measurement."""

    visible: bool = True
    active: bool = True
    dx: float | None = None
    dy: float | None = None
    delta_x: float | None = None
    delta_y: float | None = None
    x1: float | None = None
    y1: float | None = None
    x2: float | None = None
    y2: float | None = None
    unit_x: str | None = None
    unit_y: str | None = None
    points: list[Point] = Field(default_factory=list)
    raw_text: str | None = ""
    graph_name: str | None = None
    verified: bool = True
    detail: str = ""


class MeasureGraphAreaRequest(Model):
    """Specification for area under curve (integral) measurement."""

    handle: int = 0
    graph_name: str | None = None
    enable: bool | None = None
    point: Point | None = None
    allow_foreground: bool = True


class MeasureGraphAreaResult(Model):
    """Outcome of curve area integration."""

    visible: bool = True
    area: float | None = None
    unit: str | None = None
    raw_text: str | None = ""
    graph_name: str | None = None
    verified: bool = True
    detail: str = ""


class ToggleGraphStatisticsRequest(Model):
    """Specification for toggling statistics box and extracting values."""

    handle: int = 0
    graph_name: str | None = None
    enable: bool | None = None
    allow_foreground: bool = True


class ToggleGraphStatisticsResult(Model):
    """Outcome of toggling graph statistics."""

    visible: bool = True
    statistics: GraphStatistics | None = None
    graph_name: str | None = None
    verified: bool = True
    detail: str = ""


# ---------------------------------------------------------------------------
# 8. Unified Seam Request & Result Models
# ---------------------------------------------------------------------------


class GraphRequest(Model):
    """Unified request for all Capstone graph operations."""

    action: GraphAction
    create: CreateGraphRequest | None = None
    read: ReadGraphRequest | None = None
    fit: FitGraphRequest | None = None
    select_measurement: SelectMeasurementRequest | None = None
    toolbox_delta: GraphDeltaRequest | None = None
    toolbox_area: MeasureGraphAreaRequest | None = None
    toolbox_statistics: ToggleGraphStatisticsRequest | None = None
    analyze: AnalyzeGraphRequest | None = None


class GraphResult(Model):
    """Unified result containing the outcome of the requested graph action."""

    action: GraphAction
    create: CreateGraphResult | None = None
    read: ReadGraphResult | None = None
    fit: FitGraphResult | None = None
    select_measurement: SelectMeasurementResult | None = None
    toolbox_delta: GraphDeltaResult | None = None
    toolbox_area: MeasureGraphAreaResult | None = None
    toolbox_statistics: ToggleGraphStatisticsResult | None = None
    analyze: AnalyzeGraphResult | None = None
