# Copyright 2026 Capstone MCP contributors.
"""Graph state inspection, native XML decoding, and analytical reporting."""

from __future__ import annotations

import logging
from _ctypes import COMError
from contextlib import suppress
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Final, override
from xml.etree.ElementTree import Element, ParseError

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.graphs.models import (
    FIT_ROWS,
    FIT_SUCCESS_STATUSES,
    FIT_TYPES,
    USER_DEFINED_FIT,
    FitMetric,
    FitParameter,
    GraphAnalysisReport,
    GraphInput,
    GraphInputProvenance,
    GraphSeries,
    GraphState,
    LimitationCode,
    MetricIdentity,
    MetricMinimum,
    ModelAnalysisRow,
    NativeFit,
    NativeMetricValue,
    ParameterValue,
    RendererAnalysisGroup,
)

if TYPE_CHECKING:
    from capstone_mcp.models import Snapshot

try:
    import win32clipboard
    import win32gui
    import win32process

    from capstone_mcp.ui_events import WindowEvents
except ImportError:
    win32clipboard = None  # type: ignore[assignment]
    win32gui = None  # type: ignore[assignment]
    win32process = None  # type: ignore[assignment]
    WindowEvents = None  # type: ignore[assignment, misc]

logger = logging.getLogger(__name__)

MAX_GRAPH_XML_BYTES: Final = 8 * 1024 * 1024
MAX_GRAPH_XML_NODES: Final = 100_000
FIT_ERROR_STATUS_FAILED: Final = 10
TRANSITION_SECONDS: Final = 15
GRAPH_MIME: Final = "ItemCutCopyPasteMimeType"
MENU_RELEASE_ATTEMPTS: Final = 3
MIN_MODELS_FOR_COMPARISON: Final = 2


class GraphStateError(ValueError):
    """Raised when native graph clipboard XML violates invariant structure."""


# ---------------------------------------------------------------------------
# 1. XML Decoding Helpers
# ---------------------------------------------------------------------------


def _required(element: Element, attribute: str) -> str:
    value = element.get(attribute)
    if value is None:
        msg = f"Graph clipboard XML element is missing attribute {attribute!r}."
        raise GraphStateError(msg)
    return value


def _required_integer(element: Element, attribute: str) -> int:
    raw = _required(element, attribute)
    return _integer(raw, context=attribute)


