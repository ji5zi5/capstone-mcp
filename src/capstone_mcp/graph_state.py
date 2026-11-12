# Copyright 2026 Capstone MCP contributors.
"""Typed graph state decoded from Capstone's native clipboard XML."""

# allow: SIZE_OK - The mandated fit catalog and its clipboard boundary share one file.

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Final
from xml.etree.ElementTree import Element, ParseError

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring
from pydantic import computed_field

from capstone_mcp.models import Model

if TYPE_CHECKING:
    from collections.abc import Mapping

MAX_GRAPH_XML_BYTES: Final = 8 * 1024 * 1024
MAX_GRAPH_XML_NODES: Final = 100_000
# IDA 0x14087AF80: convergence, small residual, small step, or both.
FIT_SUCCESS_STATUSES: Final = frozenset((0, 1, 2, 3))
USER_DEFINED_FIT: Final = 16
FIT_STATUS_NAMES: Final = (
    "SUCCESS_CONVERGENCE", "SUCCESS_SUM_SQUARES_SMALL", "SUCCESS_ERROR_SMALL",
    "SUCCESS_SUM_AND_ERROR_SMALL", "FAIL_ORTHO", "FAIL_MAX_ITERATONS",
    "FAIL_SUM_SQUARES_UNDERFLOW", "FAIL_ERROR_UNDERFLOW", "FAIL_ORTHO_UNDERFLOW",
    "FAIL_MEMORY", "INVALID_INPUT", "USER_CANCELED", "IN_PROGRESS",
)


class FitModel(StrEnum):
    """Settable built-in models in native fit-menu row order."""

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


class FitParameter(Model):
    """One native fit parameter with its displayed uncertainty."""

    name: str
    value: str | None
    uncertainty: str | None
    locked: bool


class FitMetric(Model):
    """One native goodness-of-fit result."""

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
        """Expose the observed native solver status without making AI guess codes."""
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
        bindings = [
            (series.renderer_id, [
                (item.index, item.source_id, item.dataset_id, item.unit_id)
                for item in sorted(series.inputs, key=lambda item: item.index)
            ])
            for series in sorted(self.series, key=lambda series: series.renderer_id)
        ]
        return hashlib.sha256(json.dumps(
            bindings, separators=(",", ":"), ensure_ascii=True,
        ).encode()).hexdigest()


class GraphStateError(ValueError):
    """Raised when graph clipboard XML is malformed, ambiguous, or incomplete."""


def _required(element: Element, attribute: str) -> str:
    value = element.attrib.get(attribute)
    if value is None:
        msg = f"<{element.tag}> is missing {attribute!r}."
        raise GraphStateError(msg)
    return value


def _integer(raw: str, *, context: str) -> int:
    try:
        return int(raw)
    except ValueError as exc:
        msg = f"Invalid integer {raw!r} in {context}."
        raise GraphStateError(msg) from exc


def _required_integer(element: Element, attribute: str) -> int:
    return _integer(_required(element, attribute), context=f"{element.tag}.{attribute}")


def _flag(raw: str, *, context: str) -> bool:
    match raw:
        case "1" | "TRUE" | "true":
            return True
        case "0" | "FALSE" | "false":
            return False
        case _:
            msg = f"Unknown status {raw!r} in {context}."
            raise GraphStateError(msg)


def _single_descendant(element: Element, tag: str) -> Element:
    matches = list(element.iter(tag))
    if len(matches) != 1:
        msg = f"Expected exactly one <{tag}> inside <{element.tag}>."
        raise GraphStateError(msg)
    return matches[0]


def _graph_input(element: Element) -> GraphInput:
    adapters = list(element.iter("DataAdapter"))
    if len(adapters) > 1:
        msg = "BundleInput contains multiple DataAdapter elements."
        raise GraphStateError(msg)
    unit_id = None
    if adapters:
        raw_unit = adapters[0].attrib.get("ConverterConverterUnit")
        if raw_unit is not None:
            unit_id = _integer(raw_unit, context="DataAdapter.ConverterConverterUnit")
    index = _required_integer(element, "BundleIndex")
    if index < 0:
        msg = "BundleInput.BundleIndex must be nonnegative."
        raise GraphStateError(msg)
    return GraphInput(
        index=index,
        source_id=_required(element, "BundleMeasID"),
        dataset_id=_required(element, "BundleDataSetID"),
        unit_id=unit_id,
    )


def _fit_parameter(
    description: Element,
    definitions: list[Element],
    *,
    error_status: int,
) -> FitParameter:
    index = _required_integer(
        description, "ZCFDICurveFitParameterDescriptionIndexToActual",
    )
    if not 0 <= index < len(definitions):
        msg = f"Fit parameter descriptor index {index} is outside its definitions."
        raise GraphStateError(msg)
    definition = definitions[index]
    value = _required(definition, "ZCFDICurveFitParameterResultValue")
    uncertainty = _required(definition, "ZCFDICurveFitParameterFitGoodness")
    return FitParameter(
        name=_required(description, "ZCFDICurveFitParameterAbbreviation"),
        value=value if error_status in FIT_SUCCESS_STATUSES else None,
        uncertainty=uncertainty if error_status in FIT_SUCCESS_STATUSES else None,
        locked=_flag(
            _required(definition, "ZCFDICurveParameterIsLocked"),
            context="ZCFDICurveFitParameterDefinition.ZCFDICurveParameterIsLocked",
        ),
    )


