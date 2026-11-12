# Copyright 2026 Capstone MCP contributors.
"""Domain tool routers for FastMCP server."""

from capstone_mcp.tools.displays import register_display_tools
from capstone_mcp.tools.files import register_file_tools
from capstone_mcp.tools.instruments import register_instrument_tools
from capstone_mcp.tools.physics import register_physics_tools

__all__ = [
    "register_display_tools",
    "register_file_tools",
    "register_instrument_tools",
    "register_physics_tools",
]
