# Copyright 2026 Capstone MCP contributors.
"""Read-only integration: requires a running Capstone in the current desktop."""

import base64
import sys
from pathlib import Path
from typing import Final

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import ImageContent
from pydantic import BaseModel

from capstone_mcp.agent_instructions import INSTRUCTIONS
from capstone_mcp.models import Snapshot, Window

ROOT: Final = str(Path(__file__).resolve().parents[1])


class WindowsResult(BaseModel):
    result: list[Window]


class ForegroundDefault(BaseModel):
    default: bool


class InputProperties(BaseModel):
    allow_foreground: ForegroundDefault


class ForegroundSchema(BaseModel):
    properties: InputProperties


async def exercise_protocol() -> None:
    # Given: a real MCP subprocess and the installed, running Capstone.
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "capstone_mcp.server"],
        cwd=ROOT,
    )
    with anyio.fail_after(60):
        async with (
            stdio_client(parameters) as (reader, writer),
            ClientSession(reader, writer) as session,
        ):
            initialized = await session.initialize()
            assert initialized.instructions == INSTRUCTIONS
            tools = await session.list_tools()
            assert len(tools.tools) >= 9
            assert {
                "capstone_fit_models", "capstone_read_graph",
                "capstone_set_graph_fits", "capstone_analyze_graph",
            }.issubset({tool.name for tool in tools.tools})
            input_tools = {
                "capstone_action", "capstone_click", "capstone_drag",
                "capstone_scroll", "capstone_keys", "capstone_type_text",
                "capstone_set_recording", "capstone_step_sampling_rate",
                "capstone_create_graph", "capstone_select_graph_measurement",
                "capstone_read_graph",
            }
            advertised = [tool for tool in tools.tools if tool.name in input_tools]
            assert {tool.name for tool in advertised} == input_tools
            for tool in advertised:
                schema = ForegroundSchema.model_validate(tool.inputSchema)
                assert schema.properties.allow_foreground.default is True
            attached = await session.call_tool("capstone_attach")
            assert not attached.isError
            windows = WindowsResult.model_validate(attached.structuredContent).result
            assert windows
            handle = windows[0].handle
            # When: request actual control state and image via the MCP wire.
            observed = await session.call_tool(
                "capstone_snapshot", {"handle": handle},
            )
            snapshot = Snapshot.model_validate(observed.structuredContent)
            captured = await session.call_tool(
                "capstone_screenshot", {"handle": handle},
            )
            assert not captured.isError, captured.content
            invalid = await session.call_tool(
                "capstone_action", {"ref": "stale:0", "action": "invoke"},
            )
            # Then: real controls, actual PNG data, and stale-ref rejection.
            assert snapshot.controls
            assert snapshot.window.process_id == windows[0].process_id
            images = [c for c in captured.content if isinstance(c, ImageContent)]
            assert len(images) == 1
            assert base64.b64decode(images[0].data).startswith(b"\x89PNG\r\n\x1a\n")
            assert invalid.isError


def test_real_capstone_observation_over_stdio() -> None:
    anyio.run(exercise_protocol)
