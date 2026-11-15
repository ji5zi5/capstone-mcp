# Copyright 2026 Capstone MCP contributors.
"""Threshold condition monitoring and trigger evaluation for Capstone sessions."""

from __future__ import annotations

import logging
import operator
import time
from typing import TYPE_CHECKING, Any, Final

from capstone_mcp.models import Model

if TYPE_CHECKING:
    from collections.abc import Callable

LOGGER: Final = logging.getLogger(__name__)

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


class ConditionWatcher:
    """Monitors live sensor streams against user-defined threshold conditions."""

    @staticmethod
    def evaluate(
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

    def monitor(
        self,
        condition: StopCondition,
        sampler: Callable[[], float],
        *,
        halt_callback: Callable[[], Any] | None = None,
    ) -> StopConditionTrigger:
        """Continuously poll sample values until condition is met or timeout."""
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

            val = sampler()
            last_val = val

            if self.evaluate(val, condition.operator, condition.threshold):
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
