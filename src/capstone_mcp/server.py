# Copyright 2026 Capstone MCP contributors.
"""Stdio MCP entry point for Capstone UI inspection and operation."""

import base64
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, nullcontext
from typing import Annotated, Final, Literal
from uuid import UUID

import anyio
from mcp.server.fastmcp import FastMCP, Image
from mcp.types import CallToolResult, ImageContent, TextContent, ToolAnnotations
from pydantic import Field, JsonValue, TypeAdapter

from capstone_mcp.acquisition import (
    RecordingRequest,
    RecordingStatus,
    SamplingRateChange,
)
from capstone_mcp.agent_instructions import INSTRUCTIONS, GuideTopic, guide
from capstone_mcp.analysis import (
    FitInput,
    LinearFit,
    RunComparison,
    RunSamples,
    compare_runs,
    linear_fit,
)
from capstone_mcp.automation_models import NativeRequest
from capstone_mcp.automation_worker import AutomationWorker
from capstone_mcp.bridge import NativeInventory, read_inventory, read_measurement
from capstone_mcp.calculator import CreateCalculationResult
from capstone_mcp.capfile_models import (
    CapConfigurationView,
    CapDatasetPage,
    CapDatasetSummary,
    CapSection,
)
from capstone_mcp.capfiles import (
    extract_cap_datasets,
    read_cap_configuration,
    select_configuration,
)
from capstone_mcp.csv_data import CsvPage, read_csv_page
from capstone_mcp.desktop import AutomationError
from capstone_mcp.digits_display import CreateDigitsResult
from capstone_mcp.experiment_analysis import (
    CapLinearFitRequest,
    CapLinearFitResult,
    CapRunComparisonRequest,
    CapRunComparisonResult,
    compare_cap_datasets,
    fit_cap_datasets,
)
from capstone_mcp.file_workflows import FileArtifact, OpenedExperiment
from capstone_mcp.graph_control import FitGraphResult
from capstone_mcp.graph_execution import GraphCapture, GraphFailure
from capstone_mcp.graph_report import GraphAnalysisReport, summarize_graph
from capstone_mcp.graph_requests import (
    GraphAnalysisRequest,
    GraphFitOutcome,
    GraphFitRequest,
)
from capstone_mcp.graph_state import FitModel, GraphState
from capstone_mcp.graph_toolbox import (
    GraphDeltaResult,
    MeasureGraphAreaResult,
    ToggleGraphStatisticsResult,
)
from capstone_mcp.models import Action, Button, Model, Point, Result, Snapshot, Window
from capstone_mcp.oscilloscope_fft import (
    CreateFftResult,
    CreateScopeResult,
    ReadFftPeaksResult,
    ScopeTriggerResult,
)
from capstone_mcp.plotting import PlotInput, render_plot
from capstone_mcp.recipes import (
    ExperimentMacroResult,
    run_experiment_macro,
)
from capstone_mcp.repetition import AcquisitionJobs, JobStatus, RepeatPlan
from capstone_mcp.run_delete import DeleteRunResult
from capstone_mcp.run_rename import RenameRunResult
from capstone_mcp.run_visibility import SetRunVisibilityResult
from capstone_mcp.sensor_settings import (
    SamplingRateRequest,
    SensorConfiguration,
    SensorSelection,
    SensorSelectionRequest,
)
from capstone_mcp.sensor_zero import ZeroSensorResult
from capstone_mcp.signal_generator import (
    SetSignalGeneratorResult,
    SignalGeneratorStatusResult,
)
from capstone_mcp.smart_triggers import (
    KeepSampleResult,
    SamplingMode,
    SetRecordingConditionResult,
    SetSamplingModeResult,
)
from capstone_mcp.table_display import (
    CreateTableResult,
    ReadTableResult,
    SetTableColumnsResult,
)
from capstone_mcp.wireless_calibration import (
    CalibrateSensorResult,
    ConnectWirelessSensorResult,
    ScanWirelessSensorsResult,
)
from capstone_mcp.workbook_layout import (
    AddPageResult,
    PageLayoutTemplate,
    SetPageLayoutResult,
)

DEFAULT_FIT_OFFSET: Final = Point(x=20, y=20)
WORKER: Final = AutomationWorker()
JOBS: Final = AcquisitionJobs()
WINDOWS: Final = TypeAdapter(list[Window])
TEXT: Final = TypeAdapter(str)
JSON_VALUE: Final = TypeAdapter(JsonValue)


@asynccontextmanager
async def _lifespan(_server: FastMCP[None]) -> AsyncGenerator[None, None]:
    try:
        yield
    finally:
        try:
            await anyio.to_thread.run_sync(JOBS.close)
        finally:
            await anyio.to_thread.run_sync(WORKER.close)


async def _native(request: NativeRequest, *, mutates: bool = False) -> JsonValue:
    with JOBS.interaction() if mutates else nullcontext():
        if request.operation == "attach" and WORKER.retired:
            await anyio.to_thread.run_sync(WORKER.reset)
        return await anyio.to_thread.run_sync(WORKER.call, request)


MCP: Final = FastMCP(
    "capstone",
    host="127.0.0.1",
    port=8766,
    lifespan=_lifespan,
    instructions=INSTRUCTIONS,
)


@MCP.tool(annotations=ToolAnnotations(
    title="Read Capstone workflow rules", readOnlyHint=True,
    destructiveHint=False, idempotentHint=True, openWorldHint=False,
))
def capstone_guide(topic: GuideTopic | None = None) -> str:
    """Return the complete rules for one kind of work; call before starting it.

    Clients may truncate the server instructions, which therefore carry only
    the essentials. Topics: workflow, files, graphs, graph_contract, windows,
    sensors, save_export, recording, recovery. Omit topic for all of them.
    """
    return guide(topic)


class ExportedData(Model):
    """Verified native export and a bounded page of its actual text values."""

    artifact: FileArtifact
    data: CsvPage


@MCP.tool(annotations=ToolAnnotations(
    title="Insert a graph in Capstone", readOnlyHint=False,
    destructiveHint=False, idempotentHint=False, openWorldHint=False,
))
async def capstone_create_graph(
    handle: int, *, allow_foreground: bool = True,
) -> Result:
    """Insert a real graph into the active Capstone page, not a standalone PNG.

    Inspect a fresh screenshot afterward. Custom graph axes are not exposed in
    UIA; use their observed window-relative coordinates for measurement selection.
    """
    return Result.model_validate(await _native(NativeRequest(
        operation="create_graph", handle=handle,
        allow_foreground=allow_foreground,
    ), mutates=True))


@MCP.tool()
async def capstone_select_graph_measurement(
    handle: int, axis_point: Point, menu_path: list[str], frame_id: str,
    *, allow_foreground: bool = True,
) -> Result:
    """Assign an axis using its current screenshot anchor and exact menu labels.

    axis_point uses the current client-area screenshot's pixel coordinates.
    frame_id must come from capstone_observe_graph in this worker session.
    menu_path selects a measurement, optionally through nested native submenus.
    Never reuse coordinates after moving/resizing the window or graph.
    Inspect a fresh screenshot afterward to confirm the changed axis.
    """
    return Result.model_validate(await _native(NativeRequest(
        operation="select_graph_measurement", handle=handle, point=axis_point,
        menu_path=menu_path, allow_foreground=allow_foreground, frame_id=frame_id,
    ), mutates=True))


