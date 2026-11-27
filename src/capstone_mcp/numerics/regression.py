# Copyright 2026 Capstone MCP contributors.
"""Linear and polynomial regression analysis with residual diagnostics."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, localcontext
from itertools import pairwise
from typing import Final

MIN_LINEAR_POINTS: Final[int] = 2


def strictly_monotonic(values: Sequence[float]) -> bool:
    """Whether the independent variable moves in one direction along the whole run."""
    return all(a < b for a, b in pairwise(values)) or all(
        a > b for a, b in pairwise(values)
    )


@dataclass(frozen=True)
class LinearRegressionResult:
    """Results from an Ordinary Least Squares (OLS) linear fit: y = m*x + b."""

    slope: float
    intercept: float
    r_squared: float
    std_err_slope: float | None
    std_err_intercept: float | None
    residuals: list[float]


@dataclass(frozen=True)
class PolynomialRegressionResult:
    """Results from a polynomial fit: y = c0 + c1*x + c2*x^2 + ..."""

    coefficients: list[float]
    r_squared: float
    degree: int


def _rescale_ratio(value: float, numerator: float, denominator: float) -> float:
    """Apply a scale ratio without overflowing an intermediate quotient."""
    value_m, value_e = math.frexp(value)
    num_m, num_e = math.frexp(numerator)
    den_m, den_e = math.frexp(denominator)
    try:
        return math.ldexp(value_m * num_m / den_m, value_e + num_e - den_e)
    except OverflowError as exc:
        msg = "Regression result exceeds the finite floating-point range."
        raise ValueError(msg) from exc


def fit_linear_series(
    x: Sequence[float],
    y: Sequence[float],
) -> LinearRegressionResult:
    """Perform OLS linear regression on two series: y = m*x + b.

    Args:
        x: Independent variable series.
        y: Dependent variable series.

    Returns:
        LinearRegressionResult with slope, intercept, R^2, errors, and residuals.

    Raises:
        ValueError: If series have mismatched lengths or fewer than 2 points.
    """
    if len(x) != len(y):
        msg = f"Mismatched lengths: len(x)={len(x)} vs len(y)={len(y)}"
        raise ValueError(msg)

    if any(math.isinf(v) for v in (*x, *y)):
        msg = "Regression requires finite measurements; infinity is not supported."
        raise ValueError(msg)

    pairs = [
        (float(xi), float(yi))
        for xi, yi in zip(x, y, strict=True)
        if not (math.isnan(xi) or math.isnan(yi))
    ]
    n = len(pairs)
    if n < MIN_LINEAR_POINTS:
        msg = f"Need at least {MIN_LINEAR_POINTS} points for linear regression, got {n}"
        raise ValueError(msg)

    clean_x = [p[0] for p in pairs]
    clean_y = [p[1] for p in pairs]

    # Normalize before centering and squaring: units must not decide whether
    # nonconstant data has variance, or overflow otherwise finite input.
    x_scale = max(abs(v) for v in clean_x) or 1.0
    y_scale = max(abs(v) for v in clean_y) or 1.0
    scaled_x = [v / x_scale for v in clean_x]
    scaled_y = [v / y_scale for v in clean_y]
    mean_x = math.fsum(scaled_x) / n
    mean_y = math.fsum(scaled_y) / n
    dx = [v - mean_x for v in scaled_x]
    dy = [v - mean_y for v in scaled_y]
    ss_xx = math.fsum(v * v for v in dx)
    if ss_xx == 0.0:
        msg = "Independent variable x has zero variance (cannot fit vertical line)"
        raise ValueError(msg)
    ss_yy = math.fsum(v * v for v in dy)
    ss_xy = math.fsum(a * b for a, b in zip(dx, dy, strict=True))
    scaled_slope = ss_xy / ss_xx
    slope = _rescale_ratio(scaled_slope, y_scale, x_scale)
    intercept = (mean_y - scaled_slope * mean_x) * y_scale
    scaled_residuals = [b - scaled_slope * a for a, b in zip(dx, dy, strict=True)]
    residuals = [r * y_scale for r in scaled_residuals]
    ss_res = math.fsum(r * r for r in scaled_residuals)
    r_squared = max(0.0, min(1.0, 1.0 - ss_res / ss_yy)) if ss_yy else 1.0
    std_err_slope = std_err_intercept = None
    if n > MIN_LINEAR_POINTS:
        mse = ss_res / (n - 2)
        std_err_slope = _rescale_ratio(math.sqrt(mse / ss_xx), y_scale, x_scale)
        std_err_intercept = math.sqrt(mse * (1.0 / n + mean_x**2 / ss_xx)) * y_scale
    if not all(
        v is None or math.isfinite(v)
        for v in (slope, intercept, std_err_slope, std_err_intercept, *residuals)
    ):
        msg = "Regression result exceeds the finite floating-point range."
        raise ValueError(msg)

    return LinearRegressionResult(
        slope=slope,
        intercept=intercept,
        r_squared=r_squared,
        std_err_slope=std_err_slope,
        std_err_intercept=std_err_intercept,
        residuals=residuals,
    )


def _polynomial_qr(x: list[float], y: list[float], degree: int) -> list[float]:
    """Reorthogonalized QR avoids squaring the normalized design condition number."""
    columns: list[list[float]] = []
    upper = [[0.0] * (degree + 1) for _ in range(degree + 1)]
    for power in range(degree + 1):
        vector = [value**power for value in x]
        original_norm = math.sqrt(math.fsum(value * value for value in vector))
        for _ in range(2):
            for index, column in enumerate(columns):
                projection = math.fsum(
                    a * b for a, b in zip(column, vector, strict=True)
                )
                upper[index][power] += projection
                vector = [
                    b - projection * a for a, b in zip(column, vector, strict=True)
                ]
        norm = math.sqrt(math.fsum(value * value for value in vector))
        if norm <= math.ulp(1.0) * max(len(x), degree + 1) * original_norm:
            msg = "Singular or numerically unresolved polynomial design."
            raise ValueError(msg)
        upper[power][power] = norm
        columns.append([value / norm for value in vector])
    rhs = [
        math.fsum(a * b for a, b in zip(column, y, strict=True)) for column in columns
    ]
    coefficients = [0.0] * (degree + 1)
    for index in range(degree, -1, -1):
        tail = math.fsum(
            upper[index][j] * coefficients[j] for j in range(index + 1, degree + 1)
        )
        coefficients[index] = (rhs[index] - tail) / upper[index][index]
    return coefficients


def _original_polynomial_basis(
    coefficients: list[float],
    center: float,
    scale: float,
    y_scale: float,
) -> list[float]:
    """Compose c((x-center)/scale) without intermediate binary overflow."""
    with localcontext() as context:
        context.prec = max(80, 4 * len(coefficients))
        inverse = Decimal(1) / Decimal(scale)
        shift = -Decimal(center) * inverse
        result = [Decimal(0)]
        for coefficient in reversed(coefficients):
            expanded = [Decimal(0)] * (len(result) + 1)
            for index, value in enumerate(result):
                expanded[index] += value * shift
                expanded[index + 1] += value * inverse
            expanded[0] += Decimal(coefficient)
            result = expanded
        result = [value * Decimal(y_scale) for value in result[:-1]]
        converted = [float(value) for value in result]
        if any(
            not math.isfinite(v) or (v == 0 and d != 0)
            for v, d in zip(converted, result, strict=True)
        ):
            msg = "Polynomial coefficients exceed the finite floating-point range."
            raise ValueError(msg)
        return converted


def _validate_original_polynomial(  # noqa: PLR0913, PLR0917
    xs: list[float], normalized_x: list[float], coefficients: list[float],
    original: list[float], y_scale: float, residual: float,
) -> None:
    """Reject coefficient output that loses the fitted curve when evaluated."""
    # Compare in y-normalized units. sqrt(epsilon) reserves half the binary
    # precision for the basis conversion; residual RMS scales the noise floor.
    precision = math.sqrt(math.ulp(1.0))
    residual_rms = math.sqrt(residual / len(xs))
    for x_value, normalized in zip(xs, normalized_x, strict=True):
        expected = 0.0
        for coefficient in reversed(coefficients):
            expected = expected * normalized + coefficient
        observed = 0.0
        for coefficient in reversed(original):
            observed = observed * x_value + coefficient
        observed /= y_scale
        tolerance = precision * (
            len(original) * max(1.0, abs(expected)) + residual_rms
        )
        if not math.isfinite(observed) or abs(observed - expected) > tolerance:
            msg = "Original-basis polynomial coefficients are numerically unstable."
            raise ValueError(msg)


def fit_polynomial_series(
    x: Sequence[float],
    y: Sequence[float],
    degree: int = 2,
) -> PolynomialRegressionResult:
    """Fit a centered/scaled polynomial by QR; return original-basis coefficients."""
    if degree < 1:
        msg = f"Polynomial degree must be >= 1, got {degree}"
        raise ValueError(msg)
    pairs = [(float(a), float(b)) for a, b in zip(x, y, strict=True)]
    if not all(math.isfinite(value) for pair in pairs for value in pair):
        msg = "Polynomial samples must be finite."
        raise ValueError(msg)
    if len(pairs) <= degree:
        msg = (
            f"Need at least {degree + 1} points for degree {degree} fit, "
            f"got {len(pairs)}"
        )
        raise ValueError(msg)
    xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
    center = min(xs) / 2 + max(xs) / 2
    scale = max(abs(value - center) for value in xs)
    if scale == 0:
        msg = "Singular polynomial design: independent variable has zero variance."
        raise ValueError(msg)
    y_scale = max(abs(value) for value in ys) or 1.0
    normalized_x = [(value - center) / scale for value in xs]
    normalized_y = [value / y_scale for value in ys]
    coefficients = _polynomial_qr(normalized_x, normalized_y, degree)
    original = _original_polynomial_basis(coefficients, center, scale, y_scale)
    mean_y = math.fsum(normalized_y) / len(pairs)
    total = math.fsum((value - mean_y) ** 2 for value in normalized_y)
    residual = math.fsum(
        (yi - math.fsum(c * xi**p for p, c in enumerate(coefficients))) ** 2
        for xi, yi in zip(normalized_x, normalized_y, strict=True)
    )
    _validate_original_polynomial(
        xs, normalized_x, coefficients, original, y_scale, residual,
    )
    r_squared = max(0.0, min(1.0, 1 - residual / total)) if total else 1.0
    return PolynomialRegressionResult(
        coefficients=original, r_squared=r_squared, degree=degree,
    )
