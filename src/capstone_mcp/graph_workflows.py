# Copyright 2026 Capstone MCP contributors.
"""Operate native graph pages using current screenshot anchors and UI menus."""

from _ctypes import COMError
from typing import Final

import win32clipboard
import win32gui
import win32process

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.graph_execution import GraphProgress
from capstone_mcp.graph_requests import (
    GraphAnalysisRequest,
    GraphFitOutcome,
    GraphFitRequest,
)
from capstone_mcp.graph_state import (
    FIT_ROWS,
    FIT_SUCCESS_STATUSES,
    FIT_TYPES,
    GraphState,
    parse_graph_xml,
)
from capstone_mcp.models import Point, Result, Snapshot
from capstone_mcp.ui_events import WindowEvents

TRANSITION_SECONDS: Final = 15
GRAPH_MIME: Final = "ItemCutCopyPasteMimeType"
MAX_GRAPH_BYTES: Final = 8 * 1024 * 1024


def invoke_graph_menu(
    app: Capstone, ref: str, *, screen_point: Point | None = None,
) -> None:
    """Click an open menu item without activating its transient Qt window."""
    foreground = win32gui.GetForegroundWindow()
    if win32process.GetWindowThreadProcessId(foreground)[1] != app.pid:
        msg = "Capstone lost foreground focus; no menu input was sent."
        raise AutomationError(msg)
    control = app.control(ref)
    bounds = control.rectangle()
    point = screen_point or Point(
        x=(bounds.left + bounds.right) // 2,
        y=(bounds.top + bounds.bottom) // 2,
    )
    control.click_input(button="left", coords=(point.x, point.y), absolute=True)
    app.refs.clear()


def _copied_graph(sequence: int, process_id: int) -> GraphState | None:
    if win32clipboard.GetClipboardSequenceNumber() == sequence:
        return None
    owner = win32clipboard.GetClipboardOwner()
    if not owner or win32process.GetWindowThreadProcessId(owner)[1] != process_id:
        msg = "Another application changed the clipboard during graph inspection."
        raise AutomationError(msg)
    format_id = win32clipboard.RegisterClipboardFormat(GRAPH_MIME)
    if not win32clipboard.IsClipboardFormatAvailable(format_id):
        msg = "Copy Display did not provide native graph data."
        raise AutomationError(msg)
    win32clipboard.OpenClipboard()
    try:
        payload = win32clipboard.GetClipboardData(format_id)
    finally:
        win32clipboard.CloseClipboard()
    if not isinstance(payload, bytes) or len(payload) > MAX_GRAPH_BYTES:
        msg = "Native graph clipboard payload is invalid or exceeds 8 MiB."
        raise AutomationError(msg)
    return parse_graph_xml(payload.rstrip(b"\0"))


def read_graph(
    app: Capstone, handle: int, *, allow_foreground: bool = True,
) -> GraphState:
    """Read selected graph state via native Copy Display; replaces the clipboard."""
    if not allow_foreground:
        msg = "Graph inspection uses the native Copy Display menu."
        raise AutomationError(msg)
    windows = app.windows()
    if len(windows) != 1 or windows[0].handle != handle:
        msg = "Select one graph and close existing menus before graph inspection."
        raise AutomationError(msg)
    pid = windows[0].process_id
    with WindowEvents(pid, clipboard=True) as events:
        _ = app.focus_window(handle)
        snapshot = app.snapshot(handle, 3, 400)
        menus = [
            c for c in snapshot.controls
            if c.control_type == "MenuItem" and c.name == "Display"
            and c.visible and c.enabled
        ]
        if len(menus) != 1:
            msg = "Expected one enabled Display menu."
            raise AutomationError(msg)
        _ = app.control(menus[0].ref).expand()
        popup = events.changes.until(
            lambda: ready_graph_menu(app, {handle}, "Copy Display"), TRANSITION_SECONDS,
            description="Display menu with Copy Display",
        )
        copies = [
            c for c in popup.controls if c.name == "Copy Display"
            and c.control_type == "MenuItem" and c.enabled and c.visible
        ]
        if len(copies) != 1:
            msg = "Select exactly one graph before inspecting its analysis."
            raise AutomationError(msg)
        sequence = win32clipboard.GetClipboardSequenceNumber()
        # Copy Display is nonmodal: invoke the named action, not a moving row.
        _ = app.control(copies[0].ref).invoke()
        app.refs.clear()
        state = events.changes.until(
            lambda: _copied_graph(sequence, pid), TRANSITION_SECONDS,
            description="New native graph clipboard data",
        )
        if any(w.handle == popup.window.handle for w in app.windows()):
            _ = app.keys(handle, "{ESC}")
        _ = events.changes.until(
            lambda: True if {w.handle for w in app.windows()} == {handle} else None,
            TRANSITION_SECONDS,
            description="Copy Display menu dismissal",
        )
        return state


