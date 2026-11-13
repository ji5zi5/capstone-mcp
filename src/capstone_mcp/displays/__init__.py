# Copyright 2026 Capstone MCP contributors.
"""Consolidated Display Harness module for Capstone MCP."""

from capstone_mcp.displays.harness import (
    DEFAULT_DISPLAY_KEYWORDS,
    DisplayHarness,
    center_coords,
    click_control,
    double_click_control,
    drag_control,
    find_display_container,
    find_display_containers,
    find_palette_item,
    is_within_bounds,
    set_control_value,
)

__all__ = [
    "DEFAULT_DISPLAY_KEYWORDS",
    "DisplayHarness",
    "center_coords",
    "click_control",
    "double_click_control",
    "drag_control",
    "find_display_container",
    "find_display_containers",
    "find_palette_item",
    "is_within_bounds",
    "set_control_value",
]
