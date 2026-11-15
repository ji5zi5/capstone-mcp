# Copyright 2026 Capstone MCP contributors.
"""Stdio MCP entry point for Capstone UI inspection and operation."""

from __future__ import annotations

import json
import re
from contextlib import asynccontextmanager, nullcontext
from typing import TYPE_CHECKING, Any, Final

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

from capstone_mcp.agent_instructions import INSTRUCTIONS
from capstone_mcp.automation_models import NativeRequest
from capstone_mcp.automation_worker import AutomationWorker, NativeSessionError
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
        first_content = res.root.content[0] if res.root.content else None
        raw_text = (
            first_content.text if isinstance(first_content, TextContent) else ""
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