@MCP.tool(structured_output=False, annotations=ToolAnnotations(
    title="Capture graph image and one-use frame receipt", readOnlyHint=False,
    destructiveHint=False, idempotentHint=False, openWorldHint=False,
))
async def capstone_observe_graph(handle: int) -> CallToolResult:
    """Return an original-size PNG and JSON frame_id for the next graph input.

    Activates the graph window and captures its visible client-area screen pixels.
    Use coordinates from this exact image, without resizing. Graph input rejects
    changed pixels or window bounds before starting; animation or live updates
    can therefore require a new capture. A receipt is consumed by one request.
    Capture again after each graph operation or any failed input request.
    """
    capture = GraphCapture.model_validate(await _native(NativeRequest(
        operation="observe_graph", handle=handle,
    ), mutates=True))
    frame_json = capture.frame.model_dump_json()
    return CallToolResult(
        content=[
            ImageContent(type="image", data=capture.png_base64, mimeType="image/png"),
            TextContent(type="text", text=frame_json),
        ],
        structuredContent=TypeAdapter(dict[str, JsonValue]).validate_json(frame_json),
    )


@MCP.tool(annotations=ToolAnnotations(
    title="Read the last structured graph failure", readOnlyHint=True,
    destructiveHint=False, idempotentHint=True, openWorldHint=False,
))
def capstone_graph_recovery() -> GraphFailure | None:
    """Read failure stage, confirmed steps and safe next action without replay.

    This is the last graph failure, not a claim about a later successful call.
    Correlate request_id and operation. If graph_input_may_have_been_sent is true,
    inspect the app before another write; never automatically replay the request.
    """
    return WORKER.last_graph_failure


@MCP.tool(annotations=ToolAnnotations(
    title="Compare native fits within matching data bindings", readOnlyHint=False,
    destructiveHint=False, idempotentHint=True, openWorldHint=False,
))
async def capstone_graph_report(
    handle: int, *, allow_foreground: bool = True,
) -> GraphAnalysisReport:
    """Read a selected graph and group fit comparisons by exact renderer/run/units.

    Returns native parameters, free parameter counts, valid common metrics and
    descriptive MSE/RMSE minima, never an overall best-model recommendation.
    Missing sample count/residuals prevent AIC/BIC and residual-based conclusions.
    request_model contains an accepted API enum when the native model is settable.
    Uses Copy Display and replaces the clipboard; does not change fitted models.
    """
    state = GraphState.model_validate(await _native(NativeRequest(
        operation="read_graph", handle=handle, allow_foreground=allow_foreground,
    ), mutates=True))
    return summarize_graph(state)


@MCP.tool(annotations=ToolAnnotations(
    title="Inspect selected graph and native results", readOnlyHint=False,
    destructiveHint=False, idempotentHint=True, openWorldHint=False,
))
async def capstone_read_graph(
    handle: int, *, allow_foreground: bool = True,
) -> GraphState:
    """Read selected graph's actual models, native coefficients and run/unit IDs.

    Uses Display > Copy Display and replaces the Windows clipboard with the
    selected graph. Does not save or modify the experiment. Select exactly one
    graph and close menus first. Values come from Capstone, not an external fit.
    Copy data_signature into the next fitting request to guard source/run/unit
    identity. It does not fingerprint live sample contents or screenshot layout.
    """
    return GraphState.model_validate(await _native(NativeRequest(
        operation="read_graph", handle=handle, allow_foreground=allow_foreground,
    ), mutates=True))


@MCP.tool(annotations=ToolAnnotations(
    title="List accepted native fitting model names", readOnlyHint=True,
    destructiveHint=False, idempotentHint=True, openWorldHint=False,
))
def capstone_fit_models() -> list[FitModel]:
    """List supported built-in native models; custom-expression editing is excluded."""
    return list(FitModel)


@MCP.tool(annotations=ToolAnnotations(
    title="Set and verify exact native fitting models", readOnlyHint=False,
    destructiveHint=True, idempotentHint=True, openWorldHint=False,
))
async def capstone_set_graph_fits(
    handle: int, request: GraphFitRequest,
) -> GraphFitOutcome:
    """Set an exact native fit-model set and return verified native results.

    Repeated requests preserve already selected fits; [] removes all models.
    Use current screenshot anchors for menu_point (dropdown arrow) and
    master_point (fit icon, needed when fitting is disabled).
    Copies the graph before/after actions, replacing the Windows clipboard.
    Numerical failure is reported separately from verified model selection.
    First read_graph, then capstone_observe_graph for a new one-use frame_id.
    Copy data_signature to
    request.expected_data_signature; do not fabricate coordinates or model names.
    Check next_action and each fit's status/successful, not changed alone.
    """
    return GraphFitOutcome.model_validate(await _native(NativeRequest(
        operation="set_graph_fits", handle=handle,
        frame_id=request.frame_id,
        graph_request=JSON_VALUE.validate_json(request.model_dump_json()),
    ), mutates=True))


@MCP.tool(annotations=ToolAnnotations(
    title="Configure graph axes and analyze native fits", readOnlyHint=False,
    destructiveHint=True, idempotentHint=False, openWorldHint=False,
))
async def capstone_analyze_graph(
    handle: int, request: GraphAnalysisRequest,
) -> GraphFitOutcome:
    """Configure optional X/Y axes, apply model choices, and read native results.

    Create/select a graph and inspect its screenshot first. This combines named
    measurement selection with idempotent native fitting in one worker session.
    Uses the clipboard for verification. Existing unrelated displays are retained.
    fitting.expected_data_signature checks the original graph before changing
    either axis; the updated bindings are then verified for the fitting stage.
    fitting.frame_id must be the latest capstone_observe_graph receipt.
    """
    return GraphFitOutcome.model_validate(await _native(NativeRequest(
        operation="analyze_graph", handle=handle,
        frame_id=request.fitting.frame_id,
        graph_request=JSON_VALUE.validate_json(request.model_dump_json()),
    ), mutates=True))


@MCP.tool()
async def capstone_save_experiment(
    handle: int, path: str, *, allow_foreground: bool = True,
) -> FileArtifact:
    """Save As to a new .cap path and verify the completed archive.

    Never overwrites an existing file. The active experiment adopts the new path.
    Close existing dialogs before calling.
    """
    return FileArtifact.model_validate(await _native(NativeRequest(
        operation="save_experiment", handle=handle, value=path,
        allow_foreground=allow_foreground,
    ), mutates=True))


@MCP.tool()
async def capstone_open_experiment(
    handle: int, path: str,
    *, discard_unsaved: bool = False, allow_foreground: bool = True,
) -> OpenedExperiment:
    """Open an existing .cap in the attached Capstone, replacing its document.

    Uses File > Open Experiment and confirms the result by the window title.
    Prefer this to typing Ctrl+O and a path, which Capstone can ignore while it
    is still starting. Refuses when the current experiment has unsaved changes
    (title ends with *) unless discard_unsaved=true, which answers the save
    prompt with Discard. Close existing dialogs before calling.
    """
    return OpenedExperiment.model_validate(await _native(NativeRequest(
        operation="open_experiment", handle=handle, value=path,
        discard_unsaved=discard_unsaved, allow_foreground=allow_foreground,
    ), mutates=True))


@MCP.tool()
async def capstone_export_data(
    handle: int, path: str,
    offset: Annotated[int, Field(ge=0)] = 0,
    limit: Annotated[int, Field(ge=1, le=10_000)] = 1000,
    *, allow_foreground: bool = True,
) -> ExportedData:
    """Read unsaved data by native CSV export to a new path, without saving .cap.

    Selects all data and aligns by index. CSV uses Capstone's configured display
    precision, not lossless cache values. Headers preserve native labels; source
    IDs and time alignment are not inferred. The entire CSV remains at path.
    """
    artifact = FileArtifact.model_validate(await _native(NativeRequest(
        operation="export_data", handle=handle, value=path,
        allow_foreground=allow_foreground,
    ), mutates=True))
    data = await anyio.to_thread.run_sync(read_csv_page, artifact.path, offset, limit)
    return ExportedData(artifact=artifact, data=data)


