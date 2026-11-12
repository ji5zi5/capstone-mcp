# Copyright 2026 Capstone MCP contributors.
"""Tests for high-level Table display creation, column mapping, and reading."""

from unittest.mock import MagicMock

import pytest

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.models import Bounds, Control, Snapshot, Window
from capstone_mcp.table_display import (
    CreateTableRequest,
    CreateTableResult,
    ReadTableRequest,
    ReadTableResult,
    SetTableColumnsRequest,
    SetTableColumnsResult,
    create_table,
    read_table,
    set_table_columns,
)


def _mock_window(handle: int = 100) -> Window:
    return Window(
        handle=handle,
        title="Capstone",
        process_id=1,
        bounds=Bounds(left=0, top=0, right=1200, bottom=900),
    )


def test_create_table_refuses_disabled_foreground() -> None:
    app = Capstone()
    req = CreateTableRequest(handle=100, allow_foreground=False)
    with pytest.raises(AutomationError, match="allow_foreground=true"):
        create_table(app, req)


def test_create_table_raises_when_palette_item_missing() -> None:
    app = Capstone()
    mock_win = _mock_window()
    app.snapshot = MagicMock(
        return_value=Snapshot(
            window=mock_win,
            controls=[
                Control(
                    ref="ref:other",
                    parent=None,
                    name="Graph",
                    control_type="Text",
                    automation_id="Palette.Graph",
                    enabled=True,
                    visible=True,
                    bounds=Bounds(left=10, top=10, right=50, bottom=50),
                ),
            ],
            truncated=False,
        ),
    )
    with pytest.raises(AutomationError, match="Table display palette item not found"):
        create_table(app, CreateTableRequest(handle=100))


def test_create_table_success() -> None:
    app = Capstone()
    mock_win = _mock_window()
    table_item = Control(
        ref="ref:table_palette",
        parent=None,
        name="Table",
        control_type="Text",
        automation_id="Palette.ObjNameTable",
        enabled=True,
        visible=True,
        bounds=Bounds(left=10, top=100, right=60, bottom=130),
    )
    app.snapshot = MagicMock(
        return_value=Snapshot(
            window=mock_win,
            controls=[table_item],
            truncated=False,
        ),
    )
    app.click = MagicMock()

    result = create_table(app, CreateTableRequest(handle=100))
    assert isinstance(result, CreateTableResult)
    assert result.created is True
    assert result.table_name == "Table"
    assert result.verified is True
    app.click.assert_called_once_with(100, "ref:table_palette", allow_foreground=True)


def test_set_table_columns_validates_inputs() -> None:
    app = Capstone()
    with pytest.raises(AutomationError, match="columns must not be empty"):
        set_table_columns(app, SetTableColumnsRequest(columns=[], handle=100))

    with pytest.raises(AutomationError, match="allow_foreground=true"):
        set_table_columns(
            app,
            SetTableColumnsRequest(
                columns=["Time (s)"],
                handle=100,
                allow_foreground=False,
            ),
        )


def test_set_table_columns_configures_and_auto_expands() -> None:
    app = Capstone()
    mock_win = _mock_window()

    table_ctrl = Control(
        ref="ref:table",
        parent=None,
        name="Table 1",
        control_type="Table",
        automation_id="TableWidget",
        enabled=True,
        visible=True,
        bounds=Bounds(left=100, top=100, right=600, bottom=500),
    )
    header_1 = Control(
        ref="ref:h1",
        parent="ref:table",
        name="<Select Measurement>",
        control_type="Button",
        automation_id="Header_0",
        enabled=True,
        visible=True,
        bounds=Bounds(left=100, top=100, right=250, bottom=130),
    )
    add_col_btn = Control(
        ref="ref:add_col",
        parent="ref:table",
        name="Add Column",
        control_type="Button",
        automation_id="Table.AddColumnButton",
        enabled=True,
        visible=True,
        bounds=Bounds(left=260, top=100, right=290, bottom=130),
    )
    header_2 = Control(
        ref="ref:h2",
        parent="ref:table",
        name="<Select Measurement>",
        control_type="Button",
        automation_id="Header_1",
        enabled=True,
        visible=True,
        bounds=Bounds(left=250, top=100, right=400, bottom=130),
    )

    call_count = 0

    def mock_snapshot(*_args: object, **_kwargs: object) -> Snapshot:
        nonlocal call_count
        call_count += 1
        ctrls = [table_ctrl, header_1, add_col_btn]
        if call_count > 1:
            ctrls.append(header_2)
        return Snapshot(window=mock_win, controls=ctrls, truncated=False)

    app.snapshot = mock_snapshot
    app.click = MagicMock()
    app.keys = MagicMock()

    mock_node = MagicMock()
    mock_node.iface_value.SetValue = MagicMock()
    app.control = MagicMock(return_value=mock_node)

    res = set_table_columns(
        app,
        SetTableColumnsRequest(
            columns=["Time (s)", "Velocity (m/s)"],
            handle=100,
            table_name="Table 1",
        ),
    )

    assert isinstance(res, SetTableColumnsResult)
    assert res.table_name == "Table 1"
    assert res.column_count == 2
    assert res.columns == ["Time (s)", "Velocity (m/s)"]
    assert res.verified is True
    assert app.click.call_count >= 3


