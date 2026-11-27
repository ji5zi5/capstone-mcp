# Copyright 2026 Capstone MCP contributors.
"""Native-free bootstrap waiting for the parent's process-job assignment."""

from __future__ import annotations

import ctypes
import runpy
import sys
from contextlib import suppress
from ctypes import wintypes

DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
ERROR_ACCESS_DENIED = 5


def init_dpi_awareness() -> None:
    """Initialize Per-Monitor DPI awareness to prevent coordinate scaling drift."""
    if sys.platform != "win32":
        return
    with suppress(AttributeError, OSError):
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        set_context = user32.SetProcessDpiAwarenessContext
        set_context.argtypes = (wintypes.HANDLE,)
        set_context.restype = wintypes.BOOL
        if set_context(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2):
            return
        if ctypes.get_last_error() == ERROR_ACCESS_DENIED:
            return  # A launcher or manifest already set the process context.
    with suppress(AttributeError, OSError):
        _ = ctypes.windll.shcore.SetProcessDpiAwareness(2)


def main() -> None:
    """Import the COM runtime only after an explicit parent initialization signal."""
    if sys.stdin.readline() != "INITIALIZE\n":
        return
    init_dpi_awareness()
    sys.__dict__["coinit_flags"] = 0
    _ = runpy.run_module("capstone_mcp.native_loop", run_name="__main__")


if __name__ == "__main__":
    main()