@MCP.tool()
async def capstone_csv_page(
    path: str, offset: Annotated[int, Field(ge=0)] = 0,
    limit: Annotated[int, Field(ge=1, le=10_000)] = 1000,
) -> CsvPage:
    """Read another page of an existing CSV without repeating native export."""
    return await anyio.to_thread.run_sync(read_csv_page, path, offset, limit)


@MCP.tool()
async def capstone_recording_status(handle: int) -> RecordingStatus:
    """Read actual recording toggle, enabled state, and displayed time/rate."""
    return RecordingStatus.model_validate(await _native(NativeRequest(
        operation="recording_status", handle=handle,
    )))


@MCP.tool()
async def capstone_set_recording(
    handle: int, *, recording: bool, allow_foreground: bool = True,
) -> RecordingRequest:
    """Request start/stop only when the observed state differs from the request.

    Requires configured hardware/data sources. Foreground input is enabled by default.
    transition_pending=true means the requested state has not yet been observed;
    it is not a claim that acquisition succeeded.
    """
    return RecordingRequest.model_validate(await _native(NativeRequest(
        operation="set_recording", handle=handle, recording=recording,
        allow_foreground=allow_foreground,
    ), mutates=True))


@MCP.tool()
async def capstone_step_sampling_rate(
    handle: int, direction: Literal["increase", "decrease"], expected_sensor: str,
    *, allow_foreground: bool = True,
) -> SamplingRateChange:
    """Move one supported rate step for the explicitly named selected sensor.

    Read the sensor name from a fresh snapshot. Uses Capstone's native discrete
    rate buttons, not a guessed frequency setter; recording must be stopped.
    """
    return SamplingRateChange.model_validate(await _native(NativeRequest(
        operation="step_sampling_rate", handle=handle, direction=direction,
        sensor=expected_sensor,
        allow_foreground=allow_foreground,
    ), mutates=True))


@MCP.tool()
async def capstone_select_sensor(
    handle: int, request: SensorSelectionRequest,
) -> SensorSelection:
    """Select one exact sensor name from the current sampling menu and verify it."""
    return SensorSelection.model_validate(await _native(NativeRequest(
        operation="select_sensor", handle=handle, sensor=request.sensor,
        allow_foreground=request.allow_foreground,
    ), mutates=True))


@MCP.tool()
async def capstone_configure_sensor(
    handle: int, request: SamplingRateRequest,
) -> SensorConfiguration:
    """Select the named sensor and reach a supported rate such as 100 Hz.

    The target unit must match the native display. Unsupported targets restore
    the selected sensor's original rate rather than silently rounding.
    """
    return SensorConfiguration.model_validate(await _native(NativeRequest(
        operation="configure_sensor", handle=handle, sensor=request.sensor,
        target=request.target, step_limit=request.step_limit,
        allow_foreground=request.allow_foreground,
    ), mutates=True))


@MCP.tool()
async def capstone_repeat_acquisition(plan: RepeatPlan) -> JobStatus:
    """Start bounded repeated runs, confirming native start/stop events each cycle.

    Requires the debug endpoint and UI to belong to the same Capstone process,
    and an enabled recording source. Foreground input is enabled by default.
    With plan.capture, saves a baseline and each stopped run to a new directory.
    Optional source-ID fitting analyzes only newly attributed samples and compares
    completed runs. Without capture, results remain in Capstone.
    """
    return await anyio.to_thread.run_sync(JOBS.start, plan)


@MCP.tool()
def capstone_acquisition_job(job_id: str) -> JobStatus:
    """Read a repeat job's completion and confirmed-cycle receipts."""
    return JOBS.status(job_id)


@MCP.tool()
def capstone_cancel_acquisition(job_id: str) -> JobStatus:
    """Request cancellation; completion requires the worker to stop recording."""
    return JOBS.cancel(job_id)


@MCP.tool()
def capstone_plot(samples: PlotInput) -> Image:
    """Render paired numeric data as a PNG, optionally showing an OLS fit.

    Produces a standalone graph for the AI/user; does not modify Capstone pages.
    Supply explicit axis labels including units from the source metadata.
    """
    return Image(data=render_plot(samples), format="png")


@MCP.tool()
def capstone_inspect_file(
    path: str, sections: list[CapSection] | None = None,
) -> CapConfigurationView:
    """Read saved .cap hardware/settings, source metadata, pages and calculations.

    Does not open the file in Capstone or infer live hardware connectivity.
    Array decoding is independent, so unknown recorded storage types do not
    prevent configuration inspection.

    The complete result is often several hundred thousand characters, mostly
    workspace (page layout) and data_sources. Pass sections to read only what
    is needed, e.g. ["hardware_interfaces", "experiment_settings"]. Sections
    not requested are null and named in omitted_sections; omit sections for all.
    """
    return select_configuration(read_cap_configuration(path), sections)


@MCP.tool()
def capstone_file_datasets(path: str) -> list[CapDatasetSummary]:
    """List decodable saved datasets with source IDs, unit IDs and sample counts.

    run_name/run_number identify the recorded run a dataset belongs to; datasets
    of one run share its dataset_id across sources. Pair x and y by that run.

    Supports type-7 strings and type-0 tagged doubles, with stored, interval,
    or implicit-index independent coordinates.
    Unsupported array encodings raise an error instead of reporting empty data.
    """
    return [
        CapDatasetSummary(
            index=index, dataset_id=dataset.data_set_id,
            source_euid=dataset.source_euid, name=dataset.source_name,
            run_name=dataset.run_name, run_number=dataset.run_number,
            unit_id=dataset.unit_id, value_kind=dataset.value_kind,
            count=len(dataset.raw_values),
        )
        for index, dataset in enumerate(extract_cap_datasets(path))
    ]


@MCP.tool()
def capstone_extract_dataset(
    path: str, dataset_index: Annotated[int, Field(ge=0)],
    offset: Annotated[int, Field(ge=0)] = 0,
    limit: Annotated[int, Field(ge=1, le=10_000)] = 1000,
) -> CapDatasetPage:
    """Extract one sample page from a saved dataset, preserving original text.

    Numeric decimals are serialized losslessly as decimal strings. Implicit
    sample_indices are indices, not seconds. Use list tools to select the dataset.
    """
    datasets = extract_cap_datasets(path)
    if dataset_index >= len(datasets):
        msg = "Dataset index is outside this file's dataset list."
        raise AutomationError(msg)
    dataset = datasets[dataset_index]
    end = offset + limit
    return CapDatasetPage(
        dataset=CapDatasetSummary(
            index=dataset_index, dataset_id=dataset.data_set_id,
            source_euid=dataset.source_euid, name=dataset.source_name,
            run_name=dataset.run_name, run_number=dataset.run_number,
            unit_id=dataset.unit_id, value_kind=dataset.value_kind,
            count=len(dataset.raw_values),
        ),
        offset=offset,
        sample_indices=dataset.sample_indices[offset:end],
        raw_values=dataset.raw_values[offset:end],
        numeric_values=(
            None if dataset.numeric_values is None
            else dataset.numeric_values[offset:end]
        ),
        independent_values=dataset.independent_values[offset:end],
        independent_kind=dataset.independent_kind,
    )


@MCP.tool()
def capstone_fit_file(
    path: str, request: CapLinearFitRequest,
) -> CapLinearFitResult:
    """Extract and fit two explicit saved datasets, returning their full provenance."""
    return fit_cap_datasets(path, request)


