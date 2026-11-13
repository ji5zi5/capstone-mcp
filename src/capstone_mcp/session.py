# Copyright 2026 Capstone MCP contributors.
"""Unified session manager coordinating Desktop UIA and CDP telemetry."""

from __future__ import annotations

import logging
import operator
import time
from typing import TYPE_CHECKING, Any, Final

from capstone_mcp import bridge
from capstone_mcp.models import Model

if TYPE_CHECKING:
    from collections.abc import Callable

    from capstone_mcp.automation_worker import AutomationWorker
    from capstone_mcp.bridge import NativeInventory

LOGGER: Final = logging.getLogger(__name__)
DEFAULT_DEBUG_PORT: Final = 9222

COMPARATORS: Final[dict[str, Callable[[float, float], bool]]] = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
    "=": operator.eq,
    "above": operator.gt,
    "below": operator.lt,
    "reaches": operator.ge,
}


class StopCondition(Model):
    """Threshold specification for monitoring and halting recording."""

    measurement_euid: str
    operator: str
    threshold: float
    unit_type: int = 0
    timeout: float = 10.0
    poll_interval: float = 0.05


class StopConditionTrigger(Model):
    """Evaluation result for threshold stop conditions."""

    triggered: bool
    current_value: float
    threshold: float
    operator: str
    elapsed_seconds: float
    detail: str


class UnifiedSessionManager:
    """Coordinates desktop UI automation worker and CDP WebSocket fast-path."""

    def __init__(
        self,
        worker: AutomationWorker | None = None,
        debug_port: int = DEFAULT_DEBUG_PORT,
    ) -> None:
        """Initialize session manager with optional worker and debug port."""
        self.worker = worker
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

    def evaluate_stop_condition(
        self,
        current_value: float,
        operator_str: str,
        threshold: float,
    ) -> bool:
        """Check if current value satisfies the stop condition threshold."""
        op_fn = COMPARATORS.get(operator_str.strip().lower())
        if op_fn is None:
            msg = f"Unsupported threshold operator: {operator_str!r}"
            raise ValueError(msg)
        return op_fn(current_value, threshold)

    def monitor_until_stop(
        self,
        condition: StopCondition,
        *,
        halt_callback: Callable[[], Any] | None = None,
        port: int | None = None,
    ) -> StopConditionTrigger:
        """Continuously poll live measurement until threshold is met or timeout."""
        target_port = port if port is not None else self.debug_port
        start_time = time.monotonic()
        last_val = 0.0

        while True:
            elapsed = time.monotonic() - start_time
            if elapsed > condition.timeout:
                return StopConditionTrigger(
                    triggered=False,
                    current_value=last_val,
                    threshold=condition.threshold,
                    operator=condition.operator,
                    elapsed_seconds=elapsed,
                    detail=(
                        f"Timeout of {condition.timeout:.1f}s exceeded "
                        "before threshold was met."
                    ),
                )

            val = bridge.read_measurement(
                target_port, condition.measurement_euid, condition.unit_type,
            )
            last_val = val

            if self.evaluate_stop_condition(
                val, condition.operator, condition.threshold,
            ):
                if halt_callback is not None:
                    halt_callback()
                return StopConditionTrigger(
                    triggered=True,
                    current_value=val,
                    threshold=condition.threshold,
                    operator=condition.operator,
                    elapsed_seconds=time.monotonic() - start_time,
                    detail=(
                        f"Stop condition triggered: {val} {condition.operator} "
                        f"{condition.threshold}"
                    ),
                )

            time.sleep(condition.poll_interval)


__all__ = [
    "DEFAULT_DEBUG_PORT",
    "StopCondition",
    "StopConditionTrigger",
    "UnifiedSessionManager",
]
