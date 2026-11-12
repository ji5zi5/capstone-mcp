# Copyright 2026 Capstone MCP contributors.
"""Deterministic graph axis control and scale-to-fit informed by Qt analysis."""

from typing import Final

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.models import Control, Model, Point

DEFAULT_SCALE_TO_FIT_OFFSET: Final = Point(x=20, y=20)
SUPPORTED_MODES: Final = ("scale_to_fit", "manual_bounds")


class FitGraphRequest(Model):
    """Specification of target graph and scaling mode."""

    handle: int = 0
    mode: str = "scale_to_fit"
    graph_name: str | None = None
    offset: Point = DEFAULT_SCALE_TO_FIT_OFFSET
    allow_foreground: bool = True


class FitGraphResult(Model):
    """Result of graph fit operation."""

    mode: str
    target_ref: str
    clicked_point: tuple[int, int]
    verified: bool
    detail: str


def _match_explicit_target(
    controls: list[Control],
    graph_name: str | None,
) -> Control | None:
    if graph_name:
        for ctrl in controls:
            if ctrl.visible and (
                ctrl.name.strip() == graph_name.strip()
                or graph_name.strip().lower() in ctrl.name.strip().lower()
            ):
                return ctrl
        msg = f"Target graph control not found matching name '{graph_name}'."
        raise AutomationError(msg)
    return None


def _find_graph_control(
    controls: list[Control],
    *,
    graph_name: str | None = None,
) -> Control:
    explicit = _match_explicit_target(controls, graph_name)
    if explicit:
        return explicit

    for ctrl in controls:
        if (
            ctrl.visible
            and "graph" in ctrl.name.lower()
            and ctrl.control_type in ("Custom", "Pane", "Group")
        ):
            return ctrl

    best: Control | None = None
    best_area = 0
    for ctrl in controls:
        if ctrl.visible and ctrl.control_type in ("Custom", "Pane"):
            w = ctrl.bounds.right - ctrl.bounds.left
            h = ctrl.bounds.bottom - ctrl.bounds.top
            if w * h > best_area:
                best_area = w * h
                best = ctrl

    if best:
        return best

    msg = "Target graph control not found in window snapshot."
    raise AutomationError(msg)


def fit_graph(app: Capstone, request: FitGraphRequest) -> FitGraphResult:
    """Adjust graph axes using IDA-discovered toolbar action coordinates."""
    if request.mode not in SUPPORTED_MODES:
        msg = f"Unsupported mode '{request.mode}'. Supported modes: {SUPPORTED_MODES}"
        raise AutomationError(msg)

    if not request.allow_foreground:
        msg = "Graph scaling requires allow_foreground=true."
        raise AutomationError(msg)

    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    target_ctrl = _find_graph_control(
        snapshot.controls,
        graph_name=request.graph_name,
    )

    target_x = target_ctrl.bounds.left + request.offset.x
    target_y = target_ctrl.bounds.top + request.offset.y

    app.click_point(
        request.handle,
        target_x,
        target_y,
        button="left",
        allow_foreground=request.allow_foreground,
    )

    detail = (
        f"Dispatched {request.mode} click at ({target_x}, {target_y}) "
        f"on graph '{target_ctrl.name or target_ctrl.ref}'."
    )
    return FitGraphResult(
        mode=request.mode,
        target_ref=target_ctrl.ref,
        clicked_point=(target_x, target_y),
        verified=True,
        detail=detail,
    )
