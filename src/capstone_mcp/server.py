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
from capstone_mcp.agent_instructions import INSTRUCTIONS
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
from capstone_mcp.capfile_models import (
    CapConfiguration,
    CapDatasetPage,
    CapDatasetSummary,
)
from capstone_mcp.capfiles import extract_cap_datasets, read_cap_configuration
from capstone_mcp.csv_data import CsvPage, read_csv_page
from capstone_mcp.desktop import AutomationError
from capstone_mcp.experiment_analysis import (
    CapLinearFitRequest,
    CapLinearFitResult,
    CapRunComparisonRequest,
    CapRunComparisonResult,
    compare_cap_datasets,
    fit_cap_datasets,
)
from capstone_mcp.file_workflows import FileArtifact
from capstone_mcp.graph_execution import GraphCapture, GraphFailure
from capstone_mcp.graph_report import GraphAnalysisReport, summarize_graph
from capstone_mcp.graph_requests import (
    GraphAnalysisRequest,
    GraphFitOutcome,
    GraphFitRequest,
)
from capstone_mcp.graph_state import FitModel, GraphState
from capstone_mcp.models import Action, Button, Model, Point, Result, Snapshot, Window
from capstone_mcp.plotting import PlotInput, render_plot
from capstone_mcp.repetition import AcquisitionJobs, JobStatus, RepeatPlan
from capstone_mcp.sensor_settings import (
    SamplingRateRequest,
    SensorConfiguration,
    SensorSelection,
    SensorSelectionRequest,
)

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
def capstone_inspect_file(path: str) -> CapConfiguration:
    """Read saved .cap hardware/settings, source metadata, pages and calculations.

    Does not open the file in Capstone or infer live hardware connectivity.
    Array decoding is independent, so unknown recorded storage types do not
    prevent configuration inspection.
    """
    return read_cap_configuration(path)


@MCP.tool()
def capstone_file_datasets(path: str) -> list[CapDatasetSummary]:
    """List decodable saved datasets with source IDs, unit IDs and sample counts.

    Supports type-7 strings and type-0 tagged doubles, with stored, interval,
    or implicit-index independent coordinates.
    Unsupported array encodings raise an error instead of reporting empty data.
    """
    return [
        CapDatasetSummary(
            index=index, dataset_id=dataset.data_set_id,
            source_euid=dataset.source_euid, name=dataset.source_name,
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
) -> Snapshot:
    """Read control names, roles, bounds, and fresh action references."""
    return Snapshot.model_validate(await _native(NativeRequest(
        operation="snapshot", handle=handle, depth=depth, limit=limit,
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
async def capstone_screenshot(handle: int) -> Image:
    """Capture PNG pixels at native resolution; does not raise the window."""
    encoded = TEXT.validate_python(await _native(NativeRequest(
        operation="screenshot", handle=handle,
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


def main() -> None:
    """Serve MCP over stdio; diagnostics must never go to stdout."""
    MCP.run(transport="stdio")


def http_main() -> None:
    """Serve only on loopback for local MCP clients supporting HTTP."""
    MCP.run(transport="streamable-http")


if __name__ == "__main__":
    main()
