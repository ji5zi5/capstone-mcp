# Copyright 2026 Capstone MCP contributors.
"""Tool router for graphs, tables, digits displays, and workbook pages."""

from collections.abc import Awaitable, Callable
from typing import Any, Final, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, ImageContent, TextContent, ToolAnnotations
from pydantic import JsonValue, TypeAdapter

from capstone_mcp.automation_models import NativeRequest
from capstone_mcp.displays import (
    AddPageRequest,
    AddPageResult,
    CreateDigitsRequest,
    CreateDigitsResult,
    CreateTableRequest,
    CreateTableResult,
    DisplayAction,
    DisplayRequest,
    DisplayResult,
    PageLayoutTemplate,
    ReadTableRequest,
    ReadTableResult,
    SetPageLayoutRequest,
    SetPageLayoutResult,
    SetTableColumnsRequest,
    SetTableColumnsResult,
)
from capstone_mcp.graphs import (
    AnalyzeGraphRequest,
    CreateGraphRequest,
    FitGraphRequest,
    FitGraphResult,
    FitModel,
    GraphAction,
    GraphAnalysisReport,
    GraphCapture,
    GraphDeltaRequest,
    GraphDeltaResult,
    GraphFailure,
    GraphFitOutcome,
    GraphFitRequest,
    GraphRequest,
    GraphResult,
    GraphState,
    MeasureGraphAreaRequest,
    MeasureGraphAreaResult,
    ReadGraphRequest,
    ToggleGraphStatisticsRequest,
    ToggleGraphStatisticsResult,
    summarize_graph,
)
from capstone_mcp.models import Point, Result

type NativeCaller = Callable[..., Awaitable[Any]]
DEFAULT_FIT_OFFSET: Final = Point(x=20, y=20)
JSON_VALUE: Final = TypeAdapter(JsonValue)