def ready_graph_menu(app: Capstone, before: set[int], name: str) -> Snapshot | None:
    """Observe a newly opened menu only after its requested item is usable."""
    for window in app.windows():
        if window.handle in before:
            continue
        try:
            snapshot = app.snapshot(window.handle, 5, 500)
        except (COMError, AutomationError):
            # Qt can remove a popup or shadow between enumeration and observation.
            continue
        if any(c.name == name and c.control_type == "MenuItem"
               and c.enabled and c.visible
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
                lambda selected=name: ready_graph_menu(app, before, selected),
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
            invoke_graph_menu(app, matches[0].ref)
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
        try:
            snapshot = app.snapshot(window.handle, 3, 100)
        except (COMError, AutomationError):
            continue
        items = [c for c in snapshot.controls if c.control_type == "MenuItem"]
        if (
            len(items) == 1 and not items[0].name
            and not snapshot.controls[0].automation_id
        ):
            return snapshot
    return None


def _toggle_fit(
    app: Capstone, handle: int, point: Point, native_type: int,
    *, allow_foreground: bool = True,
) -> Result:
    """Toggle one known native model; callers must verify the copied state."""
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
            description=f"Native fit menu at {point}",
        )
        # IDA 0x1401CB9F0 builds 24 fit rows, not native-enum order.
        # The embedded widget ignores keyboard selection. Click its row center.
        bounds = popup.window.bounds
        if bounds.top < rect.top or bounds.bottom > rect.bottom:
            msg = "Fit menu is clipped; enlarge the window before choosing a fit."
            raise AutomationError(msg)
        item = next(c for c in popup.controls if c.control_type == "MenuItem")
        invoke_graph_menu(
            app, item.ref, screen_point=Point(
                x=(bounds.left + bounds.right) // 2,
                y=bounds.top + (bounds.bottom - bounds.top)
                * (2 * FIT_ROWS[native_type] + 1) // 48,
            ),
        )
        _ = app.keys(handle, "{ESC}")
        _ = events.changes.until(
            lambda: True if {w.handle for w in app.windows()} == before else None,
            TRANSITION_SECONDS,
        )
    return Result(
        detail=f"Native fit type {native_type} toggled; verify copied graph state.",
    )


def _enable_fitting(
    app: Capstone, handle: int, point: Point | None,
) -> GraphState:
    if point is None:
        msg = "Native fitting remained disabled; inspect the fit toolbar."
        raise AutomationError(msg)
    window = app.window(handle)
    rect = window.rectangle()
    if not (
        0 <= point.x < rect.right - rect.left
        and 0 <= point.y < rect.bottom - rect.top
    ):
        msg = "Fit icon anchor must be inside the current window."
        raise AutomationError(msg)
    _ = app.focus_window(handle)
    window.click_input(button="left", coords=(point.x, point.y))
    return read_graph(app, handle)


