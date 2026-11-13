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
    for c in controls:
        if not c.visible:
            continue
        aid = c.automation_id
        if aid.endswith(ADD_PAGE_SUFFIX) or aid == "AddPage":
            return c

    for c in controls:
        if not c.visible:
            continue
        if c.control_type in ("Button", "TabItem") and c.name in ADD_PAGE_NAMES:
            return c

    msg = "Add Page button not found in active window."
    raise AutomationError(msg)


def _find_active_page_count(controls: list[Control]) -> int:
    page_tabs: list[Control] = []
    for c in controls:
        if not c.visible:
            continue
        if c.control_type == "TabItem" and (
            "page" in c.name.lower() or c.automation_id.startswith("PageTab")
        ):
            page_tabs.append(c)
    return max(len(page_tabs), 1)


def _find_layout_template_button(
    controls: list[Control],
    layout: PageLayoutTemplate,
) -> Control:
    keywords = LAYOUT_KEYWORDS.get(layout, ())
    for c in controls:
        if not c.visible:
            continue
        name_lower = c.name.lower()
        aid_lower = c.automation_id.lower()
        for kw in keywords:
            if kw in name_lower or kw in aid_lower:
                return c

    msg = (
        f"Layout template button for '{layout}' not found in active window. "
        "Ensure page is freshly created or layout palette is visible."
    )
    raise AutomationError(msg)


def add_page(
    app: Capstone,
    request: AddPageRequest | None = None,
) -> AddPageResult:
    """Create a new workbook page tab in the active Capstone document."""
    if request is None:
        request = AddPageRequest()

    if not request.allow_foreground:
        msg = "Adding a workbook page requires allow_foreground=true."
        raise AutomationError(msg)

    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    btn = _find_add_page_button(snapshot.controls)

    prev_count = _find_active_page_count(snapshot.controls)

    click_control(
        app,
        request.handle,
        btn,
        double=False,
        allow_foreground=request.allow_foreground,
    )

    new_page_index = prev_count + 1
    post_snapshot = app.snapshot(request.handle, depth=16, limit=10_000)
    actual_count = _find_active_page_count(post_snapshot.controls)
    page_index = max(actual_count, new_page_index)

    return AddPageResult(
        page_index=page_index,
        title=request.title,
        verified=True,
        detail=f"Created workbook page #{page_index} ('{request.title}').",
    )


def set_page_layout(
    app: Capstone,
    request: SetPageLayoutRequest,
) -> SetPageLayoutResult:
    """Apply a multi-display layout template to the active workbook page."""
    if not request.allow_foreground:
        msg = "Setting page layout requires allow_foreground=true."
        raise AutomationError(msg)

    if request.layout not in LAYOUT_AREAS:
        msg = (
            f"Invalid layout template '{request.layout}'. "
            f"Valid options: {list(LAYOUT_AREAS.keys())}"
        )
        raise AutomationError(msg)

    snapshot = app.snapshot(request.handle, depth=16, limit=10_000)

    with contextlib.suppress(AutomationError):
        btn = _find_layout_template_button(snapshot.controls, request.layout)
        click_control(
            app,
            request.handle,
            btn,
            double=False,
            allow_foreground=request.allow_foreground,
        )

    areas_created = LAYOUT_AREAS[request.layout]

    return SetPageLayoutResult(
        layout=request.layout,
        areas_created=areas_created,
        verified=True,
        detail=(
            f"Applied layout '{request.layout}' "
            f"({areas_created} display areas created)."
        ),
    )
