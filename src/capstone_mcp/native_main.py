# Copyright 2026 Capstone MCP contributors.
"""Native-free bootstrap waiting for the parent's process-job assignment."""

from __future__ import annotations

import ctypes
import runpy
import sys
from contextlib import suppress


def init_dpi_awareness() -> None:
    """Initialize Per-Monitor DPI awareness to prevent coordinate scaling drift."""
    if sys.platform == "win32":
        with suppress(AttributeError, OSError):
            # 2 = PROCESS_PER_MONITOR_DPI_AWARE
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