@MCP.tool()
def capstone_compare_file(
    path: str, request: CapRunComparisonRequest,
) -> CapRunComparisonResult:
    """Extract and compare saved datasets with matching declared unit IDs."""
    return compare_cap_datasets(path, request)


@MCP.tool()
def capstone_linear_fit(samples: FitInput) -> LinearFit:
    """Fit supplied paired numeric samples with an intercept and standard errors.

    Performs local ordinary least squares, not a click on Capstone's fit menu.
    Standard errors assume independent residuals with common variance.
    Keep samples in their original units; no automatic unit conversion is applied.
    """
    return linear_fit(samples)


@MCP.tool()
def capstone_compare_runs(
    runs: Annotated[list[RunSamples], Field(min_length=2, max_length=50)],
) -> list[RunComparison]:
    """Compare run means, sample deviations and ranges in a common supplied unit.

    Does not start measurements or assume time alignment between runs.
    """
    return compare_runs(runs)


@MCP.tool()
async def capstone_live_configuration(
    debug_port: Annotated[int, Field(ge=1024, le=65535)] = 9223,
) -> NativeInventory:
    """Read native sensor/measurement metadata without screen scraping.

    Requires Capstone started with QTWEBENGINE_REMOTE_DEBUGGING=127.0.0.1:PORT.
    This returns the application's configured metadata, not proof that every
    listed sensor is physically connected.
    """
    return await anyio.to_thread.run_sync(read_inventory, debug_port)


@MCP.tool()
async def capstone_current_value(
    measurement_euid: UUID,
    unit_type: Annotated[int, Field(ge=0)],
    debug_port: Annotated[int, Field(ge=1024, le=65535)] = 9223,
) -> float:
    """Read one native current value using IDs returned by live configuration.

    Unavailable values raise an error rather than returning a fabricated zero.
    This is not an extraction of an entire recorded run.
    """
    return await anyio.to_thread.run_sync(
        read_measurement, debug_port, "{" + str(measurement_euid) + "}", unit_type,
    )


@MCP.tool()
async def capstone_attach(
    *, launch: bool = False,
    process_id: Annotated[int, Field(gt=0)] | None = None,
) -> list[Window]:
    """Attach to installed Capstone, optionally selecting an exact process ID."""
    return WINDOWS.validate_python(await _native(NativeRequest(
        operation="attach", launch=launch, process_id=process_id,
    ), mutates=True))


@MCP.tool()
async def capstone_windows() -> list[Window]:
    """List Capstone windows, including file dialogs and modal dialogs."""
    return WINDOWS.validate_python(await _native(NativeRequest(operation="windows")))


@MCP.tool()
async def capstone_snapshot(
    handle: int,
    depth: Annotated[int, Field(ge=1, le=30)] = 12,
    limit: Annotated[int, Field(ge=1, le=3000)] = 800,
    query: Annotated[str, Field(max_length=200)] = "",
    control_types: Annotated[list[str], Field(max_length=20)] | None = None,
) -> Snapshot:
    """Read control names, roles, bounds, and fresh action references.

    A full experiment window holds hundreds of controls. Pass query, a
    case-insensitive substring of a control's name or automation_id, and/or
    control_types such as ["Button", "CheckBox"] to return only the matches.
    depth and limit still bound the traversal, so truncated=true means an
    unvisited control may match. Custom-drawn graph toolbars are not exposed.
    """
    return Snapshot.model_validate(await _native(NativeRequest(
        operation="snapshot", handle=handle, depth=depth, limit=limit,
        query=query, control_types=control_types or [],
    )))


@MCP.tool()
async def capstone_action(
    ref: str, action: Action, *, allow_foreground: bool = True,
) -> Result:
    """Activate by click (invoke), or use UIA toggle/select/expand/collapse/focus.

    Foreground input defaults to true. Avoids Capstone's blocking modal
    InvokePattern provider; this is physical input, not background UIA Invoke.
    """
    return Result.model_validate(await _native(NativeRequest(
        operation="action", ref=ref, action=action, allow_foreground=allow_foreground,
    ), mutates=True))


@MCP.tool()
async def capstone_read_value(ref: str) -> str:
    """Read literal current text from a control's UIA Value pattern."""
    return TEXT.validate_python(await _native(NativeRequest(
        operation="read_value", ref=ref,
    )))


@MCP.tool()
async def capstone_set_value(ref: str, value: str) -> Result:
    """Set literal text in a control supporting the UIA Value pattern."""
    return Result.model_validate(await _native(NativeRequest(
        operation="set_value", ref=ref, value=value,
    ), mutates=True))


@MCP.tool()
async def capstone_screenshot(
    handle: int,
    *,
    scale: float = 1.0,
    crop_region: list[int] | None = None,
) -> Image:
    """Capture PNG pixels at native resolution, optionally scaled or cropped.

    Does not raise the target window to the foreground.
    """
    encoded = TEXT.validate_python(await _native(NativeRequest(
        operation="screenshot", handle=handle, scale=scale,
        crop_region=crop_region,
    )))
    return Image(data=base64.b64decode(encoded, validate=True), format="png")


@MCP.tool()
async def capstone_click(
    handle: int, point: Point, button: Button = Button.LEFT,
    *, double: bool = False, allow_foreground: bool = True,
) -> Result:
    """Click window-relative pixels; foreground input is enabled by default."""
    return Result.model_validate(await _native(NativeRequest(
        operation="click", handle=handle, point=point, button=button,
        double=double, allow_foreground=allow_foreground,
    ), mutates=True))


@MCP.tool()
async def capstone_drag(
    handle: int, start: Point, end: Point, *, allow_foreground: bool = True,
) -> Result:
    """Drag between window-relative pixels; hard timeout leaves outcome uncertain."""
    return Result.model_validate(await _native(NativeRequest(
        operation="drag", handle=handle, point=start, end=end,
        allow_foreground=allow_foreground,
    ), mutates=True))


@MCP.tool()
async def capstone_scroll(
    handle: int, point: Point,
    notches: Annotated[int, Field(ge=-100, le=100)],
    *, allow_foreground: bool = True,
) -> Result:
    """Scroll at window-relative pixels; positive notches scroll upward."""
    return Result.model_validate(await _native(NativeRequest(
        operation="scroll", handle=handle, point=point, notches=notches,
        allow_foreground=allow_foreground,
    ), mutates=True))


@MCP.tool()
async def capstone_keys(
    handle: int, keys: str, *, allow_foreground: bool = True,
) -> Result:
    """Send pywinauto key syntax: ^o, {ESC}, {ENTER}, %{F4}. Changes focus."""
    return Result.model_validate(await _native(NativeRequest(
        operation="keys", handle=handle, value=keys, allow_foreground=allow_foreground,
    ), mutates=True))


@MCP.tool()
async def capstone_type_text(
    handle: int, text: str, *, allow_foreground: bool = True,
) -> Result:
    """Type literal Unicode text in the focused field, escaping shortcut syntax."""
    escaped = "".join(
        "{" + char + "}" if char in "+^%~(){}" else char for char in text
    )
    return Result.model_validate(await _native(NativeRequest(
        operation="keys", handle=handle, value=escaped,
        allow_foreground=allow_foreground, unicode_input=True,
    ), mutates=True))


@MCP.tool()
async def capstone_fit_graph(
    handle: int = 0,
    *,
    mode: Literal["scale_to_fit", "manual_bounds"] = "scale_to_fit",
    graph_name: str | None = None,
    offset: Point = DEFAULT_FIT_OFFSET,
    allow_foreground: bool = True,
) -> FitGraphResult:
    """Scale graph axes to fit all data or adjust bounds deterministically.

    Args:
        handle: Capstone main window handle (0 for active window).
        mode: Scaling mode ('scale_to_fit' or 'manual_bounds').
        graph_name: Target graph display name (None for active graph).
        offset: Offset coordinate point for scale-to-fit toolbar icon.
        allow_foreground: Bring window to foreground for UI automation.

    Returns:
        FitGraphResult with scaling outcome and graph identity.
    """
    return FitGraphResult.model_validate(await _native(NativeRequest(
        operation="fit_graph", handle=handle, mode=mode,
        target=graph_name or "", point=offset,
        allow_foreground=allow_foreground,
    ), mutates=True))


