# Copyright 2026 Capstone MCP contributors.
"""Tests for workbook page creation and layout template tools."""

from unittest.mock import MagicMock

import pytest

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.models import Bounds, Control, Snapshot, Window
from capstone_mcp.workbook_layout import (
    AddPageRequest,
    AddPageResult,
    SetPageLayoutRequest,
    SetPageLayoutResult,
    add_page,
    set_page_layout,
)


def _make_window() -> Window:
    return Window(
        handle=100,
        title="Capstone",
        process_id=1,
        bounds=Bounds(left=0, top=0, right=1200, bottom=900),
    )


# --- Tests for add_page ---


def test_add_page_rejects_empty_title() -> None:
    app = Capstone()
    req = AddPageRequest(handle=100, title="")
    with pytest.raises(AutomationError, match="title must not be empty"):
        _ = add_page(app, req)


def test_add_page_requires_foreground() -> None:
    app = Capstone()
    req = AddPageRequest(handle=100, title="Page 2", allow_foreground=False)
    with pytest.raises(AutomationError, match="allow_foreground"):
        _ = add_page(app, req)


def test_add_page_raises_when_add_button_not_found() -> None:
    app = Capstone()
    mock_win = _make_window()
    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_win,
        controls=[],
        truncated=False,
    ))

    req = AddPageRequest(handle=100, title="Page 2")
    with pytest.raises(AutomationError, match="Add Page button not found"):
        _ = add_page(app, req)


def test_add_page_success() -> None:
    app = Capstone()
    mock_win = _make_window()

    tab1 = Control(
        ref="ref:tab1", parent=None, name="Page 1",
        control_type="TabItem", automation_id="page_tab_1",
        enabled=True, visible=True,
        bounds=Bounds(left=10, top=10, right=80, bottom=35),
    )
    add_btn = Control(
        ref="ref:add_btn", parent=None, name="Add Page",
        control_type="Button", automation_id="Workbook.AddPageButton",
        enabled=True, visible=True,
        bounds=Bounds(left=85, top=10, right=110, bottom=35),
    )
    tab2 = Control(
        ref="ref:tab2", parent=None, name="New Page",
        control_type="TabItem", automation_id="page_tab_2",
        enabled=True, visible=True,
        bounds=Bounds(left=85, top=10, right=155, bottom=35),
    )

    step = 0

    def mock_snapshot(*_args: object, **_kwargs: object) -> Snapshot:
        nonlocal step
        step += 1
        if step == 1:
            return Snapshot(
                window=mock_win,
                controls=[tab1, add_btn],
                truncated=False,
            )
        return Snapshot(
            window=mock_win,
            controls=[tab1, tab2, add_btn],
            truncated=False,
        )

    app.snapshot = mock_snapshot
    app.click = MagicMock()
    app.keys = MagicMock()

    tab2_node = MagicMock()
    app.control = MagicMock(return_value=tab2_node)

    req = AddPageRequest(handle=100, title="Experiment Results")
    result = add_page(app, req)

    assert isinstance(result, AddPageResult)
    assert result.page_index == 1
    assert result.title == "Experiment Results"
    assert result.verified is True
    app.click.assert_called_once_with(100, "ref:add_btn", allow_foreground=True)
    tab2_node.iface_value.SetValue.assert_called_once_with("Experiment Results")


# --- Tests for set_page_layout ---


def test_set_page_layout_requires_foreground() -> None:
    app = Capstone()
    req = SetPageLayoutRequest(
        handle=100,
        layout="two_vertical",
        allow_foreground=False,
    )
    with pytest.raises(AutomationError, match="allow_foreground"):
        _ = set_page_layout(app, req)


def test_set_page_layout_raises_when_page_not_found() -> None:
    app = Capstone()
    mock_win = _make_window()
    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_win,
        controls=[
            Control(
                ref="ref:tab1", parent=None, name="Page 1",
                control_type="TabItem", automation_id="tab_1",
                enabled=True, visible=True,
                bounds=Bounds(left=0, top=0, right=50, bottom=30),
            ),
        ],
        truncated=False,
    ))

    req = SetPageLayoutRequest(
        handle=100,
        layout="two_vertical",
        page_name="Nonexistent Page",
    )
    with pytest.raises(AutomationError, match="Workbook page 'Nonexistent Page'"):
        _ = set_page_layout(app, req)


def test_set_page_layout_raises_when_template_not_found() -> None:
    app = Capstone()
    mock_win = _make_window()
    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_win,
        controls=[],
        truncated=False,
    ))

    req = SetPageLayoutRequest(handle=100, layout="four_grid")
    with pytest.raises(AutomationError, match="Layout template control"):
        _ = set_page_layout(app, req)


def test_set_page_layout_two_vertical_success() -> None:
    app = Capstone()
    mock_win = _make_window()

    template_btn = Control(
        ref="ref:tpl_2v", parent=None, name="Two Vertical Displays",
        control_type="Button", automation_id="TemplateTwoVertical",
        enabled=True, visible=True,
        bounds=Bounds(left=100, top=100, right=200, bottom=180),
    )
    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_win,
        controls=[template_btn],
        truncated=False,
    ))
    app.click = MagicMock()

    req = SetPageLayoutRequest(handle=100, layout="two_vertical")
    result = set_page_layout(app, req)

    assert isinstance(result, SetPageLayoutResult)
    assert result.layout == "two_vertical"
    assert result.areas_created == 2
    assert result.verified is True
    app.click.assert_called_once_with(100, "ref:tpl_2v", allow_foreground=True)


def test_set_page_layout_four_grid_with_page_selection_success() -> None:
    app = Capstone()
    mock_win = _make_window()

    page2_tab = Control(
        ref="ref:page2", parent=None, name="Analysis",
        control_type="TabItem", automation_id="page_analysis",
        enabled=True, visible=True,
        bounds=Bounds(left=100, top=10, right=180, bottom=35),
    )
    grid4_btn = Control(
        ref="ref:grid4", parent=None, name="4 Displays Grid",
        control_type="Button", automation_id="TemplateFourDisplays",
        enabled=True, visible=True,
        bounds=Bounds(left=200, top=100, right=300, bottom=180),
    )

    app.snapshot = MagicMock(return_value=Snapshot(
        window=mock_win,
        controls=[page2_tab, grid4_btn],
        truncated=False,
    ))
    app.click = MagicMock()

    page2_node = MagicMock()
    app.control = MagicMock(return_value=page2_node)

    req = SetPageLayoutRequest(
        handle=100,
        layout="four_grid",
        page_name="Analysis",
    )
    result = set_page_layout(app, req)

    assert isinstance(result, SetPageLayoutResult)
    assert result.layout == "four_grid"
    assert result.areas_created == 4
    assert result.page_name == "Analysis"
    assert result.verified is True
    page2_node.iface_selection_item.Select.assert_called_once()
    app.click.assert_called_once_with(100, "ref:grid4", allow_foreground=True)