def _integer(raw: str, *, context: str) -> int:
    try:
        return int(raw)
    except ValueError as exc:
        msg = f"Graph clipboard XML field {context!r} is not an integer: {raw!r}."
        raise GraphStateError(msg) from exc


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
        msg = f"Graph clipboard XML must contain exactly one {tag} descendant."
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
        child
        for child in element
        if child.tag == "ZCFDICurveFitParameterDescriptionDefinition"
    ]
    definitions = [
        child
        for child in element
        if child.tag == "ZCFDICurveFitParameterDefinition"
    ]
    results = [
        child
        for child in element
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
        "ZCFDICurveFitUserExpression"
        if native_type == USER_DEFINED_FIT
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


# ---------------------------------------------------------------------------
# 2. Native Clipboard Read & Menu Release
# ---------------------------------------------------------------------------


def release_menu_bar(app: Capstone, handle: int) -> None:
    """Leave menu mode entirely before or after a menu workflow."""
    for _ in range(MENU_RELEASE_ATTEMPTS):
        snapshot = app.snapshot(handle, 3, 400)
        armed = any(
            c.control_type == "MenuItem" and app.refs[c.ref].has_keyboard_focus()
            for c in snapshot.controls
        )
        if not armed and {w.handle for w in app.windows()} == {handle}:
            return
        _ = app.keys(handle, "{ESC}")
    msg = "Capstone stayed in menu mode after Escape; inspect the window."
    raise AutomationError(msg)


def _copied_graph(sequence: int, process_id: int) -> GraphState | None:
    if win32clipboard is None or win32process is None:
        return None
    if win32clipboard.GetClipboardSequenceNumber() == sequence:
        return None
    owner = win32clipboard.GetClipboardOwner()
    if not owner or win32process.GetWindowThreadProcessId(owner)[1] != process_id:
        msg = "Another application changed the clipboard during graph inspection."
        raise AutomationError(msg)
    format_id = win32clipboard.RegisterClipboardFormat(GRAPH_MIME)
    if not win32clipboard.IsClipboardFormatAvailable(format_id):
        msg = "Copy Display did not provide native graph data."
        raise AutomationError(msg)
    win32clipboard.OpenClipboard()
    try:
        payload = win32clipboard.GetClipboardData(format_id)
    finally:
        win32clipboard.CloseClipboard()
    if not isinstance(payload, bytes) or len(payload) > MAX_GRAPH_XML_BYTES:
        msg = "Native graph clipboard payload is invalid or exceeds 8 MiB."
        raise AutomationError(msg)
    return parse_graph_xml(payload.rstrip(b"\0"))


def read_graph(
    app: Capstone,
    handle: int,
    *,
    allow_foreground: bool = True,
) -> GraphState:
    """Read selected graph state via native Copy Display; replaces the clipboard."""
    if not allow_foreground:
        msg = "Graph inspection uses the native Copy Display menu."
        raise AutomationError(msg)
    windows = app.windows()
    if len(windows) != 1 or windows[0].handle != handle:
        msg = "Select one graph and close existing menus before graph inspection."
        raise AutomationError(msg)
    pid = windows[0].process_id
    if (
        WindowEvents is None
        or win32clipboard is None
        or win32gui is None
        or win32process is None
    ):
        msg = "Native clipboard events require Windows pywin32 environment."
        raise AutomationError(msg)
    with WindowEvents(pid, clipboard=True) as events:
        _ = app.focus_window(handle)
        release_menu_bar(app, handle)
        snapshot = app.snapshot(handle, 3, 400)
        menus = [
            c
            for c in snapshot.controls
            if c.control_type == "MenuItem"
            and c.name == "Display"
            and c.visible
            and c.enabled
        ]
        if len(menus) != 1:
            msg = "Expected one enabled Display menu."
            raise AutomationError(msg)
        _ = app.control(menus[0].ref).expand()
        try:
            popup = events.changes.until(
                lambda: _display_popup(app, handle),
                TRANSITION_SECONDS,
                description="Display menu popup window",
            )
        except AutomationError:
            close_menus(app, handle)
            raise
        copies = [
            c
            for c in popup.controls
            if c.name == "Copy Display"
            and c.control_type == "MenuItem"
            and c.enabled
            and c.visible
        ]
        if len(copies) != 1:
            msg = "Select exactly one graph before inspecting its analysis."
            raise AutomationError(msg)
        sequence = win32clipboard.GetClipboardSequenceNumber()
        _ = app.control(copies[0].ref).invoke()
        app.refs.clear()
        state = events.changes.until(
            lambda: _copied_graph(sequence, pid),
            TRANSITION_SECONDS,
            description="New native graph clipboard data",
        )
        if any(w.handle == popup.window.handle for w in app.windows()):
            _ = app.keys(handle, "{ESC}")
        _ = events.changes.until(
            lambda: True if {w.handle for w in app.windows()} == {handle} else None,
            TRANSITION_SECONDS,
            description="Copy Display menu dismissal",
        )
        release_menu_bar(app, handle)
        return state


def _display_popup(app: Capstone, main_handle: int) -> Snapshot | None:
    for window in app.windows():
        if window.handle == main_handle:
            continue
        try:
            snapshot = app.snapshot(window.handle, 3, 100)
        except Exception as e:  # noqa: BLE001
            logger.debug(
                "Failed to snapshot window handle %s: %s", window.handle, e,
            )
            continue
        if any(
            c.name == "Copy Display"
            and c.control_type == "MenuItem"
            and c.visible
            and c.enabled
            for c in snapshot.controls
        ):
            return snapshot
    return None


def close_menus(app: Capstone, handle: int) -> None:
    """Dismiss a menu this workflow opened so its failure does not block the next."""
    with suppress(Exception):
        release_menu_bar(app, handle)


def menu_item_disabled(app: Capstone, before: set[int], name: str) -> bool:
    """Report whether an open menu shows the named item but keeps it disabled."""
    for window in app.windows():
        if window.handle in before:
            continue
        try:
            snapshot = app.snapshot(window.handle, 5, 500)
        except (COMError, AutomationError):
            continue
        if any(
            c.name == name and c.control_type == "MenuItem" and not c.enabled
            for c in snapshot.controls
        ):
            return True
    return False


def verify_graph_binding(state: GraphState, expected: str | None) -> None:
    """Reject stale data identity before changing axes or fit selections."""
    if expected is not None and state.data_signature != expected:
        msg = (
            "Graph data bindings changed. Call capstone_read_graph and inspect "
            "the source, dataset and unit IDs before issuing a new request."
        )
        raise AutomationError(msg)


# ---------------------------------------------------------------------------
# 3. Pure Summary Report Generator
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DuplicateNativeModelError(ValueError):
    """A renderer contains multiple entries for one native model type."""

    renderer_id: str
    native_type: int

    @override
    def __str__(self) -> str:
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
        metrics.append(
            NativeMetricValue(
                name=metric.name,
                abbreviation=metric.abbreviation,
                value=value,
            ),
        )
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
            request_model=next(
                (
                    model
                    for model, native_type in FIT_TYPES.items()
                    if native_type == fit.native_type
                ),
                None,
            ),
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
        minima.append(
            MetricMinimum(
                metric=metric,
                smallest_value=displayed,
                tied_model_ids=ties,
            ),
        )
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
        renderers=groups,
        overall_limitations=_unique_codes(limitations),
    )
