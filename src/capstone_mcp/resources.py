# Copyright 2026 Capstone MCP contributors.
"""FastMCP dynamic resources for real-time Capstone status and telemetry."""

from __future__ import annotations

import json
import time
from contextlib import suppress
from typing import TYPE_CHECKING, Final

import anyio
import httpx2
from pydantic import JsonValue, TypeAdapter

from capstone_mcp import __version__
from capstone_mcp.agent_instructions import guide
from capstone_mcp.automation_models import NativeRequest
from capstone_mcp.session import UnifiedSessionManager

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Sequence
    from typing import Any

    from mcp.server.fastmcp import FastMCP

    from capstone_mcp.automation_worker import AutomationWorker
    from capstone_mcp.repetition import AcquisitionJobs

JSON_VALUE: Final = TypeAdapter(JsonValue)

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


async def _read_status_doc(
    worker: AutomationWorker,
    jobs: AcquisitionJobs,
    native: Callable[[NativeRequest], Coroutine[Any, Any, JsonValue]],
) -> str:
    windows_json: JsonValue = []
    recording_json: JsonValue = None
    if not worker.retired and worker.process_id:
        with suppress(Exception):
            windows_json = await native(NativeRequest(operation="windows"))
            recording_json = await native(NativeRequest(operation="recording_status"))
    status_doc = {
        "server": "capstone-mcp",
        "version": __version__,
        "attached": not worker.retired and bool(worker.process_id),
        "worker_retired": worker.retired,
        "process_id": worker.process_id,
        "windows_count": len(windows_json) if isinstance(windows_json, list) else 0,
        "active_jobs_count": len(jobs.jobs),
        "windows": windows_json,
        "recording": recording_json,
        "last_graph_failure": (
            worker.last_graph_failure.model_dump()
            if worker.last_graph_failure
            else None
        ),
    }
    return JSON_VALUE.dump_json(status_doc, indent=2).decode("utf-8")


def _read_active_runs_doc(
    worker: AutomationWorker,
    jobs: AcquisitionJobs,
) -> str:
    with jobs.lock:
        entries = list(jobs.jobs.items())
    runs_info = {
        "process_id": worker.process_id,
        "active_jobs": [
            {
                "job_id": jid,
                "state": (
                    job.result.result().state
                    if job.result.done()
                    else "running"
                ),
            }
            for jid, job in entries
        ],
    }
    return json.dumps(runs_info, indent=2)


async def _read_hardware_inventory_doc(
    worker: AutomationWorker,
    native: Callable[[NativeRequest], Coroutine[Any, Any, JsonValue]],
) -> str:
    inventory_doc: dict[str, JsonValue] = {
        "attached": not worker.retired and bool(worker.process_id),
        "process_id": worker.process_id,
        "interfaces": [],
        "sensors": [],
        "wireless_devices": [],
        "recording": None,
        "sampling_rate": None,
    }
    if not worker.retired and worker.process_id:
        with suppress(Exception):
            rec_status = await native(NativeRequest(operation="recording_status"))
            inventory_doc["recording"] = rec_status
            if isinstance(rec_status, dict):
                inventory_doc["sampling_rate"] = rec_status.get("sampling_rate_display")
        with suppress(Exception):
            scan_res = await native(
                NativeRequest(
                    operation="manage_instrument",
                    instrument_request={
                        "action": "scan_wireless",
                        "scan_wireless": {"timeout_seconds": 1.0},
                    },
                ),
            )
            if isinstance(scan_res, dict) and "scan_wireless" in scan_res:
                sw = scan_res["scan_wireless"]
                if isinstance(sw, dict) and "sensors" in sw:
                    inventory_doc["wireless_devices"] = sw["sensors"]
    return JSON_VALUE.dump_json(inventory_doc, indent=2).decode("utf-8")


