# Copyright 2026 Capstone MCP contributors.
"""Telemetry ring buffer and streaming sample aggregator for Capstone sessions."""

from __future__ import annotations

import math
import time
from collections import OrderedDict, deque
from itertools import islice
from statistics import mean
from threading import Lock
from typing import Final, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_BUFFER_CAPACITY: Final = 1000
MAX_MEASUREMENTS: Final = 256


class TelemetryClock(BaseModel):
    """Caller-declared timestamp identity; no implicit clock conversion occurs."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)
    clock_id: str = Field(min_length=1)
    unit: Literal["seconds", "milliseconds", "microseconds", "nanoseconds", "ticks"]
    origin: str = Field(min_length=1)


class TelemetrySnapshot(BaseModel):
    """Atomic copy of sample values and the clock needed to interpret timestamps."""

    clock: TelemetryClock | None
    first_timestamp: float | None
    first_sample_index: int
    samples: list[tuple[float, float]]


class TelemetryBuffer:
    """Thread-safe, bounded ring buffer for streaming sensor samples."""

    def __init__(self, capacity: int = DEFAULT_BUFFER_CAPACITY) -> None:
        """Initialize telemetry buffer with bounded capacity per measurement."""
        self._capacity = max(1, capacity)
        self._buffers: OrderedDict[str, deque[tuple[float, float]]] = OrderedDict()
        self._origins: dict[str, float] = {}
        self._counts: dict[str, int] = {}
        self._clocks: dict[str, TelemetryClock] = {}
        self._host_clock = TelemetryClock(
            clock_id=f"host-monotonic:{uuid4().hex}", unit="seconds",
            origin="unspecified monotonic epoch; not a hardware acquisition clock",
        )
        self._lock = Lock()

    def push_sample(
        self,
        euid: str,
        value: float,
        timestamp: float | None = None,
        *,
        clock: TelemetryClock | None = None,
    ) -> None:
        """Record a sample, rejecting missing or mixed timestamp provenance."""
        if not math.isfinite(value):
            msg = "Telemetry sample value must be finite."
            raise ValueError(msg)
        if timestamp is not None and clock is None:
            msg = (
                "Explicit telemetry timestamps require a clock identity, "
                "unit and origin."
            )
            raise ValueError(msg)
        if timestamp is None and clock is not None:
            msg = "A declared external clock requires an explicit timestamp."
            raise ValueError(msg)
        selected_clock = self._host_clock if clock is None else clock
        with self._lock:
            ts = timestamp if timestamp is not None else time.monotonic()
            if not math.isfinite(ts):
                msg = "Telemetry timestamp must be finite."
                raise ValueError(msg)
            buf = self._buffers.get(euid)
            if euid in self._clocks and self._clocks[euid] != selected_clock:
                msg = (
                    "Telemetry clock domain, unit or origin changed; "
                    "clear before reuse."
                )
                raise ValueError(msg)
            if buf and ts < buf[-1][0]:
                msg = "Telemetry timestamps must not decrease within a measurement."
                raise ValueError(msg)
            if buf is None:
                if len(self._buffers) >= MAX_MEASUREMENTS:
                    evicted, _ = self._buffers.popitem(last=False)
                    self._clocks.pop(evicted, None)
                    self._origins.pop(evicted, None)
                    self._counts.pop(evicted, None)
                self._origins[euid] = ts
                self._counts[euid] = 0
                buf = self._buffers[euid] = deque(maxlen=self._capacity)
                self._clocks[euid] = selected_clock
            buf.append((ts, value))
            self._counts[euid] += 1
            self._buffers.move_to_end(euid)

    def get_clock(self, euid: str) -> TelemetryClock | None:
        """Return immutable timestamp provenance for retained channel samples."""
        with self._lock:
            return self._clocks.get(euid)

    def get_snapshot(self, euid: str) -> TelemetrySnapshot:
        """Export timestamps with their provenance under the same buffer lock."""
        with self._lock:
            return TelemetrySnapshot(
                clock=self._clocks.get(euid),
                first_timestamp=self._origins.get(euid),
                first_sample_index=(
                    self._counts.get(euid, 0) - len(self._buffers.get(euid, ()))
                ),
                samples=list(self._buffers.get(euid, ())),
            )

    def get_samples(
        self,
        euid: str,
        limit: int | None = None,
    ) -> list[tuple[float, float]]:
        """Retrieve recent samples as (timestamp, value) pairs."""
        if limit is not None and limit < 0:
            msg = "Sample limit must be nonnegative."
            raise ValueError(msg)
        if limit == 0:
            return []
        with self._lock:
            buf = self._buffers.get(euid)
            if not buf:
                return []
            if limit is None:
                return list(buf)
            samples = list(islice(reversed(buf), min(limit, len(buf))))
        samples.reverse()
        return samples

    def sample_count(self, euid: str) -> int:
        """Return the number of retained samples without copying the buffer."""
        with self._lock:
            return len(self._buffers.get(euid, ()))

    def get_latest(self, euid: str) -> float | None:
        """Get the most recent value for a given measurement EUID."""
        with self._lock:
            buf = self._buffers.get(euid)
            return buf[-1][1] if buf else None

    def clear(self, euid: str | None = None) -> None:
        """Clear recorded samples for a specific EUID or all buffers."""
        with self._lock:
            if euid is not None:
                self._buffers.pop(euid, None)
                self._clocks.pop(euid, None)
                self._origins.pop(euid, None)
                self._counts.pop(euid, None)
            else:
                self._buffers.clear()
                self._clocks.clear()
                self._origins.clear()
                self._counts.clear()

    def compute_stats(self, euid: str) -> dict[str, float]:
        """Compute basic summary statistics for buffered samples."""
        samples = self.get_samples(euid)
        if not samples:
            return {"count": 0.0, "mean": 0.0, "min": 0.0, "max": 0.0}
        vals = [v for _, v in samples]
        count = len(vals)
        return {
            "count": float(count),
            "mean": mean(vals),
            "min": min(vals),
            "max": max(vals),
        }
