# Copyright 2026 Capstone MCP contributors.
"""Numerical analysis of explicitly supplied Capstone measurement samples."""

import math
from typing import Annotated, Final

from pydantic import Field, FiniteFloat

from capstone_mcp.models import Model

MIN_COMPARISON_RUNS: Final = 2
MAX_DIAGNOSTIC_SAMPLES: Final = 256


class AnalysisError(ValueError):
    """The samples cannot support the requested numerical analysis."""


class FitInput(Model):
    """Paired samples; callers retain responsibility for units and run identity."""

    x: Annotated[list[FiniteFloat], Field(min_length=3, max_length=1_000_000)]
    y: Annotated[list[FiniteFloat], Field(min_length=3, max_length=1_000_000)]


class LinearFitDiagnostics(Model):
    """Descriptive OLS diagnostics that do not establish model validity.

    Leverage is the diagonal of the intercept-model hat matrix. Cook's distance
    uses two fitted parameters and residual variance RSS/(n-2); it is undefined
    when that variance is zero or the sample leverage equals one.
    ``influential_indices`` reports samples with Cook's distance greater than
    the descriptive 4/n threshold, without testing significance or removing
    observations. Lag-1 correlation is the Pearson correlation between adjacent
    residuals in supplied order, or ``None`` when either lagged series is
    constant.
    Per-sample arrays and influential indices are bounded to 256 entries for
    MCP responses; summary calculations still use every supplied sample.
    """

    residuals: list[float]
    leverage: list[float]
    cooks_distance: list[float | None]
    influential_indices: list[int]
    lag1_residual_correlation: float | None
    sample_count: int
    truncated: bool
    influential_count: int


class LinearFit(Model):
    """Ordinary least squares with an intercept and residual-based standard errors."""

    count: int
    slope: float
    intercept: float
    slope_standard_error: float
    intercept_standard_error: float
    residual_standard_error: float
    r_squared: float | None
    diagnostics: LinearFitDiagnostics


def linear_fit(samples: FitInput) -> LinearFit:
    """Fit OLS with an intercept and attach diagnostics without dropping samples."""
    if len(samples.x) != len(samples.y):
        msg = "x and y must contain the same number of paired samples."
        raise AnalysisError(msg)
    count = len(samples.x)
    mean_x = math.fsum(value / count for value in samples.x)
    mean_y = math.fsum(value / count for value in samples.y)
    dx = [value - mean_x for value in samples.x]
    dy = [value - mean_y for value in samples.y]
    sxx = math.fsum(value * value for value in dx)
    sxy = math.fsum(x * y for x, y in zip(dx, dy, strict=True))
    syy = math.fsum(value * value for value in dy)
    if sxx == 0 or not all(math.isfinite(v) for v in (sxx, sxy, syy)):
        msg = "x has no usable variation or sample magnitudes exceed float precision."
        raise AnalysisError(msg)
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    residuals = [y - slope * x for x, y in zip(dx, dy, strict=True)]
    residual_sum = math.fsum(value * value for value in residuals)
    variance = residual_sum / (count - 2)
    leverage = [1 / count + value * value / sxx for value in dx]
    cooks_distance = [
        None
        if variance == 0 or sample_leverage == 1
        else (
            residual * residual
            / (2 * variance)
            * sample_leverage
            / ((1 - sample_leverage) ** 2)
        )
        for residual, sample_leverage in zip(residuals, leverage, strict=True)
    ]
    threshold = 4 / count
    influential_indices = [
        index
        for index, distance in enumerate(cooks_distance)
        if distance is not None and distance > threshold
    ]
    lag_count = count - 1
    lagged = residuals[:-1]
    leading = residuals[1:]
    lagged_mean = math.fsum(value / lag_count for value in lagged)
    leading_mean = math.fsum(value / lag_count for value in leading)
    lagged_sum = math.fsum((value - lagged_mean) ** 2 for value in lagged)
    leading_sum = math.fsum((value - leading_mean) ** 2 for value in leading)
    if lagged_sum == 0 or leading_sum == 0:
        lag1_correlation = None
    else:
        lag1_numerator = math.fsum(
            (lagged_value - lagged_mean) * (leading_value - leading_mean)
            for lagged_value, leading_value in zip(lagged, leading, strict=True)
        )
        lag1_correlation = max(
            -1.0,
            min(
                1.0,
                lag1_numerator / math.sqrt(lagged_sum) / math.sqrt(leading_sum),
            ),
        )
    result = LinearFit(
        count=count,
        slope=slope,
        intercept=intercept,
        slope_standard_error=math.sqrt(variance / sxx),
        intercept_standard_error=math.sqrt(
            variance * (1 / count + mean_x * mean_x / sxx),
        ),
        residual_standard_error=math.sqrt(variance),
        r_squared=None if syy == 0 else 1 - residual_sum / syy,
        diagnostics=LinearFitDiagnostics(
            residuals=residuals[:MAX_DIAGNOSTIC_SAMPLES],
            leverage=leverage[:MAX_DIAGNOSTIC_SAMPLES],
            cooks_distance=cooks_distance[:MAX_DIAGNOSTIC_SAMPLES],
            influential_indices=influential_indices[:MAX_DIAGNOSTIC_SAMPLES],
            lag1_residual_correlation=lag1_correlation,
            sample_count=count, truncated=count > MAX_DIAGNOSTIC_SAMPLES,
            influential_count=len(influential_indices),
        ),
    )
    if not all(math.isfinite(value) for value in (
        result.slope, result.intercept, result.slope_standard_error,
        result.intercept_standard_error, result.residual_standard_error,
        *residuals, *leverage,
    )) or not all(
        distance is None or math.isfinite(distance)
        for distance in cooks_distance
    ) or (
        result.diagnostics.lag1_residual_correlation is not None
        and not math.isfinite(result.diagnostics.lag1_residual_correlation)
    ):
        msg = "Fit results exceed finite floating-point precision."
        raise AnalysisError(msg)
    return result


class RunSamples(Model):
    """One explicitly named run in a common measurement unit."""

    name: Annotated[str, Field(min_length=1)]
    values: Annotated[list[FiniteFloat], Field(min_length=1, max_length=1_000_000)]


class RunComparison(Model):
    """Per-run summary; standard deviation is undefined for a single sample."""

    name: str
    count: int
    mean: float
    sample_standard_deviation: float | None
    minimum: float
    maximum: float
    mean_difference_from_first: float


def compare_runs(runs: list[RunSamples]) -> list[RunComparison]:
    """Compare run distributions, without assuming time alignment or equal lengths."""
    if len(runs) < MIN_COMPARISON_RUNS or len({run.name for run in runs}) != len(runs):
        msg = "Provide at least two runs with distinct names, using the same unit."
        raise AnalysisError(msg)
    results: list[RunComparison] = []
    baseline = math.fsum(value / len(runs[0].values) for value in runs[0].values)
    for run in runs:
        count = len(run.values)
        mean = math.fsum(value / count for value in run.values)
        squared = math.fsum((value - mean) ** 2 for value in run.values)
        deviation = math.sqrt(squared / (count - 1)) if count > 1 else None
        difference = mean - baseline
        if not math.isfinite(difference) or (
            deviation is not None and not math.isfinite(deviation)
        ):
            msg = "Run statistics exceed finite floating-point precision."
            raise AnalysisError(msg)
        results.append(RunComparison(
            name=run.name, count=count, mean=mean,
            sample_standard_deviation=deviation,
            minimum=min(run.values), maximum=max(run.values),
            mean_difference_from_first=difference,
        ))
    return results
