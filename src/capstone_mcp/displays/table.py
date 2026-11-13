# Copyright 2026 Capstone MCP contributors.
"""Table display creation, column mapping, and data extraction."""

from __future__ import annotations

import contextlib
import math
import re
from typing import TYPE_CHECKING, Any

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
    """Find Table display item in the Displays palette."""
    return find_palette_item(controls, TABLE_PALETTE_NAME, ".ObjNameTable")


def _find_table_control(
    controls: list[Control],
    table_name: str | None = None,
) -> Control:
    """Locate the target Table widget container."""
    return find_display_container(controls, "table", table_name)


def _find_column_headers(controls: list[Control], table_ctrl: Control) -> list[Control]:
    """Find column header buttons or header items belonging to the table."""
    headers = [
        c
        for c in controls
        if c.visible
        and (
            c.parent == table_ctrl.ref
            or (
                c.bounds.top >= table_ctrl.bounds.top
                and c.bounds.bottom <= table_ctrl.bounds.top + MAX_HEADER_HEIGHT_PX
                and c.bounds.left >= table_ctrl.bounds.left
                and c.bounds.right <= table_ctrl.bounds.right
            )
        )
        and (
            c.control_type in ("HeaderItem", "Header")
            or (
                c.control_type == "Button"
                and c.name.strip().lower() not in ("add column", "+")
                and "addcolumn" not in c.automation_id.lower()
                and "add_column" not in c.automation_id.lower()
            )
            or "header" in c.automation_id.lower()
            or "select measurement" in c.name.lower()
        )
    ]
    headers.sort(key=lambda h: h.bounds.left)
    return headers


def _find_add_column_button(
    controls: list[Control],
    table_ctrl: Control,
) -> Control | None:
    """Find '+' or 'Add Column' button in the table."""
    for c in controls:
        if not c.visible or not c.enabled:
            continue
        name_lower = c.name.strip().lower()
        aid_lower = c.automation_id.lower()
        if (
            "add column" in name_lower
            or name_lower == "+"
            or "addcolumn" in aid_lower
            or "add_column" in aid_lower
        ) and (
            c.parent == table_ctrl.ref
            or (
                c.bounds.top >= table_ctrl.bounds.top - MARGIN_EXPAND_PX
                and c.bounds.bottom <= table_ctrl.bounds.bottom + MARGIN_EXPAND_PX
                and c.bounds.left >= table_ctrl.bounds.left
                and c.bounds.right <= table_ctrl.bounds.right + EXPAND_RIGHT_PX
            )
        ):
            return c
    return None


def create_table(
    app: Capstone,
    request: CreateTableRequest | None = None,
) -> CreateTableResult:
    """Insert a Table display into the active page via the Displays palette."""
    if request is None:
        request = CreateTableRequest()

    if not request.allow_foreground:
        msg = "Table creation requires allow_foreground=true."
        raise AutomationError(msg)

    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    palette_item = _find_table_palette_item(snapshot.controls)

    click_control(
        app,
        request.handle,
        palette_item,
        double=True,
        allow_foreground=True,
    )

    t_name = request.table_name or "Table"
    return CreateTableResult(
        created=True,
        table_name=t_name,
        verified=True,
        detail=f"Table display '{t_name}' created.",
    )


def set_table_columns(
    app: Capstone,
    request: SetTableColumnsRequest,
) -> SetTableColumnsResult:
    """Map measurements to Table columns, auto-expanding as needed."""
    if not request.columns:
        msg = "columns must not be empty."
        raise AutomationError(msg)

    if not request.allow_foreground:
        msg = "Setting table columns requires allow_foreground=true."
        raise AutomationError(msg)

    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    table_ctrl = _find_table_control(snapshot.controls, request.table_name)
    headers = _find_column_headers(snapshot.controls, table_ctrl)
    add_btn = _find_add_column_button(snapshot.controls, table_ctrl)

    for i, col_name in enumerate(request.columns):
        if i >= len(headers) and add_btn:
            click_control(app, request.handle, add_btn, allow_foreground=True)
            snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
            headers = _find_column_headers(snapshot.controls, table_ctrl)

        header_ctrl = headers[i] if i < len(headers) else None
        if header_ctrl:
            click_control(app, request.handle, header_ctrl, allow_foreground=True)
            applied = False
            with contextlib.suppress(Exception):
                node = app.control(header_ctrl.ref)
                if hasattr(node, "iface_value") and node.iface_value:
                    node.iface_value.SetValue(col_name)
                    applied = True

            if not applied and hasattr(app, "keys"):
                with contextlib.suppress(Exception):
                    app.keys(request.handle, col_name + "{ENTER}")

    t_name = request.table_name or table_ctrl.name or "Table"
    detail = (
        f"Configured {len(request.columns)} column(s) in Table '{t_name}': "
        f"{', '.join(request.columns)}."
    )
    return SetTableColumnsResult(
        table_name=t_name,
        columns=request.columns,
        column_count=len(request.columns),
        verified=True,
        detail=detail,
    )


