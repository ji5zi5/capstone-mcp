# Copyright 2026 Capstone MCP contributors.
"""MCP tools for the installed PASCO Capstone desktop application."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("capstone-mcp")
except PackageNotFoundError:
    __version__ = "0+unknown"
