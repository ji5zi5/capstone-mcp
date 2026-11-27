# Copyright 2026 Capstone MCP contributors.
"""Stdio protocol integration, with a separate live desktop case."""

import base64
import sys
from pathlib import Path
from typing import Final

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import ImageContent
from pydantic import BaseModel

from capstone_mcp import __version__
from capstone_mcp.agent_instructions import INSTRUCTIONS
from capstone_mcp.analysis import LinearFit
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


async def exercise_protocol(*, process_id: int | None = None) -> None:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "capstone_mcp.server"],
        cwd=ROOT,
        env={"PYTHONPATH": str(Path(ROOT) / "src")},
    )
    with anyio.fail_after(60):
        async with (
            stdio_client(parameters) as (reader, writer),
            ClientSession(reader, writer) as session,
        ):
            initialized = await session.initialize()
            assert initialized.serverInfo.version == __version__
            assert initialized.instructions == INSTRUCTIONS
            tools = await session.list_tools()
            assert len(tools.tools) <= 22
            expected_core = {
                "capstone_attach",
                "capstone_windows",
                "capstone_snapshot",
                "capstone_screenshot",
                "capstone_interact_ui",
                "capstone_manage_graph",
                "capstone_manage_display",
                "capstone_manage_instrument",
                "capstone_manage_run",
            }
            assert expected_core.issubset({tool.name for tool in tools.tools})
            interact_tool = next(t for t in tools.tools if t.name == "capstone_interact_ui")
            schema = ForegroundSchema.model_validate(interact_tool.inputSchema)
            assert schema.properties.allow_foreground.default is False
            if process_id is None:
                invalid_fit = await session.call_tool(
                    "capstone_linear_fit", {"samples": {"x": [0, 1, 2], "y": [1, 3]}},
                )
                assert invalid_fit.isError
                fit = await session.call_tool(
                    "capstone_linear_fit",
                    {"samples": {"x": [0, 1, 2], "y": [1, 3, 5]}},
                )
                assert not fit.isError, fit.content
                assert LinearFit.model_validate(fit.structuredContent).slope == 2.0
                return

            attached = await session.call_tool("capstone_attach", {"process_id": process_id})
            assert not attached.isError, attached.content
            windows = WindowsResult.model_validate(attached.structuredContent).result
            assert windows
            assert all(window.process_id == process_id for window in windows)
            documents = [window for window in windows if ".cap" in window.title.casefold()]
            assert len(documents) == 1, [window.title for window in windows]
            handle = documents[0].handle
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
                "capstone_interact_ui", {
                    "action": "action",
                    "ref": "stale:0",
                    "ui_action": "invoke",
                    "allow_foreground": True,
                },
            )
            # Then: real controls, actual PNG data, and stale-ref rejection.
            assert snapshot.controls
            assert snapshot.window.process_id == process_id
            images = [c for c in captured.content if isinstance(c, ImageContent)]
            assert len(images) == 1
            assert base64.b64decode(images[0].data).startswith(b"\x89PNG\r\n\x1a\n")
            assert invalid.isError


@pytest.mark.anyio
async def test_headless_calls_over_stdio() -> None:
    await exercise_protocol()
