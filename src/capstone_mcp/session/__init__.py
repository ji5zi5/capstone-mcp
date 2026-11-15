# Copyright 2026 Capstone MCP contributors.
"""Decomposed session management subsystem coordinating lifecycle and CDP."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Final

from capstone_mcp.session.cdp_client import DEFAULT_DEBUG_PORT, SessionCdpClient
from capstone_mcp.session.lifecycle import SessionLifecycleManager
from capstone_mcp.session.telemetry import TelemetryBuffer
from capstone_mcp.session.watcher import (
    ConditionWatcher,
    StopCondition,
    StopConditionTrigger,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from capstone_mcp.automation_worker import AutomationWorker
    from capstone_mcp.bridge import NativeInventory

LOGGER: Final = logging.getLogger(__name__)


class UnifiedSessionManager:
    """Thin facade composing lifecycle, CDP, telemetry, and watcher components."""

    def __init__(
        self,
        worker: AutomationWorker | None = None,
        debug_port: int = DEFAULT_DEBUG_PORT,
    ) -> None:
        """Initialize composite session manager with dedicated sub-components."""
        self._lifecycle = SessionLifecycleManager(worker, debug_port=debug_port)
        self._cdp_client = SessionCdpClient(debug_port=debug_port)
        self._telemetry = TelemetryBuffer()
        self._watcher = ConditionWatcher()

    @property
    def worker(self) -> AutomationWorker | None:
        """Return attached automation worker."""
        return self._lifecycle.worker

    @worker.setter
    def worker(self, worker: AutomationWorker | None) -> None:
        """Update attached automation worker."""
        self._lifecycle.worker = worker

    @property
    def debug_port(self) -> int:
        """Return the target debug port for CDP telemetry."""
        return self._lifecycle.debug_port

    @property
    def lifecycle(self) -> SessionLifecycleManager:
        """Access session lifecycle sub-component."""
        return self._lifecycle

    @property
    def cdp_client(self) -> SessionCdpClient:
        """Access CDP client sub-component."""
        return self._cdp_client

    @property
    def telemetry(self) -> TelemetryBuffer:
        """Access streaming telemetry buffer sub-component."""
        return self._telemetry

    @property
    def watcher(self) -> ConditionWatcher:
        """Access condition trigger watcher sub-component."""
        return self._watcher

    def read_live_inventory(self, port: int | None = None) -> NativeInventory:
        """Query connected sensors and measurement channels via CDP fast-path."""
        return self._cdp_client.read_live_inventory(port)

    def read_live_measurement(
        self,
        measurement_euid: str,
        unit_type: int = 0,
        port: int | None = None,
    ) -> float:
        """Poll instantaneous measurement value over CDP WebSocket (< 10 ms)."""
        val = self._cdp_client.read_live_measurement(
            measurement_euid, unit_type, port,
        )
        self._telemetry.push_sample(measurement_euid, val)
        return val

    def evaluate_stop_condition(
        self,
        current_value: float,
        operator_str: str,
        threshold: float,
    ) -> bool:
        """Check if current value satisfies the stop condition threshold."""
        return self._watcher.evaluate(current_value, operator_str, threshold)

    def monitor_until_stop(
        self,
        condition: StopCondition,
        *,
        halt_callback: Callable[[], Any] | None = None,
        port: int | None = None,
    ) -> StopConditionTrigger:
        """Continuously poll live measurement until threshold is met or timeout."""
        def sample_fn() -> float:
            return self.read_live_measurement(
                condition.measurement_euid,
                condition.unit_type,
                port,
            )

        return self._watcher.monitor(
            condition,
            sample_fn,
            halt_callback=halt_callback,
        )


__all__ = [
    "DEFAULT_DEBUG_PORT",
    "ConditionWatcher",
    "SessionCdpClient",
    "SessionLifecycleManager",
    "StopCondition",
    "StopConditionTrigger",
    "TelemetryBuffer",
    "UnifiedSessionManager",
]
