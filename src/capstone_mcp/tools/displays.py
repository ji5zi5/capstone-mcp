# Copyright 2026 Capstone MCP contributors.
"""Tool router for graphs, tables, digits displays, and workbook pages."""

from collections.abc import Awaitable, Callable
from typing import Any, Final, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, ImageContent, TextContent, ToolAnnotations
from pydantic import JsonValue, TypeAdapter

from capstone_mcp.automation_models import NativeRequest
from capstone_mcp.digits_display import CreateDigitsResult
from capstone_mcp.graph_control import FitGraphResult
from capstone_mcp.graph_execution import GraphCapture, GraphFailure
from capstone_mcp.graph_report import GraphAnalysisReport, summarize_graph
from capstone_mcp.graph_requests import (
    GraphAnalysisRequest,
    GraphFitOutcome,
    GraphFitRequest,
)
from capstone_mcp.graph_state import FitModel, GraphState
from capstone_mcp.graph_toolbox import (
    GraphDeltaResult,
    MeasureGraphAreaResult,
    ToggleGraphStatisticsResult,
)
from capstone_mcp.models import Point, Result
from capstone_mcp.runs import DeleteRunResult, RenameRunResult, SetRunVisibilityResult
from capstone_mcp.table_display import (
    CreateTableResult,
    ReadTableResult,
    SetTableColumnsResult,
)
from capstone_mcp.workbook_layout import (
    AddPageResult,
    PageLayoutTemplate,
    SetPageLayoutResult,
)

type NativeCaller = Callable[..., Awaitable[Any]]
DEFAULT_FIT_OFFSET: Final = Point(x=20, y=20)
JSON_VALUE: Final = TypeAdapter(JsonValue)