@MCP.tool()
async def capstone_rename_run(
    handle: int,
    old_name: str,
    new_name: str,
    *,
    allow_foreground: bool = True,
) -> RenameRunResult:
    """Rename a specific Run item in the Data Summary tree safely.

    Args:
        handle: Capstone main window handle.
        old_name: Existing run name in Data Summary (e.g. 'Run #1').
        new_name: Desired new name for the run (e.g. 'Baseline trial').
        allow_foreground: Bring window to foreground for UI automation.

    Returns:
        RenameRunResult with rename confirmation and updated run list.
    """
    return RenameRunResult.model_validate(await _native(NativeRequest(
        operation="rename_run", handle=handle, old_name=old_name,
        new_name=new_name, allow_foreground=allow_foreground,
    ), mutates=True))


@MCP.tool()
async def capstone_create_calculation(
    expression: str,
    handle: int = 0,
    *,
    unit: str | None = None,
    allow_foreground: bool = True,
    keep_open: bool = False,
) -> CreateCalculationResult:
    """Register a formula and optional unit in Capstone Calculator with auto-cleanup.

    Args:
        expression: Mathematical formula (e.g. 'KE = 0.5 * [Mass] * [Velocity]^2').
        handle: Capstone main window handle (0 for active window).
        unit: Optional physical unit string for the computed variable (e.g. 'J').
        allow_foreground: Bring window to foreground for UI automation.
        keep_open: Leave calculator side drawer open after registration.

    Returns:
        CreateCalculationResult with created variable name, formula, and status.
    """
    return CreateCalculationResult.model_validate(await _native(NativeRequest(
        operation="create_calculation", handle=handle, expression=expression,
        unit=unit, allow_foreground=allow_foreground, keep_open=keep_open,
    ), mutates=True))


@MCP.tool()
async def capstone_delete_run(
    handle: int = 0,
    *,
    run_name: str = "last_run",
    allow_foreground: bool = True,
) -> DeleteRunResult:
    """Delete a run from Data Summary, auto-confirming any modal dialog.

    Args:
        handle: Capstone main window handle (0 for active window).
        run_name: Name of the run to delete, or 'last_run' for most recent run.
        allow_foreground: Bring window to foreground for UI automation.

    Returns:
        DeleteRunResult with deleted run name and remaining runs.
    """
    return DeleteRunResult.model_validate(await _native(NativeRequest(
        operation="delete_run", handle=handle, run_name=run_name,
        allow_foreground=allow_foreground,
    ), mutates=True))


@MCP.tool()
async def capstone_zero_sensor(
    handle: int = 0,
    *,
    sensor_name: str | None = None,
    allow_foreground: bool = True,
) -> ZeroSensorResult:
    """Execute zero/tare for all connected sensors or a specified target sensor.

    Args:
        handle: Capstone main window handle (0 for active window).
        sensor_name: Target sensor to zero (e.g. 'Force Sensor', None for all).
        allow_foreground: Bring window to foreground for UI automation.

    Returns:
        ZeroSensorResult with zeroed sensor list and confirmation status.
    """
    return ZeroSensorResult.model_validate(await _native(NativeRequest(
        operation="zero_sensor", handle=handle, sensor_name=sensor_name,
        allow_foreground=allow_foreground,
    ), mutates=True))


@MCP.tool()
async def capstone_create_table(
    handle: int = 0,
    *,
    table_name: str | None = None,
    allow_foreground: bool = True,
) -> CreateTableResult:
    """Create a new Table display widget on the active workbook page.

    Args:
        handle: Capstone main window handle (0 for active window).
        table_name: Optional title or name for the created table display.
        allow_foreground: Bring window to foreground for UI automation.

    Returns:
        CreateTableResult with table_id, name, columns, and status.
    """
    return CreateTableResult.model_validate(await _native(NativeRequest(
        operation="create_table",
        handle=handle,
        table_name=table_name,
        allow_foreground=allow_foreground,
    ), mutates=True))


@MCP.tool()
async def capstone_set_table_columns(
    columns: list[str],
    handle: int = 0,
    *,
    table_name: str | None = None,
    allow_foreground: bool = True,
) -> SetTableColumnsResult:
    """Configure columns and data bindings for a Table display.

    Args:
        columns: List of measurement or calculation names to map as table columns.
        handle: Capstone main window handle (0 for active window).
        table_name: Target table display name or ID (None targets active table).
        allow_foreground: Bring window to foreground for UI automation.

    Returns:
        SetTableColumnsResult with updated columns list and binding status.
    """
    return SetTableColumnsResult.model_validate(await _native(NativeRequest(
        operation="set_table_columns",
        handle=handle,
        columns=columns,
        table_name=table_name,
        allow_foreground=allow_foreground,
    ), mutates=True))


@MCP.tool()
async def capstone_read_table(  # noqa: PLR0913
    handle: int = 0,
    *,
    table_name: str | None = None,
    page: int = 1,
    page_size: int = 50,
    include_statistics: bool = True,
    allow_foreground: bool = True,
) -> ReadTableResult:
    """Read rendered table rows, pagination info, and summary statistics.

    Args:
        handle: Capstone main window handle (0 for active window).
        table_name: Target table display name or ID (None targets active table).
        page: Page number for paginated rows (1-based, default 1).
        page_size: Number of rows per page (default 50).
        include_statistics: Include summary statistics (mean, std_dev, min, max).
        allow_foreground: Bring window to foreground for UI automation.

    Returns:
        ReadTableResult containing headers, rows, total_rows, and statistics.
    """
    return ReadTableResult.model_validate(await _native(NativeRequest(
        operation="read_table",
        handle=handle,
        table_name=table_name,
        page=page,
        page_size=page_size,
        include_statistics=include_statistics,
        allow_foreground=allow_foreground,
    ), mutates=False))


@MCP.tool()
async def capstone_create_digits(
    handle: int = 0,
    *,
    measurement: str | None = None,
    digits_name: str | None = None,
    allow_foreground: bool = True,
) -> CreateDigitsResult:
    """Create a large Digits numeric display and optionally bind a measurement.

    Args:
        handle: Capstone main window handle (0 for active window).
        measurement: Sensor measurement or calculation name to monitor.
        digits_name: Optional custom title/name for the digits display widget.
        allow_foreground: Bring window to foreground for UI automation.

    Returns:
        CreateDigitsResult with digits_id, name, bound measurement, and unit.
    """
    return CreateDigitsResult.model_validate(await _native(NativeRequest(
        operation="create_digits",
        handle=handle,
        measurement=measurement,
        digits_name=digits_name,
        allow_foreground=allow_foreground,
    ), mutates=True))


@MCP.tool()
async def capstone_toggle_graph_statistics(
    handle: int = 0,
    *,
    graph_name: str | None = None,
    enable: bool | None = None,
    allow_foreground: bool = True,
) -> ToggleGraphStatisticsResult:
    """Toggle graph statistics box (Σ) and read descriptive statistics.

    Args:
        handle: Capstone main window handle (0 for active window).
        graph_name: Specific graph display name (None targets active graph).
        enable: Explicitly enable (True), disable (False), or toggle (None).
        allow_foreground: Bring window to foreground for UI automation.

    Returns:
        ToggleGraphStatisticsResult with statistics dict (mean, min, max, std_dev).
    """
    return ToggleGraphStatisticsResult.model_validate(await _native(NativeRequest(
        operation="toggle_graph_statistics",
        handle=handle,
        graph_name=graph_name,
        enable=enable,
        allow_foreground=allow_foreground,
    ), mutates=True))