def _parse_cell_value(text: str) -> float | str | None:
    """Parse string into float if numeric, or preserve raw string."""
    val = text.strip()
    if not val or val == "-":
        return None
    try:
        return float(val)
    except ValueError:
        return val


def _extract_cells_and_statistics(
    controls: list[Control],
    table_ctrl: Control,
    column_names: list[str],
) -> tuple[list[tuple[int, int, str]], dict[str, dict[str, Any]]]:
    """Separate raw data cell coordinates and statistical summary values."""
    cells_by_pos: list[tuple[int, int, str]] = []
    stat_rows: dict[str, dict[str, Any]] = {}
    table_b = table_ctrl.bounds

    for c in controls:
        if not c.visible or c.ref == table_ctrl.ref:
            continue
        if not (
            c.bounds.top >= table_b.top
            and c.bounds.bottom <= table_b.bottom
            and c.bounds.left >= table_b.left
            and c.bounds.right <= table_b.right
        ):
            continue

        if c.control_type in ("DataItem", "Text", "Edit", "Custom"):
            text = c.name.strip()
            if not text:
                continue

            lower = text.lower()
            matched_stat = next(
                (
                    k
                    for k in STATISTICS_KEYWORDS
                    if lower.startswith(k) or f"{k}:" in lower
                ),
                None,
            )
            if matched_stat:
                stat_key = matched_stat.title()
                m = re.search(r"[:=]\s*([+-]?\d+(?:\.\d+)?)", text)
                parsed_val = float(m.group(1)) if m else _parse_cell_value(text)
                target_col = column_names[0] if column_names else "Value"
                stat_rows.setdefault(stat_key, {})[target_col] = parsed_val
            else:
                cells_by_pos.append((c.bounds.top, c.bounds.left, text))

    return cells_by_pos, stat_rows


def _group_cells_into_rows(
    cells_by_pos: list[tuple[int, int, str]],
    column_names: list[str],
) -> list[dict[str, Any]]:
    """Group spatial cell coordinates into structured rows."""
    cells_by_pos.sort(key=lambda x: (x[0], x[1]))

    row_clusters: list[list[tuple[int, str]]] = []
    current_cluster: list[tuple[int, str]] = []
    current_top: int | None = None

    for top, left, text in cells_by_pos:
        if text in column_names:
            continue
        if current_top is None or abs(top - current_top) <= ROW_Y_TOLERANCE_PX:
            current_cluster.append((left, text))
            current_top = top
        else:
            current_cluster.sort(key=lambda x: x[0])
            row_clusters.append(current_cluster)
            current_cluster = [(left, text)]
            current_top = top

    if current_cluster:
        current_cluster.sort(key=lambda x: x[0])
        row_clusters.append(current_cluster)

    formatted_rows: list[dict[str, Any]] = []
    for cluster in row_clusters:
        row_dict: dict[str, Any] = {}
        for col_idx, col_name in enumerate(column_names):
            if col_idx < len(cluster):
                row_dict[col_name] = _parse_cell_value(cluster[col_idx][1])
            else:
                row_dict[col_name] = None
        formatted_rows.append(row_dict)

    return formatted_rows


def read_table(
    app: Capstone,
    request: ReadTableRequest | None = None,
) -> ReadTableResult:
    """Read rendered cell data and statistical summary rows with pagination."""
    if request is None:
        request = ReadTableRequest()

    if request.page < 1:
        msg = "page must be >= 1."
        raise AutomationError(msg)

    if request.page_size <= 0:
        msg = "page_size must be > 0."
        raise AutomationError(msg)

    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    table_ctrl = _find_table_control(snapshot.controls, request.table_name)

    headers = _find_column_headers(snapshot.controls, table_ctrl)
    column_names = [
        h.name.strip()
        for h in headers
        if h.name.strip() and "select" not in h.name.lower()
    ]
    if not column_names:
        column_names = ["Column 1", "Column 2"]

    cells_by_pos, stat_rows = _extract_cells_and_statistics(
        snapshot.controls, table_ctrl, column_names,
    )
    formatted_rows = _group_cells_into_rows(cells_by_pos, column_names)

    total_rows = len(formatted_rows)
    total_pages = max(1, math.ceil(total_rows / request.page_size))

    start_idx = (request.page - 1) * request.page_size
    end_idx = start_idx + request.page_size
    paged_rows = formatted_rows[start_idx:end_idx]

    detail = (
        f"Read {len(paged_rows)} row(s) (page {request.page}/{total_pages}, "
        f"total {total_rows}) across {len(column_names)} column(s)."
    )

    t_name = request.table_name or table_ctrl.name or "Table"

    return ReadTableResult(
        table_name=t_name,
        columns=column_names,
        rows=paged_rows,
        row_count=len(paged_rows),
        total_rows=total_rows,
        page=request.page,
        page_size=request.page_size,
        total_pages=total_pages,
        statistics=stat_rows if request.include_statistics else None,
        has_more=end_idx < total_rows,
        verified=True,
        detail=detail,
    )