def register_display_tools(
    mcp: FastMCP,
    native: NativeCaller,
    get_last_failure: Callable[[], GraphFailure | None] | None = None,
) -> dict[str, Any]:
    """Register all graph, table, digits, and display layout tools."""

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Insert a graph in Capstone",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def capstone_create_graph(
        handle: int,
        *,
        allow_foreground: bool = True,
    ) -> Result:
        """Insert a real graph into the active Capstone page, not a standalone PNG.

        Inspect a fresh screenshot afterward. Custom graph axes are not exposed in
        UIA; use their observed window-relative coordinates for measurement selection.
        """
        return Result.model_validate(
            await native(
                NativeRequest(
                    operation="create_graph",
                    handle=handle,
                    allow_foreground=allow_foreground,
                ),
                mutates=True,
            ),
        )

    @mcp.tool()
    async def capstone_select_graph_measurement(
        handle: int,
        axis_point: Point,
        menu_path: list[str],
        frame_id: str,
        *,
        allow_foreground: bool = True,
    ) -> Result:
        """Assign an axis using its current screenshot anchor and exact menu labels.

        axis_point uses the current client-area screenshot's pixel coordinates.
        frame_id must come from capstone_observe_graph in this worker session.
        menu_path selects a measurement, optionally through nested native submenus.
        Never reuse coordinates after moving/resizing the window or graph.
        Inspect a fresh screenshot afterward to confirm the changed axis.
        """
        return Result.model_validate(
            await native(
                NativeRequest(
                    operation="select_graph_measurement",
                    handle=handle,
                    point=axis_point,
                    menu_path=menu_path,
                    allow_foreground=allow_foreground,
                    frame_id=frame_id,
                ),
                mutates=True,
            ),
        )

    @mcp.tool(
        structured_output=False,
        annotations=ToolAnnotations(
            title="Capture graph image and one-use frame receipt",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def capstone_observe_graph(handle: int) -> CallToolResult:
        """Return an original-size PNG and JSON frame_id for the next graph input.

        Activates the graph window and captures its visible client-area screen pixels.
        Use coordinates from this exact image, without resizing. Graph input rejects
        changed pixels or window bounds before starting; animation or live updates
        can therefore require a new capture. A receipt is consumed by one request.
        Capture again after each graph operation or any failed input request.
        """
        capture = GraphCapture.model_validate(
            await native(
                NativeRequest(
                    operation="observe_graph",
                    handle=handle,
                ),
                mutates=True,
            ),
        )
        frame_json = capture.frame.model_dump_json()
        return CallToolResult(
            content=[
                ImageContent(
                    type="image",
                    data=capture.png_base64,
                    mimeType="image/png",
                ),
                TextContent(type="text", text=frame_json),
            ],
            structuredContent=TypeAdapter(dict[str, JsonValue]).validate_json(
                frame_json,
            ),
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Read the last structured graph failure",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    def capstone_graph_recovery() -> GraphFailure | None:
        """Read failure stage, confirmed steps and safe next action without replay.

        This is the last graph failure, not a claim about a later successful call.
        Correlate request_id and operation. If graph_input_may_have_been_sent is true,
        inspect the app before another write; never automatically replay the request.
        """
        if get_last_failure is not None:
            return get_last_failure()
        return None

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Compare native fits within matching data bindings",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def capstone_graph_report(
        handle: int,
        *,
        allow_foreground: bool = True,
    ) -> GraphAnalysisReport:
        """Read a selected graph and group fit comparisons by exact renderer/run/units.

        Returns native parameters, free parameter counts, valid common metrics and
        descriptive MSE/RMSE minima, never an overall best-model recommendation.
        Missing sample count/residuals prevent AIC/BIC and residual-based conclusions.
        request_model contains an accepted API enum when the native model is settable.
        Uses Copy Display and replaces the clipboard; does not change fitted models.
        """
        state = GraphState.model_validate(
            await native(
                NativeRequest(
                    operation="read_graph",
                    handle=handle,
                    allow_foreground=allow_foreground,
                ),
                mutates=True,
            ),
        )
        return summarize_graph(state)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Inspect selected graph and native results",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def capstone_read_graph(
        handle: int,
        *,
        allow_foreground: bool = True,
    ) -> GraphState:
        """Read selected graph's actual models, native coefficients and run/unit IDs.

        Uses Display > Copy Display and replaces the Windows clipboard with the
        selected graph. Does not save or modify the experiment. Select exactly one
        graph and close menus first. Values come from Capstone, not an external fit.
        Copy data_signature into the next fitting request to guard source/run/unit
        identity. It does not fingerprint live sample contents or screenshot layout.
        """
        return GraphState.model_validate(
            await native(
                NativeRequest(
                    operation="read_graph",
                    handle=handle,
                    allow_foreground=allow_foreground,
                ),
                mutates=True,
            ),
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            title="List accepted native fitting model names",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    def capstone_fit_models() -> list[FitModel]:
        """List supported built-in native models; custom-expression editing is excluded."""
        return list(FitModel)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Set and verify exact native fitting models",
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def capstone_set_graph_fits(
        handle: int,
        request: GraphFitRequest,
    ) -> GraphFitOutcome:
        """Set an exact native fit-model set and return verified native results.

        Repeated requests preserve already selected fits; [] removes all models.
        Use current screenshot anchors for menu_point (dropdown arrow) and
        master_point (fit icon, needed when fitting is disabled).
        Copies the graph before/after actions, replacing the Windows clipboard.
        Numerical failure is reported separately from verified model selection.
        First read_graph, then capstone_observe_graph for a new one-use frame_id.
        Copy data_signature to request.expected_data_signature.
        Check next_action and each fit's status/successful, not changed alone.
        """
        return GraphFitOutcome.model_validate(
            await native(
                NativeRequest(
                    operation="set_graph_fits",
                    handle=handle,
                    frame_id=request.frame_id,
                    graph_request=JSON_VALUE.validate_json(
                        request.model_dump_json(),
                    ),
                ),
                mutates=True,
            ),
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Configure graph axes and analyze native fits",
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def capstone_analyze_graph(
        handle: int,
        request: GraphAnalysisRequest,
    ) -> GraphFitOutcome:
        """Configure optional X/Y axes, apply model choices, and read native results.

        Create/select a graph and inspect its screenshot first. This combines named
        measurement selection with idempotent native fitting in one worker session.
        Uses the clipboard for verification. Existing unrelated displays are retained.
        fitting.expected_data_signature checks the original graph before changing
        either axis; the updated bindings are then verified for the fitting stage.
        fitting.frame_id must be the latest capstone_observe_graph receipt.
        """
        return GraphFitOutcome.model_validate(
            await native(
                NativeRequest(
                    operation="analyze_graph",
                    handle=handle,
                    frame_id=request.fitting.frame_id,
                    graph_request=JSON_VALUE.validate_json(
                        request.model_dump_json(),
                    ),
                ),
                mutates=True,
            ),
        )

    @mcp.tool()
    async def capstone_fit_graph(
        handle: int = 0,
        *,
        mode: Literal["scale_to_fit", "manual_bounds"] = "scale_to_fit",
        graph_name: str | None = None,
        offset: Point = DEFAULT_FIT_OFFSET,
        allow_foreground: bool = True,
    ) -> FitGraphResult:
        """Scale graph axes to fit all data or adjust bounds deterministically.

        Args:
            handle: Capstone main window handle (0 for active window).
            mode: Scaling mode ('scale_to_fit' or 'manual_bounds').
            graph_name: Target graph display name (None for active graph).
            offset: Offset coordinate point for scale-to-fit toolbar icon.
            allow_foreground: Bring window to foreground for UI automation.

        Returns:
            FitGraphResult with scaling outcome and graph identity.
        """
        return FitGraphResult.model_validate(
            await native(
                NativeRequest(
                    operation="fit_graph",
                    handle=handle,
                    mode=mode,
                    target=graph_name or "",
                    point=offset,
                    allow_foreground=allow_foreground,
                ),
                mutates=True,
            ),
        )

    @mcp.tool()
    async def capstone_toggle_graph_statistics(
        handle: int = 0,
        *,
        graph_name: str | None = None,
        enable: bool | None = None,
        allow_foreground: bool = True,
    ) -> ToggleGraphStatisticsResult:
        """Toggle graph statistics box (Σ) and read descriptive statistics.

        Args:
            handle: Capstone main window handle (0 for active window).
            graph_name: Specific graph display name (None targets active graph).
            enable: Explicitly enable (True), disable (False), or toggle (None).
            allow_foreground: Bring window to foreground for UI automation.

        Returns:
            ToggleGraphStatisticsResult with statistics dict (mean, min, max, std_dev).
        """
        return ToggleGraphStatisticsResult.model_validate(
            await native(
                NativeRequest(
                    operation="toggle_graph_statistics",
                    handle=handle,
                    graph_name=graph_name,
                    enable=enable,
                    allow_foreground=allow_foreground,
                ),
                mutates=True,
            ),
        )

    @mcp.tool()
    async def capstone_measure_graph_area(
        handle: int = 0,
        *,
        graph_name: str | None = None,
        enable: bool | None = None,
        allow_foreground: bool = True,
    ) -> MeasureGraphAreaResult:
        """Toggle graph area integration tool (∫ydx) and extract integral value.

        Args:
            handle: Capstone main window handle (0 for active window).
            graph_name: Specific graph display name (None targets active graph).
            enable: Explicitly enable (True), disable (False), or toggle (None).
            allow_foreground: Bring window to foreground for UI automation.

        Returns:
            MeasureGraphAreaResult with area value, integral units, and active status.
        """
        return MeasureGraphAreaResult.model_validate(
            await native(
                NativeRequest(
                    operation="measure_graph_area",
                    handle=handle,
                    graph_name=graph_name,
                    enable=enable,
                    allow_foreground=allow_foreground,
                ),
                mutates=True,
            ),
        )

    @mcp.tool()
    async def capstone_graph_delta(
        handle: int = 0,
        *,
        graph_name: str | None = None,
        point1: Point | None = None,
        point2: Point | None = None,
        allow_foreground: bool = True,
    ) -> GraphDeltaResult:
        """Activate delta crosshair tool and read coordinate differences (Δx, Δy).

        Args:
            handle: Capstone main window handle (0 for active window).
            graph_name: Specific graph display name (None targets active graph).
            point1: First reference coordinate point (Point(x=..., y=...)).
            point2: Second reference coordinate point (Point(x=..., y=...)).
            allow_foreground: Bring window to foreground for UI automation.

        Returns:
            GraphDeltaResult with delta_x, delta_y, slope, and crosshair state.
        """
        return GraphDeltaResult.model_validate(
            await native(
                NativeRequest(
                    operation="graph_delta",
                    handle=handle,
                    graph_name=graph_name,
                    point1=point1,
                    point2=point2,
                    allow_foreground=allow_foreground,
                ),
                mutates=True,
            ),
        )

    @mcp.tool()
    async def capstone_create_table(
        handle: int = 0,
        *,
        table_name: str | None = None,
        allow_foreground: bool = True,
    ) -> CreateTableResult:
        """Create a new Table display widget on the active workbook page.

        Args:
            handle: Capstone main window handle (0 for active window).
            table_name: Optional title or name for the created table display.
            allow_foreground: Bring window to foreground for UI automation.

        Returns:
            CreateTableResult with table_id, name, columns, and status.
        """
        return CreateTableResult.model_validate(
            await native(
                NativeRequest(
                    operation="create_table",
                    handle=handle,
                    table_name=table_name,
                    allow_foreground=allow_foreground,
                ),
                mutates=True,
            ),
        )

    @mcp.tool()
    async def capstone_set_table_columns(
        columns: list[str],
        handle: int = 0,
        *,
        table_name: str | None = None,
        allow_foreground: bool = True,
    ) -> SetTableColumnsResult:
        """Configure columns and data bindings for a Table display.

        Args:
            columns: List of measurement or calculation names to map as table columns.
            handle: Capstone main window handle (0 for active window).
            table_name: Target table display name or ID (None targets active table).
            allow_foreground: Bring window to foreground for UI automation.

        Returns:
            SetTableColumnsResult with updated columns list and binding status.
        """
        return SetTableColumnsResult.model_validate(
            await native(
                NativeRequest(
                    operation="set_table_columns",
                    handle=handle,
                    columns=columns,
                    table_name=table_name,
                    allow_foreground=allow_foreground,
                ),
                mutates=True,
            ),
        )

    @mcp.tool()
    async def capstone_read_table(  # noqa: PLR0913
        handle: int = 0,
        *,
        table_name: str | None = None,
        page: int = 1,
        page_size: int = 50,
        include_statistics: bool = True,
        allow_foreground: bool = True,
    ) -> ReadTableResult:
        """Read rendered table rows, pagination info, and summary statistics.

        Args:
            handle: Capstone main window handle (0 for active window).
            table_name: Target table display name or ID (None targets active table).
            page: Page number for paginated rows (1-based, default 1).
            page_size: Number of rows per page (default 50).
            include_statistics: Include summary statistics (mean, std_dev, min, max).
            allow_foreground: Bring window to foreground for UI automation.

        Returns:
            ReadTableResult containing headers, rows, total_rows, and statistics.
        """
        return ReadTableResult.model_validate(
            await native(
                NativeRequest(
                    operation="read_table",
                    handle=handle,
                    table_name=table_name,
                    page=page,
                    page_size=page_size,
                    include_statistics=include_statistics,
                    allow_foreground=allow_foreground,
                ),
                mutates=False,
            ),
        )

    @mcp.tool()
    async def capstone_create_digits(
        handle: int = 0,
        *,
        measurement: str | None = None,
        digits_name: str | None = None,
        allow_foreground: bool = True,
    ) -> CreateDigitsResult:
        """Create a large Digits numeric display and optionally bind a measurement.

        Args:
            handle: Capstone main window handle (0 for active window).
            measurement: Sensor measurement or calculation name to monitor.
            digits_name: Optional custom title/name for the digits display widget.
            allow_foreground: Bring window to foreground for UI automation.

        Returns:
            CreateDigitsResult with digits_id, name, bound measurement, and unit.
        """
        return CreateDigitsResult.model_validate(
            await native(
                NativeRequest(
                    operation="create_digits",
                    handle=handle,
                    measurement=measurement,
                    digits_name=digits_name,
                    allow_foreground=allow_foreground,
                ),
                mutates=True,
            ),
        )

    @mcp.tool()
    async def capstone_rename_run(
        handle: int,
        old_name: str,
        new_name: str,
        *,
        allow_foreground: bool = True,
    ) -> RenameRunResult:
        """Rename a specific Run item in the Data Summary tree safely.

        Args:
            handle: Capstone main window handle.
            old_name: Existing run name in Data Summary (e.g. 'Run #1').
            new_name: Desired new name for the run (e.g. 'Baseline trial').
            allow_foreground: Bring window to foreground for UI automation.

        Returns:
            RenameRunResult with rename confirmation and updated run list.
        """
        return RenameRunResult.model_validate(
            await native(
                NativeRequest(
                    operation="rename_run",
                    handle=handle,
                    old_name=old_name,
                    new_name=new_name,
                    allow_foreground=allow_foreground,
                ),
                mutates=True,
            ),
        )

    @mcp.tool()
    async def capstone_delete_run(
        handle: int = 0,
        *,
        run_name: str = "last_run",
        allow_foreground: bool = True,
    ) -> DeleteRunResult:
        """Delete a run from Data Summary, auto-confirming any modal dialog.

        Args:
            handle: Capstone main window handle (0 for active window).
            run_name: Name of the run to delete, or 'last_run' for most recent run.
            allow_foreground: Bring window to foreground for UI automation.

        Returns:
            DeleteRunResult with deleted run name and remaining runs.
        """
        return DeleteRunResult.model_validate(
            await native(
                NativeRequest(
                    operation="delete_run",
                    handle=handle,
                    run_name=run_name,
                    allow_foreground=allow_foreground,
                ),
                mutates=True,
            ),
        )

    @mcp.tool()
    async def capstone_set_run_visibility(
        runs: list[str],
        handle: int = 0,
        *,
        visible: bool = True,
        target_displays: list[str] | None = None,
        allow_foreground: bool = True,
    ) -> SetRunVisibilityResult:
        """Control visibility (show/hide) of specific runs on displays.

        Args:
            runs: List of run names (e.g. ['Run #1', 'Run #2']).
            handle: Capstone main window handle (0 for active window).
            visible: Whether to make the specified runs visible (True) or hidden (False).
            target_displays: Specific display names to filter, or None for all displays.
            allow_foreground: Bring window to foreground for UI automation.

        Returns:
            SetRunVisibilityResult with list of currently visible runs.
        """
        return SetRunVisibilityResult.model_validate(
            await native(
                NativeRequest(
                    operation="set_run_visibility",
                    handle=handle,
                    runs=runs,
                    visible=visible,
                    target_displays=target_displays,
                    allow_foreground=allow_foreground,
                ),
                mutates=True,
            ),
        )

    @mcp.tool()
    async def capstone_add_page(
        handle: int = 0,
        *,
        title: str = "New Page",
        allow_foreground: bool = True,
    ) -> AddPageResult:
        """Add a new page tab to the Capstone workbook.

        Args:
            handle: Capstone main window handle (0 for active window).
            title: Title/name for the newly added page tab.
            allow_foreground: Bring window to foreground for UI automation.

        Returns:
            AddPageResult with page_index, title, and total pages count.
        """
        return AddPageResult.model_validate(
            await native(
                NativeRequest(
                    operation="add_page",
                    handle=handle,
                    title=title,
                    allow_foreground=allow_foreground,
                ),
                mutates=True,
            ),
        )

    @mcp.tool()
    async def capstone_set_page_layout(
        layout: PageLayoutTemplate = "two_vertical",
        handle: int = 0,
        *,
        page_name: str | None = None,
        allow_foreground: bool = True,
    ) -> SetPageLayoutResult:
        """Apply a multi-display split layout template to the active or target page.

        Args:
            layout: Split template ('two_vertical', 'two_horizontal',
                'three_pane', 'four_grid').
            handle: Capstone main window handle (0 for active window).
            page_name: Specific page name to layout (None targets active page).
            allow_foreground: Bring window to foreground for UI automation.

        Returns:
            SetPageLayoutResult with layout template and display placeholders.
        """
        return SetPageLayoutResult.model_validate(
            await native(
                NativeRequest(
                    operation="set_page_layout",
                    handle=handle,
                    layout=layout,
                    page_name=page_name,
                    allow_foreground=allow_foreground,
                ),
                mutates=True,
            ),
        )

    return {
        "capstone_create_graph": capstone_create_graph,
        "capstone_select_graph_measurement": capstone_select_graph_measurement,
        "capstone_observe_graph": capstone_observe_graph,
        "capstone_graph_recovery": capstone_graph_recovery,
        "capstone_graph_report": capstone_graph_report,
        "capstone_read_graph": capstone_read_graph,
        "capstone_fit_models": capstone_fit_models,
        "capstone_set_graph_fits": capstone_set_graph_fits,
        "capstone_analyze_graph": capstone_analyze_graph,
        "capstone_fit_graph": capstone_fit_graph,
        "capstone_toggle_graph_statistics": capstone_toggle_graph_statistics,
        "capstone_measure_graph_area": capstone_measure_graph_area,
        "capstone_graph_delta": capstone_graph_delta,
        "capstone_create_table": capstone_create_table,
        "capstone_set_table_columns": capstone_set_table_columns,
        "capstone_read_table": capstone_read_table,
        "capstone_create_digits": capstone_create_digits,
        "capstone_rename_run": capstone_rename_run,
        "capstone_delete_run": capstone_delete_run,
        "capstone_set_run_visibility": capstone_set_run_visibility,
        "capstone_add_page": capstone_add_page,
        "capstone_set_page_layout": capstone_set_page_layout,
    }

