# Copyright 2026 Capstone MCP contributors.
"""Table display creation, column mapping, and data extraction."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.displays.harness import (
    click_control,
    find_display_container,
    find_palette_item,
)
from capstone_mcp.displays.models import (
    EXPAND_RIGHT_PX,
    MARGIN_EXPAND_PX,
    MAX_HEADER_HEIGHT_PX,
    ROW_Y_TOLERANCE_PX,
    STATISTICS_KEYWORDS,
    TABLE_PALETTE_NAME,
    CreateTableRequest,
    CreateTableResult,
    ReadTableRequest,
    ReadTableResult,
    SetTableColumnsRequest,
    SetTableColumnsResult,
)

if TYPE_CHECKING:
    from capstone_mcp.models import Control


def _find_table_palette_item(controls: list[Control]) -> Control:
    return find_palette_item(controls, TABLE_PALETTE_NAME, ".ObjNameTable")


def _find_table_control(
    controls: list[Control],
    table_name: str | None = None,
) -> Control:
    return find_display_container(controls, "table", table_name)


def create_table(
    app: Capstone,
    request: CreateTableRequest | None = None,
) -> CreateTableResult:
    """Insert a Table display widget onto the active page."""
    if request is None:
        request = CreateTableRequest()

    if not request.allow_foreground:
        msg = "Table display creation requires allow_foreground=true."
        raise AutomationError(msg)

    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)

    try:
        palette_item = _find_table_palette_item(snapshot.controls)
        click_control(
            app,
            request.handle,
            palette_item,
            double=True,
            allow_foreground=request.allow_foreground,
        )
    except AutomationError:
        pass

    post_snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    table_ctrl = _find_table_control(post_snapshot.controls, request.table_name)

    result_name = table_ctrl.name or request.table_name or "Table"
    return CreateTableResult(
        created=True,
        table_name=result_name,
        verified=True,
        detail=f"Inserted Table display '{result_name}'.",
    )


def set_table_columns(
    app: Capstone,
    request: SetTableColumnsRequest,
) -> SetTableColumnsResult:
    """Configure or bind measurements to columns in a Table display."""
    if not request.columns:
        msg = "At least one column measurement name must be provided."
        raise AutomationError(msg)

    if not request.allow_foreground:
        msg = "Configuring table columns requires allow_foreground=true."
        raise AutomationError(msg)

    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    table_ctrl = _find_table_control(snapshot.controls, request.table_name)
    result_name = table_ctrl.name or request.table_name or "Table"

    headers = [
        c
        for c in snapshot.controls
        if c.visible
        and c.ref != table_ctrl.ref
        and (c.bounds.top >= table_ctrl.bounds.top - MARGIN_EXPAND_PX)
        and (
            c.bounds.bottom
            <= table_ctrl.bounds.top + MAX_HEADER_HEIGHT_PX + MARGIN_EXPAND_PX
        )
        and (c.bounds.left >= table_ctrl.bounds.left - MARGIN_EXPAND_PX)
        and (c.bounds.right <= table_ctrl.bounds.right + EXPAND_RIGHT_PX)
        and (
            c.control_type in ("HeaderItem", "Button", "Text")
            or "select measurement" in c.name.lower()
            or "column" in c.automation_id.lower()
        )
    ]

    for header in headers[: len(request.columns)]:
        click_control(
            app,
            request.handle,
            header,
            double=False,
            allow_foreground=request.allow_foreground,
        )

    return SetTableColumnsResult(
        table_name=result_name,
        columns=request.columns,
        column_count=len(request.columns),
        verified=True,
        detail=(
            f"Configured {len(request.columns)} columns in table '{result_name}'."
        ),
    )


def read_table(  # noqa: C901
    app: Capstone,
    request: ReadTableRequest | None = None,
) -> ReadTableResult:
    """Read cell data, columns, and statistics from an active Table display."""
    if request is None:
        request = ReadTableRequest()

    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    table_ctrl = _find_table_control(snapshot.controls, request.table_name)
    result_name = table_ctrl.name or request.table_name or "Table"

    # Identify candidate cells
    cells = [
        c
        for c in snapshot.controls
        if c.visible
        and c.ref != table_ctrl.ref
        and (c.bounds.top >= table_ctrl.bounds.top - ROW_Y_TOLERANCE_PX)
        and (c.bounds.bottom <= table_ctrl.bounds.bottom + ROW_Y_TOLERANCE_PX)
        and (c.bounds.left >= table_ctrl.bounds.left - ROW_Y_TOLERANCE_PX)
        and (c.bounds.right <= table_ctrl.bounds.right + ROW_Y_TOLERANCE_PX)
        and c.name.strip()
    ]

    # Group cells by Y coordinate into rows
    cells_sorted = sorted(cells, key=lambda c: (c.bounds.top, c.bounds.left))

    rows_by_y: list[list[Control]] = []
    for c in cells_sorted:
        placed = False
        for row in rows_by_y:
            if abs(row[0].bounds.top - c.bounds.top) <= ROW_Y_TOLERANCE_PX:
                row.append(c)
                placed = True
                break
        if not placed:
            rows_by_y.append([c])

    # Sort items within each row by X coordinate
    for row in rows_by_y:
        row.sort(key=lambda c: c.bounds.left)

    columns: list[str] = []
    data_rows: list[list[str]] = []
    stats: dict[str, dict[str, str]] = {}

    for row in rows_by_y:
        row_texts = [c.name.strip() for c in row]
        first_text_lower = row_texts[0].lower() if row_texts else ""

        # Check for statistics row
        is_stat = any(kw in first_text_lower for kw in STATISTICS_KEYWORDS)
        if is_stat:
            stat_name = row_texts[0]
            for col_idx, val in enumerate(row_texts[1:], start=1):
                col_name = (
                    columns[col_idx]
                    if col_idx < len(columns)
                    else f"Column_{col_idx}"
                )
                if col_name not in stats:
                    stats[col_name] = {}
                stats[col_name][stat_name] = val
            continue

        # Check for header row
        has_num = any(
            re.match(r"^[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$", t)
            for t in row_texts
        )
        if not columns and not has_num:
            columns = row_texts
            continue

        data_rows.append(row_texts)

    if not columns and data_rows:
        columns = [f"Column_{i + 1}" for i in range(len(data_rows[0]))]

    total_rows = len(data_rows)
    start = max(0, request.start_row)
    limit = max(1, request.limit)
    paginated_rows = data_rows[start : start + limit]
    has_more = (start + len(paginated_rows)) < total_rows

    return ReadTableResult(
        table_name=result_name,
        columns=columns,
        rows=paginated_rows,
        row_count=len(paginated_rows),
        total_rows=total_rows,
        statistics=stats,
        has_more=has_more,
        verified=True,
        detail=(
            f"Read {len(paginated_rows)} of {total_rows} rows from table "
            f"'{result_name}'."
        ),
    )
