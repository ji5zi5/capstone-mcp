# Copyright 2026 Capstone MCP contributors.
"""CDP WebSocket transport and telemetry client for Capstone sessions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

from capstone_mcp import bridge

if TYPE_CHECKING:
    from capstone_mcp.bridge import NativeInventory

LOGGER: Final = logging.getLogger(__name__)
DEFAULT_DEBUG_PORT: Final = 9222


class SessionCdpClient:
    """Specialized client for high-speed Capstone CDP WebSocket communication."""

    def __init__(self, debug_port: int = DEFAULT_DEBUG_PORT) -> None:
        """Initialize CDP client with default target port."""
        self.debug_port = debug_port

    def read_live_inventory(self, port: int | None = None) -> NativeInventory:
        """Query connected sensors and measurement channels via CDP fast-path."""
        target_port = port if port is not None else self.debug_port
        return bridge.read_inventory(target_port)

    def read_live_measurement(
        self,
        measurement_euid: str,
        unit_type: int = 0,
        port: int | None = None,
    ) -> float:
        """Poll instantaneous measurement value over CDP WebSocket (< 10 ms)."""
        target_port = port if port is not None else self.debug_port
        return bridge.read_measurement(target_port, measurement_euid, unit_type)