def register_display_tools(  # noqa: PLR0915
    mcp: FastMCP,
    native: NativeCaller,
    get_last_failure: Callable[[], GraphFailure | None] | None = None,
) -> dict[str, Any]:
    """Register all graph, table, digits, and display layout tools."""

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Unified graph management seam",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def capstone_manage_graph(
        request: GraphRequest,
    ) -> GraphResult:
        """Unified entry point for all Capstone graph display operations.

        Supported actions (request.action):
        - create: Insert a new graph onto active page (request.create)
        - read: Read graph curves, fits, and data signatures (request.read)
        - fit: Scale graph axes to fit all data (request.fit)
        - select_measurement: Select axis measurement via popup menu path
          (request.select_measurement)
        - toolbox_delta: Measure coordinates difference with delta crosshair
          (request.toolbox_delta)
        - toolbox_area: Integrate area under curve with area tool
          (request.toolbox_area)
        - toolbox_statistics: Toggle statistics box and read summary stats
          (request.toolbox_statistics)
        - analyze: Set axes, fit curves, and compile analytical report
          (request.analyze)
        """
        return GraphResult.model_validate(
            await native(
                NativeRequest(
                    operation="manage_graph",
                    graph_request=JSON_VALUE.validate_json(
                        request.model_dump_json(),
                    ),
                ),
                mutates=request.action != GraphAction.READ,
            ),
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Unified display and workbook management seam",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def capstone_manage_display(
        request: DisplayRequest,
    ) -> DisplayResult:
        """Unified entry point for all Capstone display and workbook operations.

        Supported actions (request.action):
        - create_digits: Insert Digits display and monitor numeric readout
        - create_table: Insert Table display widget on active page
        - set_table_columns: Configure measurement columns for Table display
        - read_table: Extract tabular rows, pagination, and statistics
        - create_scope: Insert Oscilloscope display widget
        - set_scope_trigger: Configure scope hardware trigger level/slope/mode
        - create_fft: Insert FFT frequency spectrum display
        - read_fft_peaks: Read detected spectral peak frequencies and amplitudes
        - add_page: Add a new workbook page tab
        - set_page_layout: Apply multi-display split grid layout template
        """
        return DisplayResult.model_validate(
            await native(
                NativeRequest(
                    operation="manage_display",
                    display_request=JSON_VALUE.validate_json(
                        request.model_dump_json(),
                    ),
                ),
                mutates=request.action not in (
                    DisplayAction.READ_TABLE,
                    DisplayAction.READ_FFT_PEAKS,
                ),
            ),
        )

    async def capstone_create_graph(
        handle: int,
        *,
        allow_foreground: bool = True,
    ) -> Result:
        """Insert a real graph into the active Capstone page, not a standalone PNG.

        Delegates to capstone_manage_graph(action='create').
        """
        req = GraphRequest(
            action=GraphAction.CREATE,
            create=CreateGraphRequest(
                handle=handle,
                allow_foreground=allow_foreground,
            ),
        )
        res = await capstone_manage_graph(req)
        return Result(
            detail=res.create.detail if res.create else "Graph created",
            delivered=True,
        )

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

    def capstone_graph_recovery() -> GraphFailure | None:
        """Read failure stage, confirmed steps and safe next action without replay.

        This is the last graph failure, not a claim about a later successful call.
        Correlate request_id and operation. If graph_input_may_have_been_sent is true,
        inspect the app before another write; never automatically replay the request.
        """
        if get_last_failure is not None:
            return get_last_failure()
        return None

    async def capstone_graph_report(
        handle: int,
        *,
        allow_foreground: bool = True,
    ) -> GraphAnalysisReport:
        """Read a selected graph and group fit comparisons by exact renderer/run/units.

        Delegates to capstone_read_graph and summarizes.
        """
        state = await capstone_read_graph(
            handle,
            allow_foreground=allow_foreground,
        )
        return summarize_graph(state)

    async def capstone_read_graph(
        handle: int,
        *,
        allow_foreground: bool = True,
    ) -> GraphState:
        """Read selected graph's actual models, native coefficients and run/unit IDs.

        Delegates to capstone_manage_graph(action='read').
        """
        req = GraphRequest(
            action=GraphAction.READ,
            read=ReadGraphRequest(
                handle=handle,
                allow_foreground=allow_foreground,
            ),
        )
        res = await capstone_manage_graph(req)
        if res.read is None:
            msg = "Expected read result from manage_graph"
            raise RuntimeError(msg)
        return res.read.state

    def capstone_fit_models() -> list[FitModel]:
        """List supported built-in native models; custom-expression editing is excluded."""
        return list(FitModel)

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

    async def capstone_analyze_graph(
        handle: int,
        request: AnalyzeGraphRequest,
    ) -> GraphFitOutcome:
        """Configure optional X/Y axes, apply model choices, and read native results.

        Delegates to capstone_manage_graph(action='analyze').
        """
        if handle and request.handle != handle:
            request = request.model_copy(update={"handle": handle})
        req = GraphRequest(
            action=GraphAction.ANALYZE,
            analyze=request,
        )
        res = await capstone_manage_graph(req)
        if res.analyze is None:
            msg = "Expected analyze result from manage_graph"
            raise RuntimeError(msg)
        return res.analyze.outcome

    async def capstone_fit_graph(
        handle: int = 0,
        *,
        mode: Literal["scale_to_fit", "manual_bounds"] = "scale_to_fit",
        graph_name: str | None = None,
        offset: Point = DEFAULT_FIT_OFFSET,
        allow_foreground: bool = True,
    ) -> FitGraphResult:
        """Scale graph axes to fit all data or adjust bounds deterministically.

        Delegates to capstone_manage_graph(action='fit').
        """
        req = GraphRequest(
            action=GraphAction.FIT,
            fit=FitGraphRequest(
                handle=handle,
                mode=mode,
                graph_name=graph_name,
                offset=offset,
                allow_foreground=allow_foreground,
            ),
        )
        res = await capstone_manage_graph(req)
        if res.fit is None:
            msg = "Expected fit result from manage_graph"
            raise RuntimeError(msg)
        return res.fit

    async def capstone_toggle_graph_statistics(
        handle: int = 0,
        *,
        graph_name: str | None = None,
        enable: bool | None = None,
        allow_foreground: bool = True,
    ) -> ToggleGraphStatisticsResult:
        """Toggle graph statistics box (Σ) and read descriptive statistics.

        Delegates to capstone_manage_graph(action='toolbox_statistics').
        """
        req = GraphRequest(
            action=GraphAction.TOOLBOX_STATISTICS,
            toolbox_statistics=ToggleGraphStatisticsRequest(
                handle=handle,
                graph_name=graph_name,
                enable=enable,
                allow_foreground=allow_foreground,
            ),
        )
        res = await capstone_manage_graph(req)
        if res.toolbox_statistics is None:
            msg = "Expected toolbox_statistics result from manage_graph"
            raise RuntimeError(msg)
        return res.toolbox_statistics

    async def capstone_measure_graph_area(
        handle: int = 0,
        *,
        graph_name: str | None = None,
        enable: bool | None = None,
        allow_foreground: bool = True,
    ) -> MeasureGraphAreaResult:
        """Toggle graph area integration tool (∫ydx) and extract integral value.

        Delegates to capstone_manage_graph(action='toolbox_area').
        """
        req = GraphRequest(
            action=GraphAction.TOOLBOX_AREA,
            toolbox_area=MeasureGraphAreaRequest(
                handle=handle,
                graph_name=graph_name,
                enable=enable,
                allow_foreground=allow_foreground,
            ),
        )
        res = await capstone_manage_graph(req)
        if res.toolbox_area is None:
            msg = "Expected toolbox_area result from manage_graph"
            raise RuntimeError(msg)
        return res.toolbox_area

    async def capstone_graph_delta(
        handle: int = 0,
        *,
        graph_name: str | None = None,
        point1: Point | None = None,
        point2: Point | None = None,
        allow_foreground: bool = True,
    ) -> GraphDeltaResult:
        """Activate delta crosshair tool and read coordinate differences (Δx, Δy).

        Delegates to capstone_manage_graph(action='toolbox_delta').
        """
        req = GraphRequest(
            action=GraphAction.TOOLBOX_DELTA,
            toolbox_delta=GraphDeltaRequest(
                handle=handle,
                graph_name=graph_name,
                point1=point1,
                point2=point2,
                allow_foreground=allow_foreground,
            ),
        )
        res = await capstone_manage_graph(req)
        if res.toolbox_delta is None:
            msg = "Expected toolbox_delta result from manage_graph"
            raise RuntimeError(msg)
        return res.toolbox_delta

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
        res = await capstone_manage_display(
            DisplayRequest(
                action=DisplayAction.CREATE_TABLE,
                create_table=CreateTableRequest(
                    handle=handle,
                    table_name=table_name,
                    allow_foreground=allow_foreground,
                ),
            ),
        )
        if res.create_table is None:
            msg = "Expected create_table result from manage_display"
            raise RuntimeError(msg)
        return res.create_table

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
        res = await capstone_manage_display(
            DisplayRequest(
                action=DisplayAction.SET_TABLE_COLUMNS,
                set_table_columns=SetTableColumnsRequest(
                    handle=handle,
                    columns=columns,
                    table_name=table_name,
                    allow_foreground=allow_foreground,
                ),
            ),
        )
        if res.set_table_columns is None:
            msg = "Expected set_table_columns result from manage_display"
            raise RuntimeError(msg)
        return res.set_table_columns

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
        res = await capstone_manage_display(
            DisplayRequest(
                action=DisplayAction.READ_TABLE,
                read_table=ReadTableRequest(
                    handle=handle,
                    table_name=table_name,
                    page=page,
                    page_size=page_size,
                    include_statistics=include_statistics,
                    allow_foreground=allow_foreground,
                ),
            ),
        )
        if res.read_table is None:
            msg = "Expected read_table result from manage_display"
            raise RuntimeError(msg)
        return res.read_table

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
        res = await capstone_manage_display(
            DisplayRequest(
                action=DisplayAction.CREATE_DIGITS,
                create_digits=CreateDigitsRequest(
                    handle=handle,
                    measurement=measurement,
                    digits_name=digits_name,
                    allow_foreground=allow_foreground,
                ),
            ),
        )
        if res.create_digits is None:
            msg = "Expected create_digits result from manage_display"
            raise RuntimeError(msg)
        return res.create_digits

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
        res = await capstone_manage_display(
            DisplayRequest(
                action=DisplayAction.ADD_PAGE,
                add_page=AddPageRequest(
                    handle=handle,
                    title=title,
                    allow_foreground=allow_foreground,
                ),
            ),
        )
        if res.add_page is None:
            msg = "Expected add_page result from manage_display"
            raise RuntimeError(msg)
        return res.add_page

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
        res = await capstone_manage_display(
            DisplayRequest(
                action=DisplayAction.SET_PAGE_LAYOUT,
                set_page_layout=SetPageLayoutRequest(
                    handle=handle,
                    layout=layout,
                    page_name=page_name,
                    allow_foreground=allow_foreground,
                ),
            ),
        )
        if res.set_page_layout is None:
            msg = "Expected set_page_layout result from manage_display"
            raise RuntimeError(msg)
        return res.set_page_layout

    return {
        "capstone_manage_display": capstone_manage_display,
        "capstone_manage_graph": capstone_manage_graph,
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
        "capstone_add_page": capstone_add_page,
        "capstone_set_page_layout": capstone_set_page_layout,
    }

