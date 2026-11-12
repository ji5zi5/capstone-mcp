# Copyright 2026 Capstone MCP contributors.
"""Descriptive statistics and summary calculations for numeric data series."""

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class SeriesSummary:
    """Summary metrics of a 1D numerical data series."""

    count: int
    mean: float
    std_dev: float
    min_val: float
    max_val: float
    peak_val: float


def compute_series_summary(values: Sequence[float]) -> SeriesSummary:
    """Compute descriptive statistics for a sequence of floating point values.

    Args:
        values: Sequence of numeric values.

    Returns:
        SeriesSummary containing count, mean, std_dev, min, max, and peak.

    Raises:
        ValueError: If the sequence is empty.
    """
    clean_vals = [float(v) for v in values if not math.isnan(v)]
    if not clean_vals:
        msg = "Cannot compute summary on empty or all-NaN series"
        raise ValueError(msg)

    n = len(clean_vals)
    mean_val = sum(clean_vals) / n
    variance = sum((x - mean_val) ** 2 for x in clean_vals) / max(n - 1, 1)
    std_val = math.sqrt(variance) if n > 1 else 0.0

    min_val = min(clean_vals)
    max_val = max(clean_vals)
    peak_val = max(abs(min_val), abs(max_val))

    return SeriesSummary(
        count=n,
        mean=mean_val,
        std_dev=std_val,
        min_val=min_val,
        max_val=max_val,
        peak_val=peak_val,
    )
