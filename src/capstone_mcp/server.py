# Copyright 2026 Capstone MCP contributors.
"""Stdio MCP entry point for Capstone UI inspection and operation."""

import base64
import json
import re
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager, nullcontext, suppress
from typing import Annotated, Any, Final

import anyio
from mcp.server.fastmcp import FastMCP, Image
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import (
    CallToolRequest,
    CallToolResult,
    ContentBlock,
    ServerResult,
    TextContent,
    ToolAnnotations,
)
from pydantic import Field, JsonValue, TypeAdapter

from capstone_mcp.agent_instructions import INSTRUCTIONS, guide
from capstone_mcp.automation_models import NativeRequest
from capstone_mcp.automation_worker import AutomationWorker, NativeSessionError
from capstone_mcp.models import (
    Action,
    Button,
    Point,
    Result,
    Snapshot,
    ToolErrorPayload,
    Window,
)
from capstone_mcp.repetition import AcquisitionJobs, JobStatus
from capstone_mcp.tools import (
    register_display_tools,
    register_file_tools,
    register_instrument_tools,
    register_physics_tools,
)
from capstone_mcp.tools.files import ExportedData
from capstone_mcp.tutor import (
    get_curriculum,
    list_experiments,
    normalize_experiment_id,
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


async def _native(
    request: NativeRequest,
    *,
    mutates: bool = False,
) -> JsonValue:
    with JOBS.interaction() if mutates else nullcontext():
        if request.operation == "attach" and WORKER.retired:
            await anyio.to_thread.run_sync(WORKER.reset)
        try:
            return await anyio.to_thread.run_sync(WORKER.call, request)
        except NativeSessionError as exc:
            if exc.error_code:
                payload = ToolErrorPayload(
                    error_code=exc.error_code,
                    message=exc.message,
                    remediation=(
                        exc.remediation
                        or "Check Capstone application state using "
                        "capstone_windows and retry."
                    ),
                )
                raise ToolError(payload.model_dump_json(indent=2)) from exc
            raise


MCP: Final = FastMCP(
    "capstone",
    host="127.0.0.1",
    port=8766,
    lifespan=_lifespan,
    instructions=INSTRUCTIONS,
)

# ---------------------------------------------------------------------------
# Core Desktop Interaction Tools
# ---------------------------------------------------------------------------


@MCP.tool(
    annotations=ToolAnnotations(
        title="Attach to installed Capstone",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
async def capstone_attach(
    *,
    launch: bool = False,
    process_id: Annotated[int, Field(gt=0)] | None = None,
) -> list[Window]:
    """Attach to installed Capstone, optionally selecting an exact process ID."""
    return WINDOWS.validate_python(
        await _native(
            NativeRequest(
                operation="attach",
                launch=launch,
                process_id=process_id,
            ),
            mutates=True,
        ),
    )


@MCP.tool(
    annotations=ToolAnnotations(
        title="List Capstone windows",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def capstone_windows() -> list[Window]:
    """List Capstone windows, including file dialogs and modal dialogs."""
    return WINDOWS.validate_python(
        await _native(NativeRequest(operation="windows")),
    )


@MCP.tool(
    annotations=ToolAnnotations(
        title="Inspect window controls and action references",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
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
    return Snapshot.model_validate(
        await _native(
            NativeRequest(
                operation="snapshot",
                handle=handle,
                depth=depth,
                limit=limit,
                query=query,
                control_types=control_types or [],
            ),
        ),
    )


@MCP.tool(
    annotations=ToolAnnotations(
        title="Perform UI action on control",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
async def capstone_action(
    ref: str,
    action: Action,
    *,
    allow_foreground: bool = True,
) -> Result:
    """Activate by click (invoke), or use UIA toggle/select/expand/collapse/focus.

    Foreground input defaults to true. Avoids Capstone's blocking modal
    InvokePattern provider; this is physical input, not background UIA Invoke.
    """
    return Result.model_validate(
        await _native(
            NativeRequest(
                operation="action",
                ref=ref,
                action=action,
                allow_foreground=allow_foreground,
            ),
            mutates=True,
        ),
    )


@MCP.tool(
    annotations=ToolAnnotations(
        title="Read control value pattern text",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def capstone_read_value(ref: str) -> str:
    """Read literal current text from a control's UIA Value pattern."""
    return TEXT.validate_python(
        await _native(
            NativeRequest(
                operation="read_value",
                ref=ref,
            ),
        ),
    )


@MCP.tool(
    annotations=ToolAnnotations(
        title="Set control value pattern text",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def capstone_set_value(ref: str, value: str) -> Result:
    """Set literal text in a control supporting the UIA Value pattern."""
    return Result.model_validate(
        await _native(
            NativeRequest(
                operation="set_value",
                ref=ref,
                value=value,
            ),
            mutates=True,
        ),
    )


@MCP.tool(
    annotations=ToolAnnotations(
        title="Capture window pixels",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def capstone_screenshot(
    handle: int,
    *,
    scale: float = 1.0,
    crop_region: list[int] | None = None,
) -> Image:
    """Capture PNG pixels at native resolution, optionally scaled or cropped.

    Does not raise the target window to the foreground.
    """
    encoded = TEXT.validate_python(
        await _native(
            NativeRequest(
                operation="screenshot",
                handle=handle,
                scale=scale,
                crop_region=crop_region,
            ),
        ),
    )
    return Image(data=base64.b64decode(encoded, validate=True), format="png")


@MCP.tool(
    annotations=ToolAnnotations(
        title="Click window pixels",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
async def capstone_click(
    handle: int,
    point: Point,
    button: Button = Button.LEFT,
    *,
    double: bool = False,
    allow_foreground: bool = True,
) -> Result:
    """Click window-relative pixels; foreground input is enabled by default."""
    return Result.model_validate(
        await _native(
            NativeRequest(
                operation="click",
                handle=handle,
                point=point,
                button=button,
                double=double,
                allow_foreground=allow_foreground,
            ),
            mutates=True,
        ),
    )


@MCP.tool(
    annotations=ToolAnnotations(
        title="Drag between window coordinates",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
async def capstone_drag(
    handle: int,
    start: Point,
    end: Point,
    *,
    allow_foreground: bool = True,
) -> Result:
    """Drag between window-relative pixels; hard timeout leaves outcome uncertain."""
    return Result.model_validate(
        await _native(
            NativeRequest(
                operation="drag",
                handle=handle,
                point=start,
                end=end,
                allow_foreground=allow_foreground,
            ),
            mutates=True,
        ),
    )


@MCP.tool(
    annotations=ToolAnnotations(
        title="Scroll at window coordinates",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
async def capstone_scroll(
    handle: int,
    point: Point,
    notches: Annotated[int, Field(ge=-100, le=100)],
    *,
    allow_foreground: bool = True,
) -> Result:
    """Scroll at window-relative pixels; positive notches scroll upward."""
    return Result.model_validate(
        await _native(
            NativeRequest(
                operation="scroll",
                handle=handle,
                point=point,
                notches=notches,
                allow_foreground=allow_foreground,
            ),
            mutates=True,
        ),
    )


@MCP.tool(
    annotations=ToolAnnotations(
        title="Send pywinauto keyboard shortcuts",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
async def capstone_keys(
    handle: int,
    keys: str,
    *,
    allow_foreground: bool = True,
) -> Result:
    """Send pywinauto key syntax: ^o, {ESC}, {ENTER}, %{F4}. Changes focus."""
    return Result.model_validate(
        await _native(
            NativeRequest(
                operation="keys",
                handle=handle,
                value=keys,
                allow_foreground=allow_foreground,
            ),
            mutates=True,
        ),
    )


@MCP.tool(
    annotations=ToolAnnotations(
        title="Type literal text into focused control",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
async def capstone_type_text(
    handle: int,
    text: str,
    *,
    allow_foreground: bool = True,
) -> Result:
    """Type literal Unicode text in the focused field, escaping shortcut syntax."""
    escaped = "".join(
        "{" + char + "}" if char in "+^%~(){}" else char for char in text
    )
    return Result.model_validate(
        await _native(
            NativeRequest(
                operation="keys",
                handle=handle,
                value=escaped,
                allow_foreground=allow_foreground,
                unicode_input=True,
            ),
            mutates=True,
        ),
    )


# ---------------------------------------------------------------------------
# Domain Tool Router Registrations
# ---------------------------------------------------------------------------

register_file_tools(MCP, _native)
register_display_tools(
    MCP,
    _native,
    get_last_failure=lambda: WORKER.last_graph_failure,
)
_instrument_tools = register_instrument_tools(MCP, _native, jobs=lambda: JOBS)
_physics_tools = register_physics_tools(MCP, _native)


# Backward-compatibility exports for test callers
def capstone_acquisition_job(job_id: str) -> JobStatus:
    """Read a repeat job's completion and confirmed-cycle receipts."""
    return JOBS.status(job_id)


def capstone_cancel_acquisition(job_id: str) -> JobStatus:
    """Request cancellation; completion requires the worker to stop recording."""
    return JOBS.cancel(job_id)


capstone_run_experiment_macro = _physics_tools["capstone_run_experiment_macro"]
capstone_generate_lab_report = _physics_tools["capstone_generate_lab_report"]
capstone_tutor_get_lesson = _physics_tools["capstone_tutor_get_lesson"]
capstone_tutor_guide_step = _physics_tools["capstone_tutor_guide_step"]

# ---------------------------------------------------------------------------
# MCP Resources
# ---------------------------------------------------------------------------


@MCP.resource("capstone://status")
async def capstone_status_resource() -> str:
    """Return JSON status of the local Capstone application and connection."""
    windows_json: JsonValue = []
    recording_json: JsonValue = None
    if not WORKER.retired and WORKER.process_id:
        with suppress(Exception):
            windows_json = await _native(
                NativeRequest(operation="windows"), mutates=False,
            )
            recording_json = await _native(
                NativeRequest(operation="recording_status"),
                mutates=False,
            )
    status_doc = {
        "server": "capstone-mcp",
        "version": "0.1.0",
        "attached": not WORKER.retired and bool(WORKER.process_id),
        "worker_retired": WORKER.retired,
        "process_id": WORKER.process_id,
        "windows_count": len(windows_json) if isinstance(windows_json, list) else 0,
        "active_jobs_count": len(JOBS.jobs),
        "windows": windows_json,
        "recording": recording_json,
        "last_graph_failure": (
            WORKER.last_graph_failure.model_dump()
            if WORKER.last_graph_failure
            else None
        ),
    }
    return JSON_VALUE.dump_json(status_doc, indent=2).decode("utf-8")


@MCP.resource("capstone://runs/active")
async def capstone_active_runs_resource() -> str:
    """Return real-time active runs and experiment metadata from Capstone."""
    runs_info = {
        "process_id": WORKER.process_id,
        "active_jobs": [
            {"job_id": jid, "state": job.observe().text}
            for jid, job in JOBS.jobs.items()
        ],
    }
    return json.dumps(runs_info, indent=2)


@MCP.resource("capstone://hardware/inventory")
async def capstone_hardware_inventory_resource() -> str:
    """Return real-time hardware status for interfaces, sensors, and devices."""
    inventory_doc: dict[str, JsonValue] = {
        "attached": not WORKER.retired and bool(WORKER.process_id),
        "process_id": WORKER.process_id,
        "interfaces": [],
        "sensors": [],
        "wireless_devices": [],
        "recording": None,
        "sampling_rate": None,
    }
    if not WORKER.retired and WORKER.process_id:
        with suppress(Exception):
            rec_status = await _native(
                NativeRequest(operation="recording_status"),
                mutates=False,
            )
            inventory_doc["recording"] = rec_status
            if isinstance(rec_status, dict):
                inventory_doc["sampling_rate"] = rec_status.get(
                    "sampling_rate_display",
                )
        with suppress(Exception):
            scan_res = await _native(
                NativeRequest(
                    operation="manage_instrument",
                    instrument_request={
                        "action": "scan_wireless",
                        "scan_wireless": {"timeout_seconds": 1.0},
                    },
                ),
                mutates=False,
            )
            if isinstance(scan_res, dict) and "scan_wireless" in scan_res:
                sw = scan_res["scan_wireless"]
                if isinstance(sw, dict) and "sensors" in sw:
                    inventory_doc["wireless_devices"] = sw["sensors"]
    return JSON_VALUE.dump_json(inventory_doc, indent=2).decode("utf-8")


_DISPLAY_KIND_MAP: Final = (
    ("table", "table_count"),
    ("graph", "graph_count"),
    ("digits", "digits_count"),
    ("scope", "scope_count"),
    ("oscilloscope", "scope_count"),
    ("fft", "fft_count"),
)


def _tally_display_controls(
    controls: Sequence[object],
    displays_doc: dict[str, JsonValue],
) -> None:
    pages_list = displays_doc["pages"]
    displays_list = displays_doc.get("displays")
    if not isinstance(pages_list, list):
        return
    for c in controls:
        if not isinstance(c, dict):
            continue
        aid = str(c.get("automation_id", "")).lower()
        name = str(c.get("name", ""))
        name_lower = name.lower()
        ctype = str(c.get("control_type", "")).lower()
        if ("tabitem" in ctype or "page" in aid) and name and name not in pages_list:
            pages_list.append(name)
        for keyword, count_field in _DISPLAY_KIND_MAP:
            if keyword in aid or keyword in name_lower:
                val = displays_doc.get(count_field, 0)
                displays_doc[count_field] = (val if isinstance(val, int) else 0) + 1
                if isinstance(displays_list, list):
                    norm_kind = "scope" if keyword == "oscilloscope" else keyword
                    displays_list.append(
                        {
                            "kind": norm_kind,
                            "name": name or aid,
                            "automation_id": str(c.get("automation_id", "")),
                        },
                    )
                break


@MCP.resource("capstone://displays/active")
async def capstone_active_displays_resource() -> str:
    """Return real-time active displays, workbook pages, and container metadata."""
    displays_doc: dict[str, JsonValue] = {
        "attached": not WORKER.retired and bool(WORKER.process_id),
        "process_id": WORKER.process_id,
        "active_page": None,
        "pages": [],
        "displays": [],
        "table_count": 0,
        "graph_count": 0,
        "digits_count": 0,
        "scope_count": 0,
        "fft_count": 0,
    }
    if not WORKER.retired and WORKER.process_id:
        with suppress(Exception):
            snapshot_res = await _native(
                NativeRequest(
                    operation="snapshot",
                    handle=0,
                    depth=12,
                    limit=5000,
                ),
                mutates=False,
            )
            controls: Sequence[object] = ()
            if isinstance(snapshot_res, dict):
                raw_ctrls = snapshot_res.get("controls")
                if isinstance(raw_ctrls, list):
                    controls = raw_ctrls
            elif isinstance(snapshot_res, list):
                controls = snapshot_res

            _tally_display_controls(controls, displays_doc)

            if displays_doc["pages"] and isinstance(displays_doc["pages"], list):
                displays_doc["active_page"] = displays_doc["pages"][0]
    return JSON_VALUE.dump_json(displays_doc, indent=2).decode("utf-8")


@MCP.resource("capstone://guide")
def capstone_guide_resource() -> str:
    """Return the complete workflow guidance manual for PASCO Capstone."""
    return guide()


@MCP.resource("capstone://tutor/lessons")
def capstone_tutor_lessons_resource() -> str:
    """Return JSON catalog of all available pedagogical physics experiment lessons."""
    catalog = [
        {
            "experiment_id": exp.experiment_id,
            "title": exp.title,
            "domain": exp.domain,
            "theory_summary": exp.theory_summary,
            "governing_equations": exp.governing_equations,
            "equipment": exp.equipment,
            "total_steps": len(exp.steps),
            "total_quiz_questions": len(exp.quiz_questions),
            "reference_file": exp.reference_file,
            "lesson_file": f"./lessons/{exp.reference_file}",
        }
        for exp in list_experiments()
    ]
    return json.dumps(catalog, indent=2)


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


@MCP.prompt()
def physics_lab_tutor(
    experiment_id: str = "photoelectric_effect",
    step_index: int = 1,
) -> str:
    """Pedagogical tutor prompt to guide students through physics lab experiments."""
    curr = get_curriculum(normalize_experiment_id(experiment_id))
    step = next(
        (s for s in curr.steps if s.step_index == step_index),
        curr.steps[0] if curr.steps else None,
    )
    step_text = ""
    if step:
        step_text = (
            f"\n\nCurrent Target Step ({step.step_index}/{len(curr.steps)}): "
            f"{step.title}\n"
            f"- Targeted Instructions: {step.instructions}\n"
            f"- Safety Warnings: {step.safety_notes}\n"
            f"- Capstone Action: {step.capstone_action}\n"
            f"- Validation Check: {step.validation_check}"
        )
    return (
        f"You are the PASCO Capstone Physics Lab Tutor for '{curr.title}' "
        f"({curr.domain}).\n"
        f"Theory Summary:\n{curr.theory_summary}\n\n"
        "Governing Equations:\n"
        + "\n".join(f"- {eq}" for eq in curr.governing_equations)
        + "\n\n"
        "Required Equipment:\n"
        + "\n".join(f"- {eq}" for eq in curr.equipment)
        + step_text
        + "\n\n"
        "Guide the student interactively: explain the physical intuition, ensure "
        "laboratory safety, verify Capstone sensor/display configurations, and test "
        "conceptual understanding with quiz questions."
    )


@MCP.prompt()
def data_analysis_workflow(
    experiment_name: str = "generic",
    fit_model: str = "Linear",
) -> str:
    """Guided prompt template for automated physics curve fitting and lab analysis."""
    return (
        f"Please execute a structured data analysis workflow for '{experiment_name}' "
        "in PASCO Capstone:\n"
        "1. Inspect active displays and windows using capstone_windows and "
        "capstone_snapshot.\n"
        "2. Observe and read the primary graph display using "
        "capstone_manage_graph(action='read').\n"
        f"3. Apply a '{fit_model}' curve fit to the active data series using "
        f"capstone_manage_graph(action='fit', fit_type='{fit_model}').\n"
        "4. Extract fit parameters (slope, intercept, r_squared, etc.) and calculate "
        "residuals or theoretical percentage error.\n"
        "5. Compile the final experimental findings into a structured lab report with "
        "capstone_generate_lab_report."
    )


@MCP.prompt()
def display_layout_workflow(
    page_title: str = "New Analysis",
    layout: str = "two_vertical",
    target_measurements: str = "Time, Position",
) -> str:
    """Guided prompt template for workbook page creation and multi-display layout."""
    return (
        f"Please execute a workbook display layout workflow for '{page_title}' "
        "in PASCO Capstone:\n"
        "1. Check existing workbook pages and display widgets via the "
        "capstone://displays/active resource.\n"
        f"2. Add a new workbook page tab titled '{page_title}' using "
        f"capstone_manage_display(action='add_page', title='{page_title}').\n"
        f"3. Apply the desired grid split layout template '{layout}' using "
        f"capstone_manage_display(action='set_page_layout', layout='{layout}').\n"
        "4. Insert appropriate display widgets into layout placeholders: "
        "use capstone_manage_display with 'create_digits', 'create_table', "
        "'create_scope', or 'create_fft' (or capstone_manage_graph for graphs).\n"
        f"5. Bind target measurements ({target_measurements}) to display axes, "
        "columns, or readout channels.\n"
        "6. Verify the active display layout visually or via capstone_snapshot."
    )


@MCP.prompt()
def run_comparison_workflow(
    run1: str = "Run #1",
    run2: str = "Run #2",
) -> str:
    """Guided prompt template for multi-run comparison and percentage analysis."""
    return (
        "Please execute a multi-run comparison workflow in PASCO Capstone:\n"
        f"1. Verify recorded experimental runs ({run1}, {run2}) via the "
        "capstone://runs/active resource.\n"
        f"2. Inspect the summary statistics for both {run1} and {run2} using "
        "capstone_manage_graph(action='toolbox_statistics').\n"
        f"3. Compare key metric parameters (mean, standard deviation, peak values) "
        f"between {run1} and {run2}.\n"
        "4. Calculate percentage difference and evaluate experimental reproducibility "
        "or trendlines.\n"
        "5. Present a comparative Markdown table summarizing the differences and "
        "scientific conclusions."
    )


@MCP.prompt()
def hardware_setup_workflow(
    interface_type: str = "850 Universal Interface",
    target_sensor: str = "Force Sensor",
    sampling_rate: str = "100 Hz",
) -> str:
    """Guided prompt template for hardware setup, sensor zeroing, and calibration."""
    return (
        f"Please execute a hardware setup workflow for '{target_sensor}' "
        f"on '{interface_type}' in PASCO Capstone:\n"
        "1. Check hardware status and connected interfaces via the "
        "capstone://hardware/inventory resource.\n"
        "2. If using wireless sensors, scan and connect using "
        "capstone_manage_instrument(action='scan_wireless') and "
        "capstone_manage_instrument(action='connect_wireless', sensor_name=...).\n"
        f"3. Select sensor and configure sampling rate to '{sampling_rate}' using "
        f"capstone_manage_instrument(action='set_sampling_rate', "
        f"sensor_name='{target_sensor}', sampling_rate='{sampling_rate}').\n"
        "4. Zero or tare the sensor prior to data acquisition using "
        f"capstone_manage_instrument(action='zero_sensor', "
        f"sensor_name='{target_sensor}').\n"
        "5. If a signal generator is required, configure waveform and frequency using "
        "capstone_manage_instrument(action='set_signal_generator', ...).\n"
        "6. Confirm live sensor values and readiness using "
        "capstone_manage_instrument(action='read_signal_generator') or "
        "capstone_snapshot."
    )


# ---------------------------------------------------------------------------
# Structured MCP Protocol Error Envelopes
# ---------------------------------------------------------------------------

_FALLBACK_ERROR_RULES: Final[tuple[tuple[tuple[str, ...], str, str], ...]] = (
    (
        ("attach", "session"),
        "SESSION_NOT_ATTACHED",
        "Call capstone_attach(launch=True) to attach to or launch PASCO Capstone.",
    ),
    (
        ("graph",),
        "GRAPH_OPERATION_ERROR",
        (
            "Verify graph display exists using capstone_manage_graph(action='read') "
            "or snapshot."
        ),
    ),
    (
        (
            "display",
            "digits",
            "table",
            "scope",
            "fft",
            "page",
            "layout",
            "workbook",
        ),
        "DISPLAY_ERROR",
        (
            "Verify display widget container and workbook layout via "
            "capstone://displays/active or reconfigure using capstone_manage_display."
        ),
    ),
    (
        ("sensor", "instrument", "generator", "calibration", "hardware"),
        "INSTRUMENT_ERROR",
        (
            "Verify hardware connection via capstone://hardware/inventory or "
            "check sensor configuration using capstone_manage_instrument."
        ),
    ),
    (
        ("file", "path"),
        "FILE_NOT_FOUND",
        "Verify the target file path exists and is accessible.",
    ),
    (
        ("invalid", "validation", "unsupported"),
        "INVALID_ARGUMENT",
        (
            "Check tool argument types, values, and schema constraints before "
            "retrying."
        ),
    ),
    (
        ("time",),
        "TIMEOUT_ERROR",
        (
            "Operation timed out; inspect Capstone responsiveness and reattach "
            "if needed."
        ),
    ),
)


def _classify_error_text(cleaned: str) -> tuple[str, str]:
    lower = cleaned.lower()
    if "control" in lower and ("not found" in lower or "missing" in lower):
        return (
            "CONTROL_NOT_FOUND",
            (
                "Inspect active window controls using capstone_snapshot to find "
                "valid references."
            ),
        )

    for keywords, code, remediation in _FALLBACK_ERROR_RULES:
        if any(kw in lower for kw in keywords):
            return code, remediation
    return (
        "AUTOMATION_ERROR",
        "Check Capstone application state using capstone_windows and retry.",
    )


def format_tool_error(error_message: Exception | str) -> ToolErrorPayload:
    """Classify and format an error string into a structured ToolErrorPayload."""
    if isinstance(error_message, NativeSessionError) and error_message.error_code:
        return ToolErrorPayload(
            error_code=error_message.error_code,
            message=error_message.message,
            remediation=error_message.remediation
            or "Check Capstone application state using capstone_windows and retry.",
        )
    msg_str = str(error_message)
    cleaned = re.sub(r"^Error executing tool \w+:\s*", "", msg_str).strip()
    with suppress(json.JSONDecodeError, KeyError, TypeError):
        data = json.loads(cleaned)
        if (
            isinstance(data, dict)
            and "error_code" in data
            and "message" in data
            and "remediation" in data
        ):
            return ToolErrorPayload(
                error_code=str(data["error_code"]),
                message=str(data["message"]),
                remediation=str(data["remediation"]),
            )

    code, remediation = _classify_error_text(cleaned)
    return ToolErrorPayload(
        error_code=code,
        message=cleaned,
        remediation=remediation,
    )


_orig_call_tool_handler = MCP._mcp_server.request_handlers[CallToolRequest]  # noqa: SLF001


async def _structured_call_tool_handler(req: CallToolRequest) -> ServerResult:
    res = await _orig_call_tool_handler(req)
    if isinstance(res, ServerResult) and res.root.isError:
        raw_text = (
            res.root.content[0].text
            if res.root.content and hasattr(res.root.content[0], "text")
            else ""
        )
        payload = format_tool_error(raw_text)
        return ServerResult(
            CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=payload.model_dump_json(indent=2),
                    ),
                ],
                isError=True,
            ),
        )
    return res


MCP._mcp_server.request_handlers[CallToolRequest] = _structured_call_tool_handler  # noqa: SLF001

_orig_fastmcp_call_tool = MCP.call_tool


async def _safe_fastmcp_call_tool(
    name: str,
    arguments: dict[str, Any],
) -> Sequence[ContentBlock] | dict[str, Any]:
    try:
        return await _orig_fastmcp_call_tool(name, arguments)
    except Exception as exc:
        payload = format_tool_error(exc)
        raise ToolError(payload.model_dump_json(indent=2)) from exc


MCP.call_tool = _safe_fastmcp_call_tool



def main() -> None:
    """Serve MCP over stdio; diagnostics must never go to stdout."""
    MCP.run(transport="stdio")


def http_main() -> None:
    """Serve only on loopback for local MCP clients supporting HTTP."""
    MCP.run(transport="streamable-http")


if __name__ == "__main__":
    main()

__all__ = [
    "MCP",
    "ExportedData",
    "ToolErrorPayload",
    "capstone_acquisition_job",
    "capstone_active_displays_resource",
    "capstone_cancel_acquisition",
    "capstone_generate_lab_report",
    "capstone_hardware_inventory_resource",
    "capstone_run_experiment_macro",
    "capstone_tutor_get_lesson",
    "capstone_tutor_guide_step",
    "capstone_tutor_lessons_resource",
    "data_analysis_workflow",
    "display_layout_workflow",
    "format_tool_error",
    "hardware_setup_workflow",
    "http_main",
    "main",
    "physics_lab_tutor",
    "run_comparison_workflow",
]