def test_read_table_validates_pagination_bounds() -> None:
    app = Capstone()
    with pytest.raises(AutomationError, match="page must be >= 1"):
        read_table(app, ReadTableRequest(handle=100, page=0))

    with pytest.raises(AutomationError, match="page_size must be > 0"):
        read_table(app, ReadTableRequest(handle=100, page=1, page_size=0))


def test_read_table_extracts_data_and_statistics() -> None:
    app = Capstone()
    mock_win = _mock_window()

    table_ctrl = Control(
        ref="ref:table",
        parent=None,
        name="Table",
        control_type="Table",
        automation_id="TableWidget",
        enabled=True,
        visible=True,
        bounds=Bounds(left=100, top=100, right=500, bottom=600),
    )
    col1 = Control(
        ref="ref:c1",
        parent="ref:table",
        name="Time (s)",
        control_type="HeaderItem",
        automation_id="Col0",
        enabled=True,
        visible=True,
        bounds=Bounds(left=100, top=100, right=300, bottom=130),
    )
    col2 = Control(
        ref="ref:c2",
        parent="ref:table",
        name="Position (m)",
        control_type="HeaderItem",
        automation_id="Col1",
        enabled=True,
        visible=True,
        bounds=Bounds(left=300, top=100, right=500, bottom=130),
    )

    # Row 1
    r1_c1 = Control(
        ref="ref:r1c1",
        parent="ref:table",
        name="0.0",
        control_type="DataItem",
        automation_id="R0C0",
        enabled=True,
        visible=True,
        bounds=Bounds(left=100, top=140, right=300, bottom=160),
    )
    r1_c2 = Control(
        ref="ref:r1c2",
        parent="ref:table",
        name="0.05",
        control_type="DataItem",
        automation_id="R0C1",
        enabled=True,
        visible=True,
        bounds=Bounds(left=300, top=140, right=500, bottom=160),
    )

    # Row 2
    r2_c1 = Control(
        ref="ref:r2c1",
        parent="ref:table",
        name="0.1",
        control_type="DataItem",
        automation_id="R1C0",
        enabled=True,
        visible=True,
        bounds=Bounds(left=100, top=170, right=300, bottom=190),
    )
    r2_c2 = Control(
        ref="ref:r2c2",
        parent="ref:table",
        name="0.22",
        control_type="DataItem",
        automation_id="R1C1",
        enabled=True,
        visible=True,
        bounds=Bounds(left=300, top=170, right=500, bottom=190),
    )

    # Row 3
    r3_c1 = Control(
        ref="ref:r3c1",
        parent="ref:table",
        name="0.2",
        control_type="DataItem",
        automation_id="R2C0",
        enabled=True,
        visible=True,
        bounds=Bounds(left=100, top=200, right=300, bottom=220),
    )
    r3_c2 = Control(
        ref="ref:r3c2",
        parent="ref:table",
        name="0.48",
        control_type="DataItem",
        automation_id="R2C1",
        enabled=True,
        visible=True,
        bounds=Bounds(left=300, top=200, right=500, bottom=220),
    )

    # Statistics row: Mean
    stat_mean = Control(
        ref="ref:stat_mean",
        parent="ref:table",
        name="Mean: 0.25",
        control_type="Text",
        automation_id="StatMean",
        enabled=True,
        visible=True,
        bounds=Bounds(left=100, top=550, right=300, bottom=580),
    )

    app.snapshot = MagicMock(
        return_value=Snapshot(
            window=mock_win,
            controls=[
                table_ctrl,
                col1,
                col2,
                r1_c1,
                r1_c2,
                r2_c1,
                r2_c2,
                r3_c1,
                r3_c2,
                stat_mean,
            ],
            truncated=False,
        ),
    )

    res = read_table(app, ReadTableRequest(handle=100, page=1, page_size=2))

    assert isinstance(res, ReadTableResult)
    assert res.columns == ["Time (s)", "Position (m)"]
    assert res.total_rows == 3
    assert res.total_pages == 2
    assert res.page == 1
    assert len(res.rows) == 2
    assert res.rows[0] == {"Time (s)": 0.0, "Position (m)": 0.05}
    assert res.rows[1] == {"Time (s)": 0.1, "Position (m)": 0.22}
    assert res.statistics is not None
    assert "Mean" in res.statistics
    assert res.statistics["Mean"]["Time (s)"] == 0.25