def set_graph_fits(
    app: Capstone, handle: int, request: GraphFitRequest,
    *, progress: GraphProgress | None = None,
) -> GraphFitOutcome:
    """Apply an exact model set and verify it against Capstone's own graph XML."""
    progress = progress or GraphProgress()
    progress.stage = "inspect_graph_for_fitting"
    before = read_graph(app, handle, allow_foreground=request.allow_foreground)
    verify_graph_binding(before, request.expected_data_signature)
    desired = {FIT_TYPES[model] for model in request.models}
    current = set(before.selected_types)
    unknown = current.difference(FIT_ROWS)
    if unknown:
        msg = f"Graph contains unsupported native fit types: {sorted(unknown)}."
        raise AutomationError(msg)
    if desired and not before.series:
        msg = "Assign both axes and select data before applying native fits."
        raise AutomationError(msg)
    if desired and not before.fit_enabled and request.master_point is None:
        msg = "Fitting is disabled; supply the observed fit icon as master_point."
        raise AutomationError(msg)
    state = before
    changed = False
    for native_type in sorted(current.symmetric_difference(desired)):
        progress.begin_input(f"select_fit_{native_type}")
        _ = _toggle_fit(app, handle, request.menu_point, native_type)
        progress.stage = f"verify_fit_{native_type}"
        expected = set(state.selected_types).symmetric_difference({native_type})
        observed = read_graph(app, handle)
        if set(observed.selected_types) != expected:
            msg = (
                f"Native fit selection was not confirmed for type {native_type}; "
                f"observed {observed.selected_types}. Inspect before retrying."
            )
            raise AutomationError(msg)
        if [
            (s.renderer_id, s.inputs) for s in observed.series
        ] != [(s.renderer_id, s.inputs) for s in before.series]:
            msg = "Graph data changed during fitting; inspect before retrying."
            raise AutomationError(msg)
        state = observed
        changed = True
        progress.confirmed(f"fit_{native_type}_verified")
    if desired and not state.fit_enabled:
        progress.begin_input("enable_fitting")
        state = _enable_fitting(app, handle, request.master_point)
        changed = True
    if set(state.selected_types) != desired or (desired and not state.fit_enabled):
        msg = "Requested native fit configuration was not confirmed."
        raise AutomationError(msg)
    progress.confirmed("fit_configuration_verified")
    successful = not desired or (
        bool(state.series) and all(
            any(
                fit.native_type == model and fit.error_status in FIT_SUCCESS_STATUSES
                for fit in series.fits
            )
            for series in state.series for model in desired
        )
    )
    return GraphFitOutcome(
        changed=changed, requested_models=request.models,
        fits_successful=successful, before=before, after=state,
    )


def analyze_graph(
    app: Capstone, handle: int, request: GraphAnalysisRequest,
    *, progress: GraphProgress | None = None,
) -> GraphFitOutcome:
    """Assign requested native axes, then set and read verified native fits."""
    progress = progress or GraphProgress()
    fitting = request.fitting
    if request.x is not None or request.y is not None:
        before = read_graph(app, handle, allow_foreground=fitting.allow_foreground)
        verify_graph_binding(before, fitting.expected_data_signature)
    for name, axis in (("x", request.x), ("y", request.y)):
        if axis is not None:
            progress.begin_input(f"select_{name}_axis")
            _ = select_graph_measurement(
                app, handle, axis.point, axis.menu_path,
                allow_foreground=request.fitting.allow_foreground,
            )
            progress.confirmed(f"{name}_menu_selection_delivered")
    if request.x is not None or request.y is not None:
        current = read_graph(app, handle)
        fitting = fitting.model_copy(update={
            "expected_data_signature": current.data_signature,
        })
    return set_graph_fits(app, handle, fitting, progress=progress)


def verify_graph_binding(state: GraphState, expected: str | None) -> None:
    """Reject stale data identity before changing axes or fit selections."""
    if expected is not None and state.data_signature != expected:
        msg = (
            "Graph data bindings changed. Call capstone_read_graph and inspect "
            "the source, dataset and unit IDs before issuing a new request."
        )
        raise AutomationError(msg)