def _read_live_measurements_doc(worker: AutomationWorker) -> str:
    session_mgr = UnifiedSessionManager(worker)
    doc: dict[str, JsonValue] = {
        "status": "disconnected",
        "process_id": worker.process_id,
        "debug_port": session_mgr.debug_port,
        "timestamp": time.time(),
        "sensors": [],
        "measurements": [],
    }

    try:
        inv = session_mgr.read_live_inventory()
        doc["status"] = "connected"
        doc["sensors"] = inv.sensors
        measurements_data: list[JsonValue] = []
        for m in inv.measurements:
            if isinstance(m, dict):
                euid = str(m.get("MeasurementEUID", ""))
                name = str(m.get("MeasurementName", "Unknown"))
                unit = str(m.get("Unit", ""))
                val_entry: dict[str, JsonValue] = {
                    "euid": euid,
                    "name": name,
                    "unit": unit,
                    "value": None,
                }
                if euid:
                    with suppress(
                        httpx2.HTTPError,
                        RuntimeError,
                        OSError,
                        ValueError,
                        TimeoutError,
                    ):
                        val_entry["value"] = session_mgr.read_live_measurement(euid)
                measurements_data.append(val_entry)
        doc["measurements"] = measurements_data
    except (
        httpx2.HTTPError,
        RuntimeError,
        OSError,
        ValueError,
        TimeoutError,
    ) as exc:
        doc["error"] = str(exc)

    return JSON_VALUE.dump_json(doc, indent=2).decode("utf-8")


async def _read_active_displays_doc(
    worker: AutomationWorker,
    native: Callable[[NativeRequest], Coroutine[Any, Any, JsonValue]],
) -> str:
    displays_doc: dict[str, JsonValue] = {
        "attached": not worker.retired and bool(worker.process_id),
        "process_id": worker.process_id,
        "active_page": None,
        "pages": [],
        "displays": [],
        "table_count": 0,
        "graph_count": 0,
        "digits_count": 0,
        "scope_count": 0,
        "fft_count": 0,
    }
    if not worker.retired and worker.process_id:
        try:
            windows = await native(NativeRequest(operation="windows"))
            if not isinstance(windows, list) or len(windows) != 1:
                displays_doc["error"] = (
                    "Display inspection requires one unambiguous Capstone window."
                )
                return JSON_VALUE.dump_json(displays_doc, indent=2).decode("utf-8")
            window = windows[0]
            handle = window.get("handle") if isinstance(window, dict) else None
            if type(handle) is not int or handle <= 0:
                displays_doc["error"] = "Capstone returned no valid window handle."
                return JSON_VALUE.dump_json(displays_doc, indent=2).decode("utf-8")
            snapshot_res = await native(
                NativeRequest(
                    operation="snapshot",
                    handle=handle,
                    depth=12,
                    limit=5000,
                ),
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
        except Exception as error:  # noqa: BLE001
            displays_doc["error"] = str(error)
    return JSON_VALUE.dump_json(displays_doc, indent=2).decode("utf-8")


def register_resources(
    mcp: FastMCP[None],
    worker: AutomationWorker,
    jobs: AcquisitionJobs,
    native: Callable[[NativeRequest], Coroutine[Any, Any, JsonValue]],
) -> dict[str, Any]:
    """Register all dynamic diagnostic and telemetry resources onto FastMCP."""

    @mcp.resource("capstone://status")
    async def capstone_status_resource() -> str:
        """Return JSON status of the local Capstone application and connection."""
        return await _read_status_doc(worker, jobs, native)

    @mcp.resource("capstone://runs/active")
    async def capstone_active_runs_resource() -> str:
        """Return real-time active runs and experiment metadata from Capstone."""
        return _read_active_runs_doc(worker, jobs)

    @mcp.resource("capstone://hardware/inventory")
    async def capstone_hardware_inventory_resource() -> str:
        """Return real-time hardware status for interfaces, sensors, and devices."""
        return await _read_hardware_inventory_doc(worker, native)

    @mcp.resource("capstone://measurements/live")
    async def capstone_live_measurements_resource() -> str:
        """Return real-time live sensor measurements via CDP WebSocket fast-path."""
        return await anyio.to_thread.run_sync(_read_live_measurements_doc, worker)

    @mcp.resource("capstone://displays/active")
    async def capstone_active_displays_resource() -> str:
        """Return real-time active displays, workbook pages, and container metadata."""
        return await _read_active_displays_doc(worker, native)

    @mcp.resource("capstone://guide")
    def capstone_guide_resource() -> str:
        """Return the complete workflow guidance manual for PASCO Capstone."""
        return guide()

    return {
        "capstone_status_resource": capstone_status_resource,
        "capstone_active_runs_resource": capstone_active_runs_resource,
        "capstone_hardware_inventory_resource": capstone_hardware_inventory_resource,
        "capstone_live_measurements_resource": capstone_live_measurements_resource,
        "capstone_active_displays_resource": capstone_active_displays_resource,
        "capstone_guide_resource": capstone_guide_resource,
    }


__all__ = [
    "register_resources",
]
