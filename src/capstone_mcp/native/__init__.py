# Copyright 2026 Capstone MCP contributors.
"""Native automation desktop runtime and error diagnosis."""

from __future__ import annotations

from capstone_mcp.native.errors import classify_native_error
from capstone_mcp.native.runtime import NativeDesktop

__all__ = ["NativeDesktop", "classify_native_error"]
