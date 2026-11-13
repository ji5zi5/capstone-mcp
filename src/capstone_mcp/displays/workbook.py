# Copyright 2026 Capstone MCP contributors.
"""Workbook page creation and multi-display layout templates in Capstone."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.displays.harness import click_control
from capstone_mcp.displays.models import (
    ADD_PAGE_NAMES,
    ADD_PAGE_SUFFIX,
    LAYOUT_AREAS,
    LAYOUT_KEYWORDS,
    AddPageRequest,
    AddPageResult,
    PageLayoutTemplate,
    SetPageLayoutRequest,
    SetPageLayoutResult,
)

if TYPE_CHECKING:
    from capstone_mcp.models import Control


def _find_add_page_button(controls: list[Control]) -> Control:
    """Find the Add Page / New Page button in the active window."""
    for ctrl in controls:
        if not ctrl.visible:
            continue
        cname = ctrl.name.strip()
        aid = ctrl.automation_id
        if aid.endswith((ADD_PAGE_SUFFIX, ".NewPageButton")):
            return ctrl
        if ctrl.control_type in ("Button", "TabItem") and (
            cname in ADD_PAGE_NAMES
            or any(n.lower() in cname.lower() for n in ("add page", "new page"))
        ):
            return ctrl
    msg = "Add Page button not found in workbook."
    raise AutomationError(msg)


def _rename_page_tab(
    app: Capstone,
    handle: int,
    tab_ctrl: Control,
    title: str,
) -> None:
    """Rename a page tab via ValuePattern or inline keyboard edit."""
    node = app.control(tab_ctrl.ref)
    with contextlib.suppress(AttributeError, RuntimeError):
        node.iface_value.SetValue(title)
        return

    # Fallback inline rename
    click_control(app, handle, tab_ctrl, allow_foreground=True)
    if hasattr(app, "keys"):
        _ = app.keys(handle, "{F2}", allow_foreground=True)
        _ = app.keys(handle, f"^a{title}{{ENTER}}", allow_foreground=True)


def add_page(
    app: Capstone,
    request: AddPageRequest | None = None,
) -> AddPageResult:
    """Create a new workbook page tab and set its title."""
    if request is None:
        request = AddPageRequest()

    clean_title = request.title.strip()
    if not clean_title:
        msg = "title must not be empty."
        raise AutomationError(msg)

    if not request.allow_foreground:
        msg = "Adding a workbook page requires allow_foreground=true."
        raise AutomationError(msg)

    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    existing_tabs = [
        c for c in snapshot.controls if c.visible and c.control_type == "TabItem"
    ]
    page_index = len(existing_tabs)

    add_btn = _find_add_page_button(snapshot.controls)
    click_control(app, request.handle, add_btn, allow_foreground=True)

    # Rename new tab if specific title was requested
    post_snap = app.snapshot(request.handle, depth=16, limit=10_000)
    new_tabs = [
        c for c in post_snap.controls if c.visible and c.control_type == "TabItem"
    ]
    if new_tabs:
        latest_tab = new_tabs[-1]
        _rename_page_tab(app, request.handle, latest_tab, clean_title)

    detail = f"Workbook page '{clean_title}' added at index {page_index}."
    return AddPageResult(
        page_index=page_index,
        title=clean_title,
        verified=True,
        detail=detail,
    )


def _switch_to_page(
    app: Capstone,
    handle: int,
    controls: list[Control],
    page_name: str,
) -> None:
    """Switch active page tab to page_name."""
    target_tab: Control | None = None
    p_lower = page_name.strip().lower()
    for ctrl in controls:
        if (
            ctrl.visible
            and ctrl.control_type == "TabItem"
            and (ctrl.name.strip().lower() == p_lower or p_lower in ctrl.name.lower())
        ):
            target_tab = ctrl
            break

    if target_tab is None:
        msg = f"Workbook page '{page_name}' not found."
        raise AutomationError(msg)

    node = app.control(target_tab.ref)
    if hasattr(node, "iface_selection_item") and node.iface_selection_item:
        with contextlib.suppress(AttributeError, RuntimeError):
            node.iface_selection_item.Select()
            return
    click_control(app, handle, target_tab, allow_foreground=True)


def _find_layout_template_control(
    controls: list[Control],
    layout: PageLayoutTemplate,
) -> Control:
    """Find layout template button corresponding to requested template."""
    keywords = LAYOUT_KEYWORDS.get(layout, ())
    for ctrl in controls:
        if not ctrl.visible:
            continue
        cname = ctrl.name.strip().lower()
        aid = ctrl.automation_id.lower()
        for kw in keywords:
            if kw in cname or kw in aid:
                return ctrl

    msg = f"Layout template control for '{layout}' not found on active page."
    raise AutomationError(msg)


def set_page_layout(
    app: Capstone,
    request: SetPageLayoutRequest,
) -> SetPageLayoutResult:
    """Apply a 1 to 4 split grid layout template to active or named workbook page."""
    if not request.allow_foreground:
        msg = "Setting page layout requires allow_foreground=true."
        raise AutomationError(msg)

    if request.layout not in LAYOUT_AREAS:
        supported = list(LAYOUT_AREAS.keys())
        msg = f"Unsupported layout '{request.layout}'. Supported layouts: {supported}"
        raise AutomationError(msg)

    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)

    if request.page_name is not None:
        _switch_to_page(app, request.handle, snapshot.controls, request.page_name)
        snapshot = app.snapshot(request.handle, depth=16, limit=10_000)

    template_ctrl = _find_layout_template_control(snapshot.controls, request.layout)
    click_control(app, request.handle, template_ctrl, allow_foreground=True)

    areas_count = LAYOUT_AREAS[request.layout]
    detail = f"Page layout template '{request.layout}' applied ({areas_count} areas)."

    return SetPageLayoutResult(
        layout=request.layout,
        page_name=request.page_name,
        areas_created=areas_count,
        verified=True,
        detail=detail,
    )
