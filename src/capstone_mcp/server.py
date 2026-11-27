# Copyright 2026 Capstone MCP contributors.
"""Stdio MCP entry point for Capstone UI inspection and operation."""

from __future__ import annotations

import argparse
import json
import re
from contextlib import asynccontextmanager, nullcontext
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, Final, override

import anyio
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import (
    CallToolRequest,
    CallToolResult,
    ServerResult,
    TextContent,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Sequence

    from mcp.types import ContentBlock
    from pydantic import JsonValue
    from starlette.applications import Starlette

from capstone_mcp import __version__, bridge
from capstone_mcp.agent_instructions import INSTRUCTIONS
from capstone_mcp.automation_models import NativeRequest
from capstone_mcp.automation_worker import AutomationWorker, NativeSessionError
from capstone_mcp.desktop import AutomationError
from capstone_mcp.instruments.models import InstrumentRequest
from capstone_mcp.models import ToolErrorPayload
from capstone_mcp.prompts import (
    collision_impulse_experiment,
    data_analysis_workflow,
    display_layout_workflow,
    hardware_setup_workflow,
    register_prompts,
    resonance_experiment_workflow,
    run_comparison_workflow,
    sensor_calibration_workflow,
    titration_keep_sample_workflow,
)
from capstone_mcp.repetition import AcquisitionJobs, JobStatus
from capstone_mcp.resources import register_resources
from capstone_mcp.runs import register_run_tools
from capstone_mcp.tools import (
    register_display_tools,
    register_file_tools,
    register_instrument_tools,
    register_physics_tools,
    register_ui_tools,
)
from capstone_mcp.tools.files import ExportedData

WORKER: Final = AutomationWorker()
JOBS: Final = AcquisitionJobs()
_APP_LIFESPAN_ACTIVE: Final = ContextVar("capstone_app_lifespan_active", default=False)


@asynccontextmanager
async def _lifespan(_server: FastMCP[None]) -> AsyncGenerator[None, None]:
    if _APP_LIFESPAN_ACTIVE.get():
        # HTTP sessions borrow resources owned by the outer ASGI lifespan.
        yield
        return
    token = _APP_LIFESPAN_ACTIVE.set(True)
    try:
        yield
    finally:
        try:
            with anyio.CancelScope(shield=True):
                try:
                    await anyio.to_thread.run_sync(JOBS.close)
                finally:
                    try:
                        await anyio.to_thread.run_sync(WORKER.close)
                    finally:
                        await anyio.to_thread.run_sync(bridge.close_connections)
        finally:
            _APP_LIFESPAN_ACTIVE.reset(token)


async def _native(
    request: NativeRequest,
    *,
    mutates: bool = False,
) -> JsonValue:
    manual = (
        mutates and request.operation == "manage_instrument"
        and isinstance(request.instrument_request, dict)
        and request.instrument_request.get("action") == "keep_sample"
    )
    admission = (
        JOBS.manual_sample() if manual
        else JOBS.interaction() if mutates else nullcontext()
    )
    with admission as recording_owner:
        try:
            if manual and recording_owner is not None:
                instrument = InstrumentRequest.model_validate(
                    request.instrument_request,
                )
                sample = instrument.keep_sample
                if sample is None or sample.handle not in {0, recording_owner.handle}:
                    msg = "Keep Sample must target the active recording window."
                    raise AutomationError(msg)
                instrument = instrument.model_copy(update={
                    "keep_sample": sample.model_copy(update={
                        "handle": recording_owner.handle,
                    }),
                })
                routed = request.model_copy(update={
                    "instrument_request": instrument.model_dump(mode="json"),
                })
                return await anyio.to_thread.run_sync(
                    recording_owner.keep_sample, routed,
                )
            if request.operation == "attach" and WORKER.retired:
                await anyio.to_thread.run_sync(WORKER.reset)
            return await anyio.to_thread.run_sync(WORKER.call, request)
        except NativeSessionError as exc:
            payload = format_tool_error(exc)
            raise ToolError(payload.model_dump_json(indent=2)) from exc


class CapstoneMCP(FastMCP[None]):
    """Keep shared runtime resources alive until the HTTP application shuts down."""

    @override
    def streamable_http_app(self) -> Starlette:
        """Wrap the SDK session manager's lifetime with application ownership."""
        app = super().streamable_http_app()
        original_lifespan = app.router.lifespan_context

        @asynccontextmanager
        async def app_lifespan(application: Starlette) -> AsyncGenerator[Any, None]:
            async with _lifespan(self), original_lifespan(application) as state:
                yield state

        app.router.lifespan_context = app_lifespan
        return app


MCP: Final = CapstoneMCP(
    "capstone",
    host="127.0.0.1",
    port=8766,
    lifespan=_lifespan,
    instructions=INSTRUCTIONS,
)
# FastMCP otherwise advertises the SDK distribution's version during initialize.
MCP._mcp_server.version = __version__  # noqa: SLF001

# ---------------------------------------------------------------------------
# Tool & Resource Router Registrations
# ---------------------------------------------------------------------------


async def _native_dispatch(
    request: NativeRequest,
    *,
    mutates: bool = False,
) -> JsonValue:
    return await _native(request, mutates=mutates)


_ui_tools = register_ui_tools(MCP, _native_dispatch)
register_file_tools(MCP, _native_dispatch)
register_display_tools(
    MCP,
    _native_dispatch,
    get_last_failure=lambda: WORKER.last_graph_failure,
)
_instrument_tools = register_instrument_tools(MCP, _native_dispatch, jobs=lambda: JOBS)
_physics_tools = register_physics_tools(MCP, _native_dispatch)
_run_tools = register_run_tools(MCP, _native_dispatch)

_resources = register_resources(MCP, WORKER, JOBS, _native_dispatch)
register_prompts(MCP)

# ---------------------------------------------------------------------------
# Backward-compatibility exports
# ---------------------------------------------------------------------------

capstone_attach = _ui_tools["capstone_attach"]
capstone_windows = _ui_tools["capstone_windows"]
capstone_snapshot = _ui_tools["capstone_snapshot"]
capstone_screenshot = _ui_tools["capstone_screenshot"]
capstone_interact_ui = _ui_tools["capstone_interact_ui"]

capstone_status_resource = _resources["capstone_status_resource"]
capstone_active_runs_resource = _resources["capstone_active_runs_resource"]
capstone_hardware_inventory_resource = _resources[
    "capstone_hardware_inventory_resource"
]
capstone_live_measurements_resource = _resources["capstone_live_measurements_resource"]
capstone_active_displays_resource = _resources["capstone_active_displays_resource"]
capstone_guide_resource = _resources["capstone_guide_resource"]


def capstone_acquisition_job(job_id: str) -> JobStatus:
    """Read a repeat job's completion and confirmed-cycle receipts."""
    return JOBS.status(job_id)


def capstone_cancel_acquisition(job_id: str) -> JobStatus:
    """Request cancellation; completion requires the worker to stop recording."""
    return JOBS.cancel(job_id)


capstone_run_experiment_macro = _physics_tools["capstone_run_experiment_macro"]
capstone_generate_lab_report = _physics_tools["capstone_generate_lab_report"]
capstone_manage_run = _run_tools["capstone_manage_run"]

# ---------------------------------------------------------------------------
# Structured MCP Protocol Error Envelopes
# ---------------------------------------------------------------------------

_FALLBACK_ERROR_RULES: Final[tuple[tuple[tuple[str, ...], str, str], ...]] = (
    (
        ("timed out", "timeout", "deadline exceeded", "time exceeded"),
        "TIMEOUT_ERROR",
        "Operation timed out; inspect Capstone responsiveness and reattach if needed.",
    ),
    (
        ("validation error", "input validation"),
        "INVALID_ARGUMENT",
        "Check tool argument types, values, and schema constraints before retrying.",
    ),
    (
        (
            "capstone_attach", "attach to capstone", "not attached",
            "no running capstone",
        ),
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
        ("no such file", "file not found", "path does not exist"),
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
)


def _classify_error_text(cleaned: str) -> tuple[str, str]:
    lower = cleaned.lower()
    if ("file" in lower or "path" in lower) and "not found" in lower:
        return "FILE_NOT_FOUND", "Verify the target file path exists and is accessible."
    if "control" in lower and ("not found" in lower or "missing" in lower):
        return (
            "CONTROL_NOT_FOUND",
            (
                "Inspect active window controls using capstone_snapshot to find "
                "valid references."
            ),
        )

    for keywords, code, remediation in _FALLBACK_ERROR_RULES:
        if any(re.search(r"\b" + re.escape(kw) + r"\b", lower) for kw in keywords):
            return code, remediation
    return (
        "AUTOMATION_ERROR",
        "Check Capstone application state using capstone_windows and retry.",
    )


def format_tool_error(error_message: Exception | str) -> ToolErrorPayload:
    """Classify and format an error string into a structured ToolErrorPayload."""
    if isinstance(error_message, NativeSessionError):
        code, remediation = _classify_error_text(error_message.message)
        return ToolErrorPayload(
            error_code=error_message.error_code or code,
            message=error_message.message,
            remediation=error_message.remediation or remediation,
        )
    if isinstance(error_message, TimeoutError):
        return ToolErrorPayload(
            error_code="TIMEOUT_ERROR", message=str(error_message),
            remediation=(
                "Inspect Capstone responsiveness before retrying "
                "the timed out operation."
            ),
        )
    msg_str = str(error_message)
    cleaned = re.sub(r"^Error executing tool \w+:\s*", "", msg_str).strip()
    try:
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
    except (json.JSONDecodeError, KeyError, TypeError):
        pass

    code, remediation = _classify_error_text(cleaned)
    return ToolErrorPayload(
        error_code=code,
        message=cleaned,
        remediation=remediation,
    )


_orig_call_tool_handler = MCP._mcp_server.request_handlers[CallToolRequest]  # noqa: SLF001


async def _structured_call_tool_handler(req: CallToolRequest) -> ServerResult:
    res = await _orig_call_tool_handler(req)
    if (
        isinstance(res, ServerResult)
        and isinstance(res.root, CallToolResult)
        and res.root.isError
    ):
        first_content = next(
            (item for item in res.root.content if isinstance(item, TextContent)), None,
        )
        raw_text = (
            first_content.text if isinstance(first_content, TextContent) else ""
        )
        payload = format_tool_error(raw_text)
        structured = TextContent(type="text", text=payload.model_dump_json(indent=2))
        content = [
            structured if item is first_content else item for item in res.root.content
        ]
        if first_content is None:
            content.insert(0, structured)
        return ServerResult(res.root.model_copy(update={"content": content}))
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


def _parser(program: str, description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=program, description=description)
    _ = parser.add_argument("--version", action="version", version=__version__)
    return parser


def main() -> None:
    """Serve MCP over stdio; diagnostics must never go to stdout."""
    _ = _parser("capstone-mcp", "Serve PASCO Capstone MCP over stdio.").parse_args()
    MCP.run(transport="stdio")


def http_main() -> None:
    """Serve only on loopback for local MCP clients supporting HTTP."""
    parser = _parser("capstone-mcp-http", "Serve PASCO Capstone MCP on loopback.")
    _ = parser.add_argument("--port", type=int, default=MCP.settings.port,
                            help="Local listening port (default: %(default)s)")
    port = parser.parse_args().port
    if not 1 <= port <= 65_535:  # noqa: PLR2004
        parser.error("--port must be between 1 and 65535")
    MCP.settings.port = port
    MCP.run(transport="streamable-http")


if __name__ == "__main__":
    main()

__all__ = [
    "MCP",
    "ExportedData",
    "NativeRequest",
    "ToolErrorPayload",
    "capstone_acquisition_job",
    "capstone_active_displays_resource",
    "capstone_active_runs_resource",
    "capstone_attach",
    "capstone_cancel_acquisition",
    "capstone_generate_lab_report",
    "capstone_guide_resource",
    "capstone_hardware_inventory_resource",
    "capstone_interact_ui",
    "capstone_live_measurements_resource",
    "capstone_manage_run",
    "capstone_run_experiment_macro",
    "capstone_screenshot",
    "capstone_snapshot",
    "capstone_status_resource",
    "capstone_windows",
    "collision_impulse_experiment",
    "data_analysis_workflow",
    "display_layout_workflow",
    "format_tool_error",
    "hardware_setup_workflow",
    "http_main",
    "main",
    "resonance_experiment_workflow",
    "run_comparison_workflow",
    "sensor_calibration_workflow",
    "titration_keep_sample_workflow",
]