def _fit_metric(element: Element, *, error_status: int) -> FitMetric:
    validity = _flag(
        _required(element, "ZCFDICurveFitResultsValidity"),
        context="ZCFDICurveFitResultsDefinition.ZCFDICurveFitResultsValidity",
    )
    valid = error_status in FIT_SUCCESS_STATUSES and validity
    value = _required(element, "ZCFDICurveFitResultsValue")
    return FitMetric(
        name=_required(element, "ZCFDICurveFitResultsName"),
        abbreviation=_required(element, "ZCFDICurveFitResultsAbbreviation"),
        value=value if valid else None,
        valid=valid,
    )


def _native_fit(element: Element) -> NativeFit:
    parameter_count = _required_integer(element, "ZCFDICurveFitCountOfParameters")
    description_count = _required_integer(
        element, "ZCFDICurveFitCountOfParameterDescriptions",
    )
    result_count = _required_integer(element, "ZCFDICurveFitCountOfResults")
    if min(parameter_count, description_count, result_count) < 0:
        msg = "Native fit counts must be nonnegative."
        raise GraphStateError(msg)
    descriptions = [
        child for child in element
        if child.tag == "ZCFDICurveFitParameterDescriptionDefinition"
    ]
    definitions = [
        child for child in element
        if child.tag == "ZCFDICurveFitParameterDefinition"
    ]
    results = [
        child for child in element
        if child.tag == "ZCFDICurveFitResultsDefinition"
    ]
    if (
        len(definitions) != parameter_count
        or len(descriptions) != description_count
        or len(results) != result_count
        or description_count != parameter_count
    ):
        msg = "Native fit child counts do not match their declared counts."
        raise GraphStateError(msg)
    indices = [
        _required_integer(
            description, "ZCFDICurveFitParameterDescriptionIndexToActual",
        )
        for description in descriptions
    ]
    if sorted(indices) != list(range(parameter_count)):
        msg = "Native fit parameter descriptor indices are incomplete or duplicated."
        raise GraphStateError(msg)
    error_status = _required_integer(element, "ZCFDICurveFitCurveFitErrorStatus")
    native_type = _required_integer(element, "ZCFDICurveFitType")
    expression_attribute = (
        "ZCFDICurveFitUserExpression" if native_type == USER_DEFINED_FIT
        else "ZCFDICurveFitExpresson"
    )
    return NativeFit(
        native_type=native_type,
        name=_required(element, "ZCFDICurveFitName"),
        expression=_required(element, expression_attribute),
        error_status=error_status,
        parameters=[
            _fit_parameter(description, definitions, error_status=error_status)
            for description in descriptions
        ],
        metrics=[
            _fit_metric(result, error_status=error_status) for result in results
        ],
    )


def _graph_series(element: Element) -> GraphSeries:
    return GraphSeries(
        renderer_id=_required(element, "ZTDDRUniqueId"),
        inputs=[
            _graph_input(child) for child in element if child.tag == "BundleInput"
        ],
        fits=[_native_fit(fit) for fit in element.iter("ZRSCurveFit")],
    )


def parse_graph_xml(payload: bytes) -> GraphState:
    """Parse one native graph clipboard payload without deriving new results."""
    if len(payload) > MAX_GRAPH_XML_BYTES:
        msg = "Graph clipboard XML exceeds the safety limit."
        raise GraphStateError(msg)
    try:
        root = fromstring(payload)
    except (DefusedXmlException, ParseError, ValueError) as exc:
        msg = "Graph clipboard XML is malformed or contains forbidden constructs."
        raise GraphStateError(msg) from exc
    if sum(1 for _ in root.iter()) > MAX_GRAPH_XML_NODES:
        msg = "Graph clipboard XML contains too many elements."
        raise GraphStateError(msg)
    workbooks = list(root.iter("WorkbookItem"))
    if len(workbooks) != 1:
        msg = "Graph clipboard XML must contain exactly one WorkbookItem."
        raise GraphStateError(msg)
    workbook = workbooks[0]
    if _required(workbook, "GUID") != "CSLineGraph":
        msg = "WorkbookItem is not a CSLineGraph."
        raise GraphStateError(msg)
    graph = _single_descendant(workbook, "CSLineGraph")
    if _required_integer(graph, "LineGraphSavedCurveFitTypeNotMenuIndex") != 1:
        msg = "Graph stores legacy menu indices instead of native fit types."
        raise GraphStateError(msg)
    selections = _single_descendant(graph, "LineGraphCurveFitSelections")
    fit_enabled = _flag(
        _required(selections, "LineGraphCurveFitState"),
        context="LineGraphCurveFitSelections.LineGraphCurveFitState",
    )
    selected_types = [
        _required_integer(child, "LineGraphCurveFitType")
        for child in selections
        if child.tag == "LineGraphCurveFitChecked"
    ]
    if len(selected_types) != len(set(selected_types)):
        msg = "Graph fit selections contain duplicate native types."
        raise GraphStateError(msg)
    if any(native_type not in FIT_ROWS for native_type in selected_types):
        msg = "Graph fit selections contain an unknown native type."
        raise GraphStateError(msg)
    return GraphState(
        fit_enabled=fit_enabled,
        selected_types=selected_types,
        series=[
            _graph_series(renderer)
            for renderer in graph.iter("ZRSIndividualRenederer")
        ],
    )
