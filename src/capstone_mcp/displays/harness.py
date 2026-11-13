# Copyright 2026 Capstone MCP contributors.
"""Unified Display Harness for Capstone UI automation and display containers."""

from __future__ import annotations

import contextlib
from typing import Final

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.models import Action, Bounds, Control

DEFAULT_DISPLAY_KEYWORDS: Final[tuple[str, ...]] = (
    "graph",
    "table",
    "digits",
    "scope",
    "oscilloscope",
    "fft",
)
CONTAINER_CONTROL_TYPES: Final[tuple[str, ...]] = (
    "Table",
    "DataGrid",
    "Custom",
    "Pane",
    "Group",
)
PALETTE_ITEM_CONTROL_TYPES: Final[tuple[str, ...]] = (
    "Text",
    "Button",
    "ListItem",
    "TreeItem",
    "Custom",
)


def center_coords(bounds: Bounds) -> tuple[int, int]:
    """Calculate the integer center coordinate (x, y) of a bounding rectangle."""
    return ((bounds.left + bounds.right) // 2, (bounds.top + bounds.bottom) // 2)


def click_control(
    app: Capstone,
    handle: int,
    ctrl: Control,
    *,
    double: bool = False,
    allow_foreground: bool = True,
) -> None:
    """Deliver a click or double-click compatible with both real Capstone and mocks."""
    if hasattr(app, "click"):
        app.click(handle, ctrl.ref, allow_foreground=allow_foreground)
        return

    with contextlib.suppress(Exception):
        node = app.control(ctrl.ref)
        if double:
            coords = center_coords(ctrl.bounds)
            node.click_input(button="left", double=True, coords=coords, absolute=True)
            return
        if hasattr(node, "invoke") and callable(node.invoke):
            node.invoke()
            return

    with contextlib.suppress(Exception):
        app.act(handle, Action.INVOKE, ref=ctrl.ref, allow_foreground=allow_foreground)
        return

    app.act(ctrl.ref, Action.INVOKE, allow_foreground=allow_foreground)


def double_click_control(
    app: Capstone,
    handle: int,
    ctrl: Control,
    *,
    allow_foreground: bool = True,
) -> None:
    """Deliver an explicit double-click to insert palette items onto the page."""
    with contextlib.suppress(Exception):
        app.focus_window(handle)

    with contextlib.suppress(Exception):
        node = app.control(ctrl.ref)
        if hasattr(node, "click_input"):
            coords = center_coords(ctrl.bounds)
            node.click_input(
                button="left",
                double=True,
                coords=coords,
                absolute=True,
            )
            return

    click_control(app, handle, ctrl, double=True, allow_foreground=allow_foreground)


def drag_control(
    app: Capstone,
    handle: int,
    source: Control,
    target: Control,
    *,
    allow_foreground: bool = True,
) -> None:
    """Drag a palette item to a target layout container or page region."""
    with contextlib.suppress(Exception):
        app.focus_window(handle)

    if hasattr(app, "drag"):
        app.drag(handle, source.ref, target.ref, allow_foreground=allow_foreground)
        return

    with contextlib.suppress(Exception):
        node = app.control(source.ref)
        if hasattr(node, "drag_mouse"):
            dst_coords = center_coords(target.bounds)
            node.drag_mouse(dst_coords)
            return

    # Fallback to double-click placement if drag is unhandled by mock/backend
    double_click_control(app, handle, source)


def set_control_value(
    app: Capstone,
    handle: int,
    ctrl: Control,
    text: str,
) -> None:
    """Set text or value in a target control via ValuePattern or keystrokes."""
    node = app.control(ctrl.ref)
    with contextlib.suppress(AttributeError, RuntimeError):
        if hasattr(node, "iface_value") and node.iface_value:
            node.iface_value.SetValue(text)
            return

    click_control(app, handle, ctrl, allow_foreground=True)
    if hasattr(app, "keys"):
        app.keys(handle, "^a{BACKSPACE}")
        if hasattr(app, "type_text"):
            app.type_text(text)
        app.keys(handle, "{ENTER}")


def is_within_bounds(inner: Control, outer: Control) -> bool:
    """Check if inner control rectangle is strictly contained within outer bounds."""
    return (
        inner.bounds.left >= outer.bounds.left
        and inner.bounds.top >= outer.bounds.top
        and inner.bounds.right <= outer.bounds.right
        and inner.bounds.bottom <= outer.bounds.bottom
    )


def find_palette_item(
    controls: list[Control],
    target_name: str,
    suffix: str | None = None,
) -> Control:
    """Find a display item in the Displays palette panel."""
    target_lower = target_name.strip().lower()
    for ctrl in controls:
        if not (ctrl.visible and ctrl.enabled):
            continue
        if ctrl.control_type not in PALETTE_ITEM_CONTROL_TYPES:
            continue

        cname_lower = ctrl.name.strip().lower()
        aid_lower = ctrl.automation_id.lower()

        if suffix and ctrl.automation_id.endswith(suffix):
            return ctrl
        if cname_lower == target_lower or target_lower in cname_lower:
            return ctrl
        if target_lower in aid_lower:
            return ctrl

    msg = f"Expected {target_name} display palette item not found in window snapshot."
    raise AutomationError(msg)


def _match_custom_name(controls: list[Control], custom_name: str) -> Control | None:
    c_lower = custom_name.strip().lower()
    for ctrl in controls:
        if not ctrl.visible:
            continue
        if (
            c_lower == ctrl.name.strip().lower()
            or c_lower in ctrl.automation_id.lower()
        ):
            return ctrl
    return None


def find_display_container(
    controls: list[Control],
    widget_type: str,
    custom_name: str | None = None,
) -> Control:
    """Locate a display widget container in the active window."""
    w_lower = widget_type.strip().lower()

    if custom_name:
        matched = _match_custom_name(controls, custom_name)
        if matched is not None:
            return matched
        msg = f"{widget_type} control matching '{custom_name}' not found."
        raise AutomationError(msg)

    # Special-case direct Table or DataGrid control types
    if w_lower == "table":
        for ctrl in controls:
            if ctrl.visible and ctrl.control_type in ("Table", "DataGrid"):
                return ctrl

    # Standard keyword search
    for ctrl in controls:
        if not ctrl.visible:
            continue
        if ctrl.control_type in CONTAINER_CONTROL_TYPES and (
            w_lower in ctrl.name.lower() or w_lower in ctrl.automation_id.lower()
        ):
            return ctrl

    # Fallback to the largest Custom/Pane that isn't the root window
    candidates = [
        c
        for c in controls
        if c.visible and c.control_type in ("Custom", "Pane") and c.parent is not None
    ]
    if candidates:
        return candidates[0]

    msg = f"No {widget_type} display found in active window."
    raise AutomationError(msg)


def find_display_containers(
    controls: list[Control],
    keywords: tuple[str, ...] = DEFAULT_DISPLAY_KEYWORDS,
) -> list[Control]:
    """Find all graph, table, or display containers in the window snapshot."""
    displays: list[Control] = []
    for ctrl in controls:
        if not ctrl.visible:
            continue
        name_lower = ctrl.name.lower()
        aid_lower = ctrl.automation_id.lower()
        if ctrl.control_type in ("Custom", "Pane", "Group", "Table", "DataGrid") and (
            any(k in name_lower for k in keywords)
            or any(k in aid_lower for k in keywords)
        ):
            displays.append(ctrl)
    return displays


class DisplayHarness:
    """Unified automation harness for display creation and container interaction."""

    def __init__(self, app: Capstone) -> None:
        """Initialize display harness bound to Capstone automation client."""
        self.app = app

    def click(
        self,
        handle: int,
        ctrl: Control,
        *,
        double: bool = False,
        allow_foreground: bool = True,
    ) -> None:
        """Click or double-click a control."""
        click_control(
            self.app,
            handle,
            ctrl,
            double=double,
            allow_foreground=allow_foreground,
        )

    def double_click(self, handle: int, ctrl: Control) -> None:
        """Double-click a control."""
        double_click_control(self.app, handle, ctrl)

    def drag(
        self,
        handle: int,
        source: Control,
        target: Control,
        *,
        allow_foreground: bool = True,
    ) -> None:
        """Drag a control from source to target."""
        drag_control(
            self.app,
            handle,
            source,
            target,
            allow_foreground=allow_foreground,
        )

    def set_value(self, handle: int, ctrl: Control, text: str) -> None:
        """Set value in a target control."""
        set_control_value(self.app, handle, ctrl, text)

    def find_palette_item(
        self,
        controls: list[Control],
        target_name: str,
        suffix: str | None = None,
    ) -> Control:
        """Find a palette item in snapshot controls."""
        return find_palette_item(controls, target_name, suffix)

    def find_container(
        self,
        controls: list[Control],
        widget_type: str,
        custom_name: str | None = None,
    ) -> Control:
        """Locate target display container."""
        return find_display_container(controls, widget_type, custom_name)

    def find_containers(
        self,
        controls: list[Control],
        keywords: tuple[str, ...] = DEFAULT_DISPLAY_KEYWORDS,
    ) -> list[Control]:
        """Find all matching display containers."""
        return find_display_containers(controls, keywords)

    @staticmethod
    def is_within_bounds(inner: Control, outer: Control) -> bool:
        """Check if inner control rectangle is inside outer bounds."""
        return is_within_bounds(inner, outer)
