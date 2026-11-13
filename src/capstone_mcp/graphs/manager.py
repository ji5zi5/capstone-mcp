# Copyright 2026 Capstone MCP contributors.
"""Unified Graph Manager engine and functional manage_graph seam."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.displays import click_control
from capstone_mcp.graphs.inspection import (
    read_graph,
    summarize_graph,
    verify_graph_binding,
)
from capstone_mcp.graphs.models import (
    FIT_ROWS,
    FIT_SUCCESS_STATUSES,
    FIT_TYPES,
    SUPPORTED_FIT_MODES,
    AnalyzeGraphRequest,
    AnalyzeGraphResult,
    CreateGraphRequest,
    CreateGraphResult,
    FitGraphRequest,
    FitGraphResult,
    GraphAction,
    GraphDeltaRequest,
    GraphDeltaResult,
    GraphFitOutcome,
    GraphProgress,
    GraphRequest,
    GraphResult,
    GraphState,
    MeasureGraphAreaRequest,
    MeasureGraphAreaResult,
    ReadGraphRequest,
    ReadGraphResult,
    SelectMeasurementRequest,
    SelectMeasurementResult,
    SetGraphFitsRequest,
    ToggleGraphStatisticsRequest,
    ToggleGraphStatisticsResult,
)
from capstone_mcp.graphs.toolbox import (
    _find_graph_control,
    graph_delta,
    measure_graph_area,
    toggle_graph_statistics,
)
from capstone_mcp.models import Point, Result, Snapshot

if TYPE_CHECKING:
    from collections.abc import Callable

try:
    import win32gui
    import win32process

    from capstone_mcp.ui_events import WindowEvents
except ImportError:
    win32gui = None  # type: ignore[assignment]
    win32process = None  # type: ignore[assignment]
    WindowEvents = None  # type: ignore[assignment, misc]

logger = logging.getLogger(__name__)

TRANSITION_SECONDS: Final = 15


# ---------------------------------------------------------------------------
# 1. Menu Interaction Helpers
# ---------------------------------------------------------------------------


def invoke_graph_menu(
    app: Capstone,
    ref: str,
    *,
    screen_point: Point | None = None,
) -> None:
    """Click an open menu item without activating its transient Qt window."""
    if win32gui is not None and win32process is not None:
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


def ready_graph_menu(app: Capstone, before: set[int], name: str) -> Snapshot | None:
    """Observe a newly opened menu only after its requested item is usable."""
    for window in app.windows():
        if window.handle in before:
            continue
        try:
            snapshot = app.snapshot(window.handle, 5, 500)
        except Exception as e:  # noqa: BLE001
            logger.debug(
                "Failed to snapshot window %s: %s", window.handle, e,
            )
            continue
        if any(
            c.name == name
            and c.control_type == "MenuItem"
            and c.enabled
            and c.visible
            for c in snapshot.controls
        ):
            return snapshot
    return None


def _fit_menu(app: Capstone, before: set[int]) -> Snapshot | None:
    for window in app.windows():
        if window.handle in before or window.title != "PASCO Capstone":
            continue
        try:
            snapshot = app.snapshot(window.handle, 3, 100)
        except Exception as e:  # noqa: BLE001
            logger.debug(
                "Failed to snapshot fit menu window %s: %s", window.handle, e,
            )
            continue
        items = [c for c in snapshot.controls if c.control_type == "MenuItem"]
        if (
            len(items) == 1
            and not items[0].name
            and not snapshot.controls[0].automation_id
        ):
            return snapshot
    return None


def _toggle_fit(
    app: Capstone,
    handle: int,
    point: Point,
    native_type: int,
    *,
    allow_foreground: bool = True,
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
    if WindowEvents is None:
        msg = "WindowEvents requires Windows environment."
        raise AutomationError(msg)
    with WindowEvents(window.process_id()) as events:
        _ = app.focus_window(handle)
        window.click_input(button="left", coords=(point.x, point.y))
        popup = events.changes.until(
            lambda: _fit_menu(app, before),
            TRANSITION_SECONDS,
            description=f"Native fit menu at {point}",
        )
        bounds = popup.window.bounds
        if bounds.top < rect.top or bounds.bottom > rect.bottom:
            msg = "Fit menu is clipped; enlarge the window before choosing a fit."
            raise AutomationError(msg)
        item = next(c for c in popup.controls if c.control_type == "MenuItem")
        invoke_graph_menu(
            app,
            item.ref,
            screen_point=Point(
                x=(bounds.left + bounds.right) // 2,
                y=bounds.top
                + (bounds.bottom - bounds.top)
                * (2 * FIT_ROWS[native_type] + 1)
                // 48,
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
    app: Capstone,
    handle: int,
    point: Point | None,
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


# ---------------------------------------------------------------------------
# 2. Individual Operational Functions
# ---------------------------------------------------------------------------


def create_graph(
    app: Capstone,
    request: CreateGraphRequest | None = None,
) -> CreateGraphResult:
    """Insert a graph into the active page through its display palette item."""
    if request is None:
        request = CreateGraphRequest()
    if not request.allow_foreground:
        msg = "Graph creation requires foreground input."
        raise AutomationError(msg)

    snapshot = app.snapshot(request.handle, depth=12, limit=800)
    matches = [
        c
        for c in snapshot.controls
        if c.name == "Graph"
        and c.control_type in ("Text", "Button", "ListItem", "Custom")
        and c.visible
        and c.enabled
    ]
    if len(matches) != 1:
        msg = "Expected one Graph display palette item; inspect the current page."
        raise AutomationError(msg)

    palette_item = matches[0]
    click_control(
        app,
        request.handle,
        palette_item,
        double=True,
        allow_foreground=True,
    )
    return CreateGraphResult(
        detail="Graph inserted; inspect a fresh screenshot before selecting axes.",
        verified=True,
    )


def fit_graph(
    app: Capstone,
    request: FitGraphRequest | None = None,
) -> FitGraphResult:
    """Adjust graph axes using IDA-discovered toolbar action coordinates."""
    if request is None:
        request = FitGraphRequest()
    if request.mode not in SUPPORTED_FIT_MODES:
        msg = (
            f"Unsupported mode '{request.mode}'. "
            f"Supported modes: {SUPPORTED_FIT_MODES}"
        )
        raise AutomationError(msg)
    if not request.allow_foreground:
        msg = "Graph scaling requires allow_foreground=true."
        raise AutomationError(msg)

    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    target_ctrl = _find_graph_control(snapshot.controls, request.graph_name)

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


def select_graph_measurement(
    app: Capstone,
    handle: int,
    point: Point,
    path: list[str],
    *,
    allow_foreground: bool = True,
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

    if WindowEvents is None:
        msg = "WindowEvents requires Windows pywin32 environment."
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
                c
                for c in menu.controls
                if c.control_type == "MenuItem"
                and c.name == name
                and c.visible
                and c.enabled
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


def set_graph_fits(
    app: Capstone,
    handle: int,
    request: SetGraphFitsRequest,
    *,
    progress: GraphProgress | None = None,
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
        bool(state.series)
        and all(
            any(
                fit.native_type == model and fit.error_status in FIT_SUCCESS_STATUSES
                for fit in series.fits
            )
            for series in state.series
            for model in desired
        )
    )
    return GraphFitOutcome(
        changed=changed,
        requested_models=request.models,
        fits_successful=successful,
        before=before,
        after=state,
    )


def analyze_graph(
    app: Capstone,
    handle: int,
    request: AnalyzeGraphRequest,
    *,
    progress: GraphProgress | None = None,
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
                app,
                handle,
                axis.point,
                axis.menu_path,
                allow_foreground=request.fitting.allow_foreground,
            )
            progress.confirmed(f"{name}_menu_selection_delivered")

    if request.x is not None or request.y is not None:
        current = read_graph(app, handle)
        fitting = fitting.model_copy(
            update={"expected_data_signature": current.data_signature},
        )
    return set_graph_fits(app, handle, fitting, progress=progress)


# ---------------------------------------------------------------------------
# 3. GraphManager Class & manage_graph Seam
# ---------------------------------------------------------------------------


class GraphManager:
    """Consolidated engine for all Capstone graph interactions and analysis."""

    def __init__(self, app: Capstone) -> None:
        """Initialize GraphManager with Capstone desktop app instance."""
        self.app = app

    def create(self, request: CreateGraphRequest) -> CreateGraphResult:
        """Insert a graph onto active page."""
        return create_graph(self.app, request)

    def read(self, request: ReadGraphRequest) -> ReadGraphResult:
        """Read graph state via native clipboard."""
        state = read_graph(
            self.app,
            request.handle,
            allow_foreground=request.allow_foreground,
        )
        return ReadGraphResult(state=state, verified=True)

    def fit(self, request: FitGraphRequest) -> FitGraphResult:
        """Auto-scale axes using Scale to Fit."""
        return fit_graph(self.app, request)

    def select_measurement(
        self,
        request: SelectMeasurementRequest,
    ) -> SelectMeasurementResult:
        """Select an axis measurement via popup menu."""
        res = select_graph_measurement(
            self.app,
            request.handle,
            request.point,
            request.path,
            allow_foreground=request.allow_foreground,
        )
        return SelectMeasurementResult(detail=res.detail, verified=True)

    def toolbox_delta(self, request: GraphDeltaRequest) -> GraphDeltaResult:
        """Toggle delta tool and read coordinate offsets."""
        return graph_delta(self.app, request)

    def toolbox_area(self, request: MeasureGraphAreaRequest) -> MeasureGraphAreaResult:
        """Toggle area tool and read curve integration."""
        return measure_graph_area(self.app, request)

    def toolbox_statistics(
        self,
        request: ToggleGraphStatisticsRequest,
    ) -> ToggleGraphStatisticsResult:
        """Toggle statistics box and extract summary metrics."""
        return toggle_graph_statistics(self.app, request)

    def analyze(self, request: AnalyzeGraphRequest) -> AnalyzeGraphResult:
        """Assign axes, fit curves, and compile summary report."""
        outcome = analyze_graph(self.app, request.handle, request)
        report = summarize_graph(outcome.after) if outcome.after else None
        return AnalyzeGraphResult(outcome=outcome, report=report)

    def _manage_create(self, request: GraphRequest) -> GraphResult:
        if request.create is None:
            msg = "create request must be provided for CREATE action."
            raise AutomationError(msg)
        return GraphResult(
            action=request.action,
            create=self.create(request.create),
        )

    def _manage_read(self, request: GraphRequest) -> GraphResult:
        if request.read is None:
            msg = "read request must be provided for READ action."
            raise AutomationError(msg)
        return GraphResult(action=request.action, read=self.read(request.read))

    def _manage_fit(self, request: GraphRequest) -> GraphResult:
        if request.fit is None:
            msg = "fit request must be provided for FIT action."
            raise AutomationError(msg)
        return GraphResult(action=request.action, fit=self.fit(request.fit))

    def _manage_select_measurement(self, request: GraphRequest) -> GraphResult:
        if request.select_measurement is None:
            msg = (
                "select_measurement request must be provided for "
                "SELECT_MEASUREMENT action."
            )
            raise AutomationError(msg)
        return GraphResult(
            action=request.action,
            select_measurement=self.select_measurement(request.select_measurement),
        )

    def _manage_delta(self, request: GraphRequest) -> GraphResult:
        if request.toolbox_delta is None:
            msg = "toolbox_delta request must be provided for TOOLBOX_DELTA action."
            raise AutomationError(msg)
        return GraphResult(
            action=request.action,
            toolbox_delta=self.toolbox_delta(request.toolbox_delta),
        )

    def _manage_area(self, request: GraphRequest) -> GraphResult:
        if request.toolbox_area is None:
            msg = "toolbox_area request must be provided for TOOLBOX_AREA action."
            raise AutomationError(msg)
        return GraphResult(
            action=request.action,
            toolbox_area=self.toolbox_area(request.toolbox_area),
        )

    def _manage_statistics(self, request: GraphRequest) -> GraphResult:
        if request.toolbox_statistics is None:
            msg = (
                "toolbox_statistics request must be provided for "
                "TOOLBOX_STATISTICS action."
            )
            raise AutomationError(msg)
        return GraphResult(
            action=request.action,
            toolbox_statistics=self.toolbox_statistics(
                request.toolbox_statistics,
            ),
        )

    def _manage_analyze(self, request: GraphRequest) -> GraphResult:
        if request.analyze is None:
            msg = "analyze request must be provided for ANALYZE action."
            raise AutomationError(msg)
        return GraphResult(
            action=request.action,
            analyze=self.analyze(request.analyze),
        )

    def manage(self, request: GraphRequest) -> GraphResult:
        """Unified dispatch method for all graph actions."""
        dispatchers: dict[GraphAction, Callable[[GraphRequest], GraphResult]] = {
            GraphAction.CREATE: self._manage_create,
            GraphAction.READ: self._manage_read,
            GraphAction.FIT: self._manage_fit,
            GraphAction.SELECT_MEASUREMENT: self._manage_select_measurement,
            GraphAction.TOOLBOX_DELTA: self._manage_delta,
            GraphAction.TOOLBOX_AREA: self._manage_area,
            GraphAction.TOOLBOX_STATISTICS: self._manage_statistics,
            GraphAction.ANALYZE: self._manage_analyze,
        }
        handler = dispatchers.get(request.action)
        if handler is None:
            msg = f"Unsupported GraphAction: {request.action}"
            raise AutomationError(msg)
        return handler(request)


def manage_graph(app: Capstone, request: GraphRequest) -> GraphResult:
    """Functional convenience wrapper for the unified graph management seam."""
    return GraphManager(app).manage(request)