@MCP.tool()
async def capstone_measure_graph_area(
    handle: int = 0,
    *,
    graph_name: str | None = None,
    enable: bool | None = None,
    allow_foreground: bool = True,
) -> MeasureGraphAreaResult:
    """Toggle graph area integration tool (∫ydx) and extract integral value.

    Args:
        handle: Capstone main window handle (0 for active window).
        graph_name: Specific graph display name (None targets active graph).
        enable: Explicitly enable (True), disable (False), or toggle (None).
        allow_foreground: Bring window to foreground for UI automation.

    Returns:
        MeasureGraphAreaResult with area value, integral units, and active status.
    """
    return MeasureGraphAreaResult.model_validate(await _native(NativeRequest(
        operation="measure_graph_area",
        handle=handle,
        graph_name=graph_name,
        enable=enable,
        allow_foreground=allow_foreground,
    ), mutates=True))


@MCP.tool()
async def capstone_graph_delta(
    handle: int = 0,
    *,
    graph_name: str | None = None,
    point1: Point | None = None,
    point2: Point | None = None,
    allow_foreground: bool = True,
) -> GraphDeltaResult:
    """Activate delta crosshair tool and read coordinate differences (Δx, Δy).

    Args:
        handle: Capstone main window handle (0 for active window).
        graph_name: Specific graph display name (None targets active graph).
        point1: First reference coordinate point (Point(x=..., y=...)).
        point2: Second reference coordinate point (Point(x=..., y=...)).
        allow_foreground: Bring window to foreground for UI automation.

    Returns:
        GraphDeltaResult with delta_x, delta_y, slope, and crosshair state.
    """
    return GraphDeltaResult.model_validate(await _native(NativeRequest(
        operation="graph_delta",
        handle=handle,
        graph_name=graph_name,
        point1=point1,
        point2=point2,
        allow_foreground=allow_foreground,
    ), mutates=True))


@MCP.tool()
async def capstone_set_run_visibility(
    runs: list[str],
    handle: int = 0,
    *,
    visible: bool = True,
    target_displays: list[str] | None = None,
    allow_foreground: bool = True,
) -> SetRunVisibilityResult:
    """Control visibility (show/hide) of specific runs on displays.

    Args:
        runs: List of run names (e.g. ['Run #1', 'Run #2']).
        handle: Capstone main window handle (0 for active window).
        visible: Whether to make the specified runs visible (True) or hidden (False).
        target_displays: Specific display names to filter, or None for all displays.
        allow_foreground: Bring window to foreground for UI automation.

    Returns:
        SetRunVisibilityResult with list of currently visible runs.
    """
    return SetRunVisibilityResult.model_validate(await _native(NativeRequest(
        operation="set_run_visibility",
        handle=handle,
        runs=runs,
        visible=visible,
        target_displays=target_displays,
        allow_foreground=allow_foreground,
    ), mutates=True))


@MCP.tool()
async def capstone_set_signal_generator(  # noqa: PLR0913
    handle: int = 0,
    *,
    waveform: str = "Sine",
    frequency: float | None = 1000.0,
    amplitude: float | None = 1.0,
    enabled: bool = True,
    generator_name: str | None = None,
    allow_foreground: bool = True,
    keep_open: bool = False,
) -> SetSignalGeneratorResult:
    """Configure signal generator waveform, frequency, amplitude, and power.

    Args:
        handle: Capstone main window handle (0 for active window).
        waveform: Shape ('Sine', 'Square', 'Triangle', 'Ramp Up', 'Ramp Down', 'DC').
        frequency: Target frequency in Hertz (Hz).
        amplitude: Target peak amplitude in Volts (V).
        enabled: Turn signal output On (True) or Off (False).
        generator_name: Target generator channel ('Output 1', None for default).
        allow_foreground: Bring window to foreground for UI automation.
        keep_open: Keep signal generator side drawer open after configuration.

    Returns:
        SetSignalGeneratorResult with applied parameters and output status.
    """
    return SetSignalGeneratorResult.model_validate(await _native(NativeRequest(
        operation="set_signal_generator",
        handle=handle,
        waveform=waveform,
        frequency=frequency,
        amplitude=amplitude,
        enabled=enabled,
        generator_name=generator_name,
        allow_foreground=allow_foreground,
        keep_open=keep_open,
    ), mutates=True))


@MCP.tool()
async def capstone_read_signal_generator_status(
    handle: int = 0,
    *,
    generator_name: str | None = None,
    allow_foreground: bool = True,
    keep_open: bool = False,
) -> SignalGeneratorStatusResult:
    """Read current waveform, frequency, amplitude, and power of signal generator.

    Args:
        handle: Capstone main window handle (0 for active window).
        generator_name: Target generator channel (e.g. 'Output 1', None for default).
        allow_foreground: Bring window to foreground for UI automation.
        keep_open: Keep signal generator side drawer open after reading.

    Returns:
        SignalGeneratorStatusResult with waveform, frequency, amplitude, and enabled.
    """
    return SignalGeneratorStatusResult.model_validate(await _native(NativeRequest(
        operation="read_signal_generator_status",
        handle=handle,
        generator_name=generator_name,
        allow_foreground=allow_foreground,
        keep_open=keep_open,
    ), mutates=True))


@MCP.tool()
async def capstone_create_scope(
    handle: int = 0,
    *,
    timebase: str | float | None = None,
    channel: str | None = None,
    allow_foreground: bool = True,
) -> CreateScopeResult:
    """Create an Oscilloscope display widget on the active page.

    Args:
        handle: Capstone main window handle (0 for active window).
        timebase: Timebase setting (e.g. '1 ms/div', '100 us/div').
        channel: Input sensor channel or measurement name.
        allow_foreground: Bring window to foreground for UI automation.

    Returns:
        CreateScopeResult with scope_id, channel, and timebase.
    """
    return CreateScopeResult.model_validate(await _native(NativeRequest(
        operation="create_scope",
        handle=handle,
        timebase=str(timebase) if timebase is not None else None,
        channel=channel,
        allow_foreground=allow_foreground,
    ), mutates=True))


@MCP.tool()
async def capstone_set_scope_trigger(  # noqa: PLR0913
    handle: int = 0,
    *,
    scope_id: str | None = None,
    trigger_level: float = 0.0,
    trigger_slope: str = "rising",
    trigger_mode: str = "auto",
    trigger_source: str | None = None,
    allow_foreground: bool = True,
) -> ScopeTriggerResult:
    """Configure oscilloscope trigger level, slope edge, mode, and source.

    Args:
        handle: Capstone main window handle (0 for active window).
        scope_id: Specific scope display ID (None targets active scope).
        trigger_level: Threshold voltage level for trigger (Volts).
        trigger_slope: Slope edge ('rising' or 'falling').
        trigger_mode: Trigger mode ('auto', 'normal', or 'single').
        trigger_source: Channel name to trigger from.
        allow_foreground: Bring window to foreground for UI automation.

    Returns:
        ScopeTriggerResult with applied trigger configuration.
    """
    return ScopeTriggerResult.model_validate(await _native(NativeRequest(
        operation="set_scope_trigger",
        handle=handle,
        scope_id=scope_id,
        trigger_level=trigger_level,
        trigger_slope=trigger_slope,
        trigger_mode=trigger_mode,
        trigger_source=trigger_source,
        allow_foreground=allow_foreground,
    ), mutates=True))


