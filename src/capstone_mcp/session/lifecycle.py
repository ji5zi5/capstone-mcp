# Copyright 2026 Capstone MCP contributors.
"""Process and worker lifecycle management for Capstone automation sessions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from capstone_mcp.automation_worker import AutomationWorker

LOGGER: Final = logging.getLogger(__name__)


class SessionLifecycleManager:
    """Manages automation worker and desktop process attachment state."""

    def __init__(
        self,
        worker: AutomationWorker | None = None,
        *,
        debug_port: int = 9222,
    ) -> None:
        """Initialize session lifecycle state."""
        self._worker: AutomationWorker | None = worker
        self._debug_port: int = debug_port
        self._is_active: bool = True

    @property
    def worker(self) -> AutomationWorker | None:
        """Return attached automation worker instance."""
        return self._worker

    @worker.setter
    def worker(self, worker: AutomationWorker | None) -> None:
        """Update attached automation worker reference."""
        self._worker = worker

    @property
    def debug_port(self) -> int:
        """Return the target debug port for CDP telemetry."""
        return self._debug_port

    @property
    def is_active(self) -> bool:
        """Check if the session lifecycle is active."""
        return self._is_active

    def terminate(self) -> None:
        """Mark session inactive and disconnect active resources."""
        self._is_active = False
        LOGGER.info("Session lifecycle marked inactive (port=%d)", self._debug_port)

    def get_session_info(self) -> dict[str, Any]:
        """Return diagnostic dictionary of session status."""
        return {
            "active": self._is_active,
            "debug_port": self._debug_port,
            "worker_attached": self._worker is not None,
        }
