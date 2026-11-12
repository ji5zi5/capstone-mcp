# Copyright 2026 Capstone MCP contributors.
"""High-level Table display creation, column mapping, and data extraction."""

import contextlib
import math
import re
from typing import Any, Final

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.models import Action, Control, Model

TABLE_PALETTE_NAME: Final = "Table"
ROW_Y_TOLERANCE_PX: Final = 5
MAX_HEADER_HEIGHT_PX: Final = 100
MARGIN_EXPAND_PX: Final = 50
EXPAND_RIGHT_PX: Final = 100

STATISTICS_KEYWORDS: Final = (
    "mean",
    "std dev",
    "stddev",
    "standard deviation",
    "minimum",
    "min",
    "maximum",
    "max",
    "count",
    "sum",
    "total",
)


class CreateTableRequest(Model):
    """Specification for inserting a Table display widget."""

    handle: int = 0
    table_name: str | None = None
    allow_foreground: bool = True


class CreateTableResult(Model):
    """Outcome of Table display creation."""

    created: bool = True
    table_name: str = "Table"
    verified: bool = True
    detail: str = ""


class SetTableColumnsRequest(Model):
    """Specification of columns/measurements to bind in a Table display."""

    columns: list[str]
    handle: int = 0
    table_name: str | None = None
    allow_foreground: bool = True


class SetTableColumnsResult(Model):
    """Outcome of Table column configuration."""

    table_name: str
    columns: list[str]
    column_count: int
    verified: bool = True
    detail: str = ""


class ReadTableRequest(Model):
    """Specification for extracting cell data and statistics from a Table."""

    handle: int = 0
    table_name: str | None = None
    page: int = 1
    page_size: int = 50
    include_statistics: bool = True
    allow_foreground: bool = True


class ReadTableResult(Model):
    """Extracted Table contents, supporting pagination and summary statistics."""

    columns: list[str]
    rows: list[dict[str, Any]]
    total_rows: int
    page: int
    page_size: int
    total_pages: int
    statistics: dict[str, dict[str, Any]] | None = None
    detail: str = ""


def _click(
    app: Capstone,
    handle: int,
    ctrl: Control,
    *,
    double: bool = False,
    allow_foreground: bool = True,
) -> None:
    """Deliver a click or double-click compatible with real app and mocks."""
    if hasattr(app, "click"):
        app.click(handle, ctrl.ref, allow_foreground=allow_foreground)
        return
    with contextlib.suppress(Exception):
        node = app.control(ctrl.ref)
        if double:
            b = ctrl.bounds
            coords = ((b.left + b.right) // 2, (b.top + b.bottom) // 2)
            node.click_input(button="left", double=True, coords=coords, absolute=True)
            return
        if hasattr(node, "invoke") and callable(node.invoke):
            node.invoke()
            return
    app.act(handle, Action.INVOKE, ref=ctrl.ref, allow_foreground=allow_foreground)


def _find_table_palette_item(controls: list[Control]) -> Control:
    """Find Table display item in the Displays palette."""
    matches = [
        c
        for c in controls
        if c.visible
        and c.enabled
        and (
            c.name.strip() == TABLE_PALETTE_NAME
            or c.name.strip().lower() == "table"
            or c.automation_id.endswith(".ObjNameTable")
            or "table" in c.automation_id.lower()
        )
        and c.control_type in ("Text", "Button", "ListItem", "TreeItem", "Custom")
    ]
    if not matches:
        msg = "Table display palette item not found in window snapshot."
        raise AutomationError(msg)
    return matches[0]


def _find_table_control(
    controls: list[Control],
    table_name: str | None = None,
) -> Control:
    """Locate the target Table widget container."""
    if table_name:
        t_lower = table_name.strip().lower()
        for ctrl in controls:
            if ctrl.visible and (
                t_lower == ctrl.name.strip().lower()
                or t_lower in ctrl.automation_id.lower()
            ):
                return ctrl
        msg = f"Table control matching '{table_name}' not found."
        raise AutomationError(msg)

    # Search for DataGrid, Table, or Pane/Custom representing table
    for ctrl in controls:
        if ctrl.visible and ctrl.control_type in ("Table", "DataGrid"):
            return ctrl

    for ctrl in controls:
        if (
            ctrl.visible
            and ctrl.control_type in ("Pane", "Custom", "Group")
            and "table" in ctrl.name.lower()
        ):
            return ctrl

    for ctrl in controls:
        if (
            ctrl.visible
            and "table" in ctrl.automation_id.lower()
            and ctrl.control_type in ("Pane", "Custom", "Group")
        ):
            return ctrl

    msg = "No Table display found in the active window."
    raise AutomationError(msg)


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

    _click(app, request.handle, palette_item, double=True, allow_foreground=True)

    t_name = request.table_name or "Table"
    return CreateTableResult(
        created=True,
        table_name=t_name,
        verified=True,
        detail=f"Table display '{t_name}' created on active page.",
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
            _click(app, request.handle, add_btn, allow_foreground=True)
            snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
            headers = _find_column_headers(snapshot.controls, table_ctrl)

        header_ctrl = headers[i] if i < len(headers) else None
        if header_ctrl:
            _click(app, request.handle, header_ctrl, allow_foreground=True)

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
    return SetTableColumnsResult(
        table_name=t_name,
        columns=request.columns,
        column_count=len(request.columns),
        verified=True,
        detail=f"Configured {len(request.columns)} column(s) on table '{t_name}'.",
    )


def _parse_cell_value(val_str: str) -> str | float | None:
    """Parse string representation of a cell value into float or str."""
    val = val_str.strip()
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

    return ReadTableResult(
        columns=column_names,
        rows=paged_rows,
        total_rows=total_rows,
        page=request.page,
        page_size=request.page_size,
        total_pages=total_pages,
        statistics=stat_rows if request.include_statistics else None,
        detail=detail,
    )