@MCP.tool()
async def capstone_create_fft(
    handle: int = 0,
    *,
    measurement: str | None = None,
    frequency_range: str | None = None,
    allow_foreground: bool = True,
) -> CreateFftResult:
    """Create an FFT frequency spectrum display widget.

    Args:
        handle: Capstone main window handle (0 for active window).
        measurement: Input sensor channel or signal measurement to analyze.
        frequency_range: Maximum frequency span (e.g. '1000 Hz', '20 kHz').
        allow_foreground: Bring window to foreground for UI automation.

    Returns:
        CreateFftResult with fft_id, measurement, and frequency_range.
    """
    return CreateFftResult.model_validate(await _native(NativeRequest(
        operation="create_fft",
        handle=handle,
        measurement=measurement,
        frequency_range=frequency_range,
        allow_foreground=allow_foreground,
    ), mutates=True))


@MCP.tool()
async def capstone_read_fft_peaks(
    handle: int = 0,
    *,
    fft_id: str | None = None,
    top_k: int = 5,
    allow_foreground: bool = True,
) -> ReadFftPeaksResult:
    """Read top peak frequencies and amplitudes from FFT display.

    Args:
        handle: Capstone main window handle (0 for active window).
        fft_id: Specific FFT display ID (None targets active FFT).
        top_k: Number of highest harmonic peaks to extract (default 5).
        allow_foreground: Bring window to foreground for UI automation.

    Returns:
        ReadFftPeaksResult with list of detected frequency peaks and amplitudes.
    """
    return ReadFftPeaksResult.model_validate(await _native(NativeRequest(
        operation="read_fft_peaks",
        handle=handle,
        fft_id=fft_id,
        top_k=top_k,
        allow_foreground=allow_foreground,
    ), mutates=False))


@MCP.tool()
async def capstone_set_recording_condition(
    handle: int = 0,
    *,
    start_condition: dict[str, JsonValue] | None = None,
    stop_condition: dict[str, JsonValue] | None = None,
    allow_foreground: bool = True,
    keep_open: bool = False,
) -> SetRecordingConditionResult:
    """Configure start/stop recording conditions based on time or threshold.

    Args:
        handle: Capstone main window handle (0 for active window).
        start_condition: Start criteria (e.g. {'type': 'threshold', 'value': 0.5}).
        stop_condition: Stop criteria (e.g. {'type': 'time', 'duration_seconds': 5.0}).
        allow_foreground: Bring window to foreground for UI automation.
        keep_open: Leave recording condition drawer open.

    Returns:
        SetRecordingConditionResult with applied start/stop conditions.
    """
    return SetRecordingConditionResult.model_validate(await _native(NativeRequest(
        operation="set_recording_condition",
        handle=handle,
        start_condition=start_condition,
        stop_condition=stop_condition,
        allow_foreground=allow_foreground,
        keep_open=keep_open,
    ), mutates=True))


@MCP.tool()
async def capstone_set_sampling_mode(
    mode: SamplingMode = "continuous",
    handle: int = 0,
    *,
    allow_foreground: bool = True,
) -> SetSamplingModeResult:
    """Switch sampling mode between continuous, keep_sample, and fast_monitor.

    Args:
        mode: Sampling mode ('continuous', 'keep_sample', or 'fast_monitor').
        handle: Capstone main window handle (0 for active window).
        allow_foreground: Bring window to foreground for UI automation.

    Returns:
        SetSamplingModeResult with active mode and description.
    """
    return SetSamplingModeResult.model_validate(await _native(NativeRequest(
        operation="set_sampling_mode",
        handle=handle,
        sampling_mode=mode,
        allow_foreground=allow_foreground,
    ), mutates=True))


@MCP.tool()
async def capstone_keep_sample(
    handle: int = 0,
    *,
    value: float | None = None,
    variable_name: str | None = None,
    allow_foreground: bool = True,
) -> KeepSampleResult:
    """Record one manual sample point in keep_sample mode.

    Args:
        handle: Capstone main window handle (0 for active window).
        value: Optional manual independent variable value (e.g. mass, concentration).
        variable_name: Name of the independent variable being recorded.
        allow_foreground: Bring window to foreground for UI automation.

    Returns:
        KeepSampleResult with recorded sample index, values, and total points.
    """
    return KeepSampleResult.model_validate(await _native(NativeRequest(
        operation="keep_sample",
        handle=handle,
        sample_value=value,
        variable_name=variable_name,
        allow_foreground=allow_foreground,
    ), mutates=True))


@MCP.tool()
async def capstone_scan_wireless_sensors(
    handle: int = 0,
    *,
    timeout_seconds: float = 5.0,
    allow_foreground: bool = True,
    keep_open: bool = False,
) -> ScanWirelessSensorsResult:
    """Scan for nearby wireless Bluetooth PASCO sensors.

    Args:
        handle: Capstone main window handle (0 for active window).
        timeout_seconds: Duration in seconds to scan for advertising devices.
        allow_foreground: Bring window to foreground for UI automation.
        keep_open: Leave hardware setup drawer open after scan.

    Returns:
        ScanWirelessSensorsResult with discovered sensor IDs and names.
    """
    return ScanWirelessSensorsResult.model_validate(await _native(NativeRequest(
        operation="scan_wireless_sensors",
        handle=handle,
        timeout_seconds=timeout_seconds,
        allow_foreground=allow_foreground,
        keep_open=keep_open,
    ), mutates=True))


@MCP.tool()
async def capstone_connect_wireless_sensor(
    sensor_id: str,
    handle: int = 0,
    *,
    allow_foreground: bool = True,
    keep_open: bool = False,
) -> ConnectWirelessSensorResult:
    """Pair and connect a discovered wireless sensor by sensor_id.

    Args:
        sensor_id: Discovered sensor hardware ID or Bluetooth name.
        handle: Capstone main window handle (0 for active window).
        allow_foreground: Bring window to foreground for UI automation.
        keep_open: Leave hardware setup drawer open after pairing.

    Returns:
        ConnectWirelessSensorResult with connection status and battery level.
    """
    return ConnectWirelessSensorResult.model_validate(await _native(NativeRequest(
        operation="connect_wireless_sensor",
        handle=handle,
        sensor_id=sensor_id,
        allow_foreground=allow_foreground,
        keep_open=keep_open,
    ), mutates=True))


@MCP.tool()
async def capstone_calibrate_sensor(  # noqa: PLR0913
    sensor_name: str,
    handle: int = 0,
    *,
    measurement_type: str | None = None,
    calibration_type: str = "two_point",
    standard_1: float = 0.0,
    standard_2: float | None = None,
    allow_foreground: bool = True,
    keep_open: bool = False,
) -> CalibrateSensorResult:
    """Execute sensor calibration wizard with standard reference points.

    Args:
        sensor_name: Target sensor to calibrate (e.g. 'Force Sensor', 'pH Sensor').
        handle: Capstone main window handle (0 for active window).
        measurement_type: Measurement to calibrate (e.g. 'Force', 'pH').
        calibration_type: Calibration wizard type ('one_point' or 'two_point').
        standard_1: First reference standard physical value.
        standard_2: Second reference standard physical value (required for two_point).
        allow_foreground: Bring window to foreground for UI automation.
        keep_open: Leave calibration dialog/drawer open.

    Returns:
        CalibrateSensorResult with calibration status, slope, and offset.
    """
    return CalibrateSensorResult.model_validate(await _native(NativeRequest(
        operation="calibrate_sensor",
        handle=handle,
        sensor_name=sensor_name,
        measurement_type=measurement_type,
        calibration_type=calibration_type,
        standard_1=standard_1,
        standard_2=standard_2,
        allow_foreground=allow_foreground,
        keep_open=keep_open,
    ), mutates=True))


