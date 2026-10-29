# Copyright 2026 Capstone MCP contributors.
"""Operate native graph pages using current screenshot anchors and UI menus."""

from typing import Final

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.models import Action, Point, Result, Snapshot
from capstone_mcp.ui_events import WindowEvents

TRANSITION_SECONDS: Final = 15


def _menu(app: Capstone, before: set[int], name: str) -> Snapshot | None:
    for window in app.windows():
        if window.handle in before:
            continue
        snapshot = app.snapshot(window.handle, 5, 500)
        if any(c.name == name and c.control_type == "MenuItem"
               for c in snapshot.controls):
            return snapshot
    return None


def create_graph(
    app: Capstone, handle: int, *, allow_foreground: bool = True,
) -> Result:
    """Insert a graph into the active page through its native display palette."""
    if not allow_foreground:
        msg = "Graph creation requires foreground input."
        raise AutomationError(msg)
    snapshot = app.snapshot(handle, 12, 800)
    matches = [
        c for c in snapshot.controls
        if c.name == "Graph" and c.control_type == "Text" and c.visible and c.enabled
    ]
    if len(matches) != 1:
        msg = "Expected one Graph display palette item; inspect the current page."
        raise AutomationError(msg)
    control = app.control(matches[0].ref)
    _ = app.focus_window(handle)
    bounds = control.rectangle()
    control.click_input(
        button="left", double=True, absolute=True,
        coords=((bounds.left + bounds.right) // 2,
                (bounds.top + bounds.bottom) // 2),
    )
    app.refs.clear()
    return Result(
        detail="Graph inserted; inspect a fresh screenshot before selecting axes.",
    )


def select_graph_measurement(
    app: Capstone, handle: int, point: Point, path: list[str],
    *, allow_foreground: bool = True,
) -> Result:
    """Open an observed axis label and choose an exact native measurement path."""
    if not allow_foreground:
        msg = "Graph axis selection requires foreground input."
        raise AutomationError(msg)
    if not path or any(not part for part in path):
        msg = "Provide a nonempty exact measurement menu path."
        raise AutomationError(msg)
    window = app.window(handle)
    rect = window.rectangle()
    if not (
        0 <= point.x < rect.right - rect.left
        and 0 <= point.y < rect.bottom - rect.top
    ):
        msg = "Axis anchor must be inside the current window."
        raise AutomationError(msg)
    before = {w.handle for w in app.windows()}
    if before != {handle}:
        msg = "Close existing dialogs and menus before selecting a graph axis."
        raise AutomationError(msg)
    with WindowEvents(window.process_id()) as events:
        _ = app.focus_window(handle)
        window.click_input(button="left", coords=(point.x, point.y))
        for name in path:
            menu = events.changes.until(
                lambda selected=name: _menu(app, before, selected),
                TRANSITION_SECONDS,
            )
            matches = [
                c for c in menu.controls
                if c.control_type == "MenuItem" and c.name == name
                and c.visible and c.enabled
            ]
            if len(matches) != 1:
                msg = f"Measurement menu entry is ambiguous or disabled: {name!r}."
                raise AutomationError(msg)
            _ = app.act(matches[0].ref, Action.INVOKE)
        _ = events.changes.until(
            lambda: True if {w.handle for w in app.windows()} == before else None,
            TRANSITION_SECONDS,
        )
    return Result(
        detail=f"Selected {path!r}; inspect a fresh screenshot to confirm the axis.",
    )


def _fit_menu(app: Capstone, before: set[int]) -> Snapshot | None:
    for window in app.windows():
        if window.handle in before or window.title != "PASCO Capstone":
            continue
        snapshot = app.snapshot(window.handle, 3, 100)
        items = [c for c in snapshot.controls if c.control_type == "MenuItem"]
        if (
            len(items) == 1 and not items[0].name
            and not snapshot.controls[0].automation_id
        ):
            return snapshot
    return None


def toggle_linear_fit(
    app: Capstone, handle: int, point: Point,
    *, allow_foreground: bool = True,
) -> Result:
    """Toggle native Linear fit through the observed graph fit-menu anchor."""
    if not allow_foreground:
        msg = "Graph fitting requires foreground input."
        raise AutomationError(msg)
    window = app.window(handle)
    rect = window.rectangle()
    if not (
        0 <= point.x < rect.right - rect.left
        and 0 <= point.y < rect.bottom - rect.top
    ):
        msg = "Fit-menu anchor must be inside the current window."
        raise AutomationError(msg)
    before = {w.handle for w in app.windows()}
    if before != {handle}:
        msg = "Close existing dialogs and menus before toggling a graph fit."
        raise AutomationError(msg)
    with WindowEvents(window.process_id()) as events:
        _ = app.focus_window(handle)
        window.click_input(button="left", coords=(point.x, point.y))
        popup = events.changes.until(
            lambda: _fit_menu(app, before), TRANSITION_SECONDS,
        )
        # IDA 0x1401CB9F0 builds 24 fit rows; Linear is row 1.
        # The embedded widget ignores keyboard selection. Click its row center.
        bounds = popup.window.bounds
        if bounds.top < rect.top or bounds.bottom > rect.bottom:
            msg = "Fit menu is clipped; enlarge the window before choosing a fit."
            raise AutomationError(msg)
        app.window(popup.window.handle).click_input(
            button="left", absolute=True,
            coords=((bounds.left + bounds.right) // 2,
                    bounds.top + (bounds.bottom - bounds.top) // 16),
        )
        _ = app.keys(handle, "{ESC}")
        _ = events.changes.until(
            lambda: True if {w.handle for w in app.windows()} == before else None,
            TRANSITION_SECONDS,
        )
    return Result(
        detail="Linear fit toggled; inspect the graph. Calling again reverses it.",
    )
