# Copyright 2026 Capstone MCP contributors.
"""Atomic popup menu selection and measurement assignment transaction."""

import contextlib
from typing import Final

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.models import Control, Model, Point

POPUP_SEARCH_LIMIT: Final = 2_000
POPUP_DEPTH_LIMIT: Final = 16


class SelectMeasurementRequest(Model):
    """Specification of popup coordinate and nested menu path."""

    handle: int = 0
    point: Point
    menu_path: list[str]
    allow_foreground: bool = True


class SelectMeasurementResult(Model):
    """Outcome of popup traversal and item selection."""

    selected_item: str
    traversed_path: list[str]
    verified: bool
    detail: str


def _find_menu_item(controls: list[Control], label: str) -> Control | None:
    norm = label.strip().lower()
    for ctrl in controls:
        if (
            ctrl.visible
            and ctrl.control_type in ("MenuItem", "ListItem", "Button", "Text")
            and (ctrl.name.strip().lower() == norm or norm in ctrl.name.strip().lower())
        ):
            return ctrl
    return None


def _traverse_segments(
    app: Capstone, request: SelectMeasurementRequest,
) -> list[str]:
    traversed: list[str] = []
    total = len(request.menu_path)
    for i, segment in enumerate(request.menu_path):
        snapshot = app.snapshot(
            request.handle, depth=POPUP_DEPTH_LIMIT, limit=POPUP_SEARCH_LIMIT,
        )
        item = _find_menu_item(snapshot.controls, segment)
        if item is None:
            msg = f"Menu item '{segment}' not found (step {i + 1}/{total})."
            raise AutomationError(msg)

        cx = (item.bounds.left + item.bounds.right) // 2
        cy = (item.bounds.top + item.bounds.bottom) // 2

        app.click_point(
            request.handle,
            cx,
            cy,
            button="left",
            allow_foreground=request.allow_foreground,
        )
        traversed.append(segment)
    return traversed


def select_graph_measurement(
    app: Capstone, request: SelectMeasurementRequest,
) -> SelectMeasurementResult:
    """Open popup at point, traverse menu path atomically, and select target item."""
    if not request.menu_path:
        msg = "menu_path must contain at least one item."
        raise AutomationError(msg)

    if not request.allow_foreground:
        msg = "Popup menu navigation requires allow_foreground=true."
        raise AutomationError(msg)

    app.click_point(
        request.handle,
        request.point.x,
        request.point.y,
        button="left",
        allow_foreground=request.allow_foreground,
    )

    try:
        traversed = _traverse_segments(app, request)
        verification_snapshot = app.snapshot(
            request.handle, depth=POPUP_DEPTH_LIMIT, limit=POPUP_SEARCH_LIMIT,
        )
        menu_open = any(
            c.visible and c.control_type == "Menu"
            for c in verification_snapshot.controls
        )

        detail = (
            f"Successfully selected '{request.menu_path[-1]}' "
            f"via path {request.menu_path}."
        )
        return SelectMeasurementResult(
            selected_item=request.menu_path[-1],
            traversed_path=traversed,
            verified=not menu_open,
            detail=detail,
        )
    except Exception as exc:
        with contextlib.suppress(Exception):
            _ = app.keys(
                request.handle, "{ESC}",
                allow_foreground=request.allow_foreground,
            )
        msg = f"Failed during menu traversal: {exc}. Safe rollback (ESC) issued."
        raise AutomationError(msg) from exc
