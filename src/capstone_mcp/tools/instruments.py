# Copyright 2026 Capstone MCP contributors.
"""Tool router for physical and virtual instruments, sensors, and acquisition."""

from collections.abc import Awaitable, Callable
from typing import Any, Final

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, JsonValue, TypeAdapter

from capstone_mcp.automation_models import NativeRequest
from capstone_mcp.instruments import (
    InstrumentAction,
    InstrumentRequest,
    InstrumentResult,
)
from capstone_mcp.repetition import AcquisitionJobs

type NativeCaller = Callable[..., Awaitable[Any]]
JSON_VALUE: Final = TypeAdapter(JsonValue)


def _json_dict(model: BaseModel) -> JsonValue:
    return JSON_VALUE.validate_json(model.model_dump_json())


def register_instrument_tools(
    mcp: FastMCP,
    native: NativeCaller,
    jobs: AcquisitionJobs | Callable[[], AcquisitionJobs] | None = None,
) -> dict[str, Any]:
    """Register all sensor, recording, oscilloscope, and instrument tools."""
    del jobs

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Manage sensors, hardware, and instruments",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def capstone_manage_instrument(
        request: InstrumentRequest,
    ) -> InstrumentResult:
        """Unified compound entry point for all Capstone instrument operations.

        Supported actions (request.action):
        - set_sampling_rate: Navigate sensor rate or select sensor (request.set_sampling_rate)
        - zero_sensor: Zero or tare connected sensors (request.zero_sensor)
        - configure_signal_generator: Configure generator or read status (request.configure_signal_generator)
        - set_recording_condition: Configure start/stop threshold triggers (request.set_recording_condition)
        - set_sampling_mode: Switch sampling mode (continuous, keep_sample) (request.set_sampling_mode)
        - keep_sample: Log discrete point in manual sampling mode (request.keep_sample)
        - scan_wireless: Discover nearby Bluetooth PASCO sensors (request.scan_wireless)
        - connect_wireless: Pair and connect a wireless sensor (request.connect_wireless)
        - calibrate_sensor: Guided 1-point or 2-point sensor calibration (request.calibrate_sensor)
        """
        is_read_only = (
            request.action == InstrumentAction.SCAN_WIRELESS
            or (
                request.action == InstrumentAction.CONFIGURE_SIGNAL_GENERATOR
                and request.configure_signal_generator is not None
                and request.configure_signal_generator.read_only
            )
        )
        return InstrumentResult.model_validate(
            await native(
                NativeRequest(
                    operation="manage_instrument",
                    instrument_request=_json_dict(request),
                ),
                mutates=not is_read_only,
            ),
        )

    return {
        "capstone_manage_instrument": capstone_manage_instrument,
    }

