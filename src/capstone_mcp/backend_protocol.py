# Copyright 2026 Capstone MCP contributors.
"""Formal abstract protocol for Capstone automation backends."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pydantic import JsonValue

    from capstone_mcp.automation_models import NativeRequest
    from capstone_mcp.displays.models import DisplayRequest, DisplayResult
    from capstone_mcp.graphs.models import GraphRequest, GraphResult
    from capstone_mcp.instruments.models import InstrumentRequest, InstrumentResult
    from capstone_mcp.models import Action, Result, Snapshot, Window
    from capstone_mcp.runs.models import RunRequest, RunResult


@runtime_checkable
class ICapstoneBackend(Protocol):
    """Unified abstraction contract implemented by DesktopBackend and FakeBackend."""

    @property
    def process_id(self) -> int | None:
        """Return the running process ID or None if detached."""
        ...

    def attach(
        self,
        *,
        launch: bool = False,
        process_id: int | None = None,
    ) -> list[Window]:
        """Attach to or launch a Capstone process."""
        ...

    def windows(self) -> list[Window]:
        """List current top-level and modal windows."""
        ...

    def snapshot(
        self,
        handle: int,
        depth: int = 12,
        limit: int = 200,
        *,
        query: str | None = None,
        control_types: list[str] | None = None,
    ) -> Snapshot:
        """Capture the control hierarchy for a window."""
        ...

    def act(
        self,
        ref: str,
        action: Action,
        *,
        allow_foreground: bool = True,
    ) -> Result:
        """Perform a UI action on a control."""
        ...

    def click(
        self,
        handle: int,
        ref: str,
        *,
        allow_foreground: bool = True,
    ) -> Result:
        """Click a control reference."""
        ...

    def type_text(self, text: str) -> None:
        """Send keystrokes to the focused control."""
        ...

    def screenshot(
        self,
        handle: int,
        *,
        scale: float = 1.0,
        crop_region: list[int] | None = None,
    ) -> bytes:
        """Capture a raster screenshot of the target window."""
        ...

    def manage_graph(self, request: GraphRequest) -> GraphResult:
        """Execute a graph domain mutation or query."""
        ...

    def manage_instrument(self, request: InstrumentRequest) -> InstrumentResult:
        """Execute an instrument domain mutation or query."""
        ...

    def manage_display(self, request: DisplayRequest) -> DisplayResult:
        """Execute a display layout domain mutation or query."""
        ...

    def manage_run(self, request: RunRequest) -> RunResult:
        """Execute a run management mutation or query."""
        ...

    def call(self, request: NativeRequest) -> JsonValue:
        """Execute a low-level native operation packet."""
        ...