@MCP.tool()
async def capstone_add_page(
    handle: int = 0,
    *,
    title: str = "New Page",
    allow_foreground: bool = True,
) -> AddPageResult:
    """Add a new page tab to the Capstone workbook.

    Args:
        handle: Capstone main window handle (0 for active window).
        title: Title/name for the newly added page tab.
        allow_foreground: Bring window to foreground for UI automation.

    Returns:
        AddPageResult with page_index, title, and total pages count.
    """
    return AddPageResult.model_validate(await _native(NativeRequest(
        operation="add_page",
        handle=handle,
        title=title,
        allow_foreground=allow_foreground,
    ), mutates=True))


@MCP.tool()
async def capstone_set_page_layout(
    layout: PageLayoutTemplate = "two_vertical",
    handle: int = 0,
    *,
    page_name: str | None = None,
    allow_foreground: bool = True,
) -> SetPageLayoutResult:
    """Apply a multi-display split layout template to the active or target page.

    Args:
        layout: Split template ('two_vertical', 'two_horizontal',
            'three_pane', 'four_grid').
        handle: Capstone main window handle (0 for active window).
        page_name: Specific page name to layout (None targets active page).
        allow_foreground: Bring window to foreground for UI automation.

    Returns:
        SetPageLayoutResult with layout template and display placeholders.
    """
    return SetPageLayoutResult.model_validate(await _native(NativeRequest(
        operation="set_page_layout",
        handle=handle,
        layout=layout,
        page_name=page_name,
        allow_foreground=allow_foreground,
    ), mutates=True))


@MCP.tool()
async def capstone_run_experiment_macro(
    experiment_id: str,
    action: str = "run",
    parameters: dict[str, JsonValue] | None = None,
) -> ExperimentMacroResult:
    """Execute high-level automation macro for canonical physics experiments.

    Supported experiments:
    - 'photoelectric_effect': Mercury lamp wavelength sweep (365, 405, 436, 546,
      577 nm), DC amplifier Ch A / DC power supply Ch B, Keep Sample stopping
      potential acquisition, and h/e linear fit.
    - 'rlc_resonance': 850 Signal generator sine sweep (10Hz-10kHz), Scope/FFT
      peak measurement, resonant frequency f_0, and Q-factor calculation.
    - 'forced_harmonic_oscillation' / 'forced_oscillation': Smart Cart 100Hz
      position, 480s stop condition, resonance amplitude curve, and damping b.
    - 'adiabatic_gas': 1000Hz sampling, cyclic work area integration (oint P dV),
      and adiabatic index gamma fit (PV^gamma = const).
    - 'slit_diffraction': Light intensity vs position scan, diffraction
      minima/maxima extraction, and slit geometry (width a, separation d).

    Actions:
    - 'setup': Configure apparatus sensors, displays, and excitation sources.
    - 'acquire': Record or sample experimental datasets.
    - 'analyze': Perform numerical regression, peak detection, and error metrics.
    - 'run': Sequentially execute setup, acquire, and analyze phases.
    """
    params = dict(parameters or {})
    return run_experiment_macro(
        experiment_id=experiment_id,
        action=action,
        parameters=params,
    )


# ---------------------------------------------------------------------------
# MCP Resources
# ---------------------------------------------------------------------------


@MCP.resource("capstone://status")
async def capstone_status_resource() -> str:
    """Return JSON status of the local Capstone application and connection."""
    windows_json = await _native(NativeRequest(operation="windows"), mutates=False)
    recording_json = await _native(
        NativeRequest(operation="recording_status"), mutates=False,
    )
    status_doc = {
        "server": "capstone-mcp",
        "version": "0.1.0",
        "worker_retired": WORKER.retired,
        "windows": windows_json,
        "recording": recording_json,
    }
    return JSON_VALUE.dump_json(status_doc, indent=2).decode("utf-8")


@MCP.resource("capstone://guide")
def capstone_guide_resource() -> str:
    """Return the complete workflow guidance manual for PASCO Capstone."""
    return guide()


# ---------------------------------------------------------------------------
# MCP Prompts
# ---------------------------------------------------------------------------


@MCP.prompt()
def resonance_experiment_workflow(
    frequency_hz: float = 1000.0,
    amplitude_v: float = 2.0,
) -> str:
    """Guided prompt template for setting up an RLC/acoustic resonance experiment."""
    return (
        "Please set up and run an acoustic/electrical resonance experiment in "
        "PASCO Capstone:\n"
        f"1. Turn on the 850/550 Signal Generator (capstone_set_signal_generator) "
        f"with a Sine wave at {frequency_hz} Hz and {amplitude_v} V amplitude.\n"
        "2. Add an Oscilloscope display (capstone_create_scope) to monitor the input "
        "and sensor output waveforms, and configure rising edge trigger "
        "(capstone_set_scope_trigger).\n"
        "3. Create an FFT display (capstone_create_fft) and extract the top "
        "harmonic frequency peaks (capstone_read_fft_peaks) to identify resonance.\n"
        "4. Report the measured peak frequency and amplitude comparison back to me."
    )


@MCP.prompt()
def collision_impulse_experiment(
    threshold_force_n: float = 0.5,
) -> str:
    """Guided prompt template for automated collision impulse measurement."""
    return (
        "Please set up a dynamics cart collision experiment in PASCO Capstone:\n"
        "1. Set an automated recording start condition "
        "(capstone_set_recording_condition) triggered when Force exceeds "
        f"{threshold_force_n} N.\n"
        "2. Arrange the page into a two-pane layout (capstone_set_page_layout "
        "with 'two_vertical') containing a Graph and a Table.\n"
        "3. Once collision data is recorded, integrate the area under the "
        "Force-Time curve (capstone_measure_graph_area) to compute the total "
        "impulse (integral of F dt).\n"
        "4. Extract summary statistics (capstone_toggle_graph_statistics) and "
        "display the resulting impulse and momentum values."
    )


@MCP.prompt()
def titration_keep_sample_workflow(
    volume_step_ml: float = 1.0,
) -> str:
    """Guided prompt template for manual point sampling (e.g. pH titration)."""
    return (
        "Please configure a manual point-by-point sampling workflow in PASCO "
        "Capstone:\n"
        "1. Switch the sampling mode to manual keep-sample "
        "(capstone_set_sampling_mode with mode='keep_sample').\n"
        "2. Create a Table display (capstone_create_table) and set columns "
        f"(capstone_set_table_columns) with 'Volume' (step {volume_step_ml} mL) "
        "and 'pH'.\n"
        "3. Guide me through recording each droplet measurement point using "
        "capstone_keep_sample(value=..., variable_name='Volume')."
    )


@MCP.prompt()
def sensor_calibration_workflow(
    sensor_name: str = "Force Sensor",
) -> str:
    """Guided prompt template for a guided 2-point sensor calibration wizard."""
    return (
        f"Please calibrate the connected '{sensor_name}' in PASCO Capstone:\n"
        "1. Open the calibration wizard (capstone_calibrate_sensor) using "
        "2-point calibration.\n"
        "2. Guide me through measuring Standard 1 (zero load) and Standard 2 "
        "(known calibration weight or buffer).\n"
        "3. Confirm calibration completion and verify sensor reading matches "
        "the reference value."
    )


def main() -> None:
    """Serve MCP over stdio; diagnostics must never go to stdout."""
    MCP.run(transport="stdio")


def http_main() -> None:
    """Serve only on loopback for local MCP clients supporting HTTP."""
    MCP.run(transport="streamable-http")


if __name__ == "__main__":
    main()
