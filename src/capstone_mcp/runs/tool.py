# Copyright 2026 Capstone MCP contributors.
"""FastMCP tool router for Capstone run management domain."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from mcp.types import ToolAnnotations
from pydantic import JsonValue, TypeAdapter

from capstone_mcp.automation_models import NativeRequest
from capstone_mcp.runs.models import RunRequest, RunResult

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from mcp.server.fastmcp import FastMCP

type NativeCaller = Callable[..., Awaitable[Any]]
JSON_VALUE: Final = TypeAdapter(JsonValue)


def register_run_tools(
    mcp: FastMCP,
    native: NativeCaller,
) -> dict[str, Any]:
    """Register consolidated Run Management tool on FastMCP."""

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Manage experimental runs",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def capstone_manage_run(
        request: RunRequest,
    ) -> RunResult:
        """Unified entry point for experimental run operations.

        Supported actions (request.action):
        - rename: Rename a specific Run in the Data Summary tree (request.rename)
        - delete: Delete a run from Data Summary, auto-confirming modals
          (request.delete)
        - set_visibility: Control visibility (show/hide) of specific runs
          (request.visibility)
        """
        return RunResult.model_validate(
            await native(
                NativeRequest(
                    operation="manage_run",
                    run_request=JSON_VALUE.validate_json(
                        request.model_dump_json(),
                    ),
                ),
                mutates=True,
            ),
        )

    return {
        "capstone_manage_run": capstone_manage_run,
    }
