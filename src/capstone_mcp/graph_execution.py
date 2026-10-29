# Copyright 2026 Capstone MCP contributors.
"""Native-free screenshot receipts and structured graph execution failures."""

from typing import Final, Literal

from pydantic import Field

from capstone_mcp.models import Bounds, Model

GRAPH_INPUT_OPERATIONS: Final = frozenset({
    "select_graph_measurement", "set_graph_fits", "analyze_graph",
})


class GraphFrame(Model):
    """A worker-issued screenshot receipt, valid for one graph input request."""

    frame_id: str
    handle: int
    bounds: Bounds
    width: int
    height: int


class GraphCapture(Model):
    """Private worker envelope; the server renders the PNG as an image block."""

    frame: GraphFrame
    png_base64: str


class GraphFailure(Model):
    """Observed progress and conservative recovery instructions, never a retry."""

    code: str
    request_id: str = ""
    operation: str
    stage: str
    completed_steps: list[str] = Field(default_factory=list)
    graph_input_may_have_been_sent: bool
    next_action: Literal[
        "observe_graph", "inspect_windows", "read_graph", "reattach_and_inspect",
    ]
    detail: str


class GraphOperationError(RuntimeError):
    """Carry a machine-readable graph failure across the private worker channel."""

    def __init__(self, failure: GraphFailure) -> None:
        """Retain the failure and direct clients to its structured recovery tool."""
        self.failure: GraphFailure = failure
        message = f"{failure.code}: {failure.detail}"
        super().__init__(message + " Call capstone_graph_recovery before retrying.")


class GraphProgress:
    """Track attempted input separately from outcomes verified in Capstone."""

    def __init__(self) -> None:
        """Start with no attempted graph input or confirmed changes."""
        self.stage: str = "inspect_graph"
        self.completed_steps: list[str] = []
        self.input_attempted: bool = False

    def begin_input(self, stage: str) -> None:
        """Record uncertainty before sending input, not after acknowledgement."""
        self.stage = stage
        self.input_attempted = True

    def confirmed(self, stage: str) -> None:
        """Record only steps whose named outcome the caller has verified."""
        self.completed_steps.append(stage)
