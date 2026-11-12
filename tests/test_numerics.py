# Copyright 2026 Capstone MCP contributors.
"""Tests for the Deep Numerics Engine (statistics, regressions, and sparklines)."""

import math

import pytest

from capstone_mcp.numerics import (
    compute_series_summary,
    fit_linear_series,
    fit_polynomial_series,
    render_ascii_sparkline,
    render_svg_sparkline,
)


def test_compute_series_summary_valid() -> None:
    """Ensure accurate statistics for standard numeric series."""
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    summary = compute_series_summary(values)

    assert summary.count == 5
    assert math.isclose(summary.mean, 3.0)
    assert math.isclose(summary.min_val, 1.0)
    assert math.isclose(summary.max_val, 5.0)
    assert math.isclose(summary.peak_val, 5.0)
    assert summary.std_dev > 0.0


def test_compute_series_summary_empty_raises() -> None:
    """Ensure empty series raises ValueError."""
    with pytest.raises(ValueError, match="empty"):
        compute_series_summary([])


def test_fit_linear_series_exact() -> None:
    """Verify exact linear fit for y = 2x + 1."""
    x = [0.0, 1.0, 2.0, 3.0, 4.0]
    y = [1.0, 3.0, 5.0, 7.0, 9.0]
    result = fit_linear_series(x, y)

    assert math.isclose(result.slope, 2.0, abs_tol=1e-7)
    assert math.isclose(result.intercept, 1.0, abs_tol=1e-7)
    assert math.isclose(result.r_squared, 1.0, abs_tol=1e-7)
    assert len(result.residuals) == 5
    for r in result.residuals:
        assert math.isclose(r, 0.0, abs_tol=1e-7)


def test_fit_linear_series_insufficient_points() -> None:
    """Ensure series with fewer than 2 points raises ValueError."""
    with pytest.raises(ValueError, match="at least 2 points"):
        fit_linear_series([1.0], [2.0])


def test_fit_linear_series_length_mismatch() -> None:
    """Ensure mismatched x and y lengths raise ValueError."""
    with pytest.raises(ValueError, match="Mismatched lengths"):
        fit_linear_series([1.0, 2.0], [3.0])


def test_fit_linear_series_zero_variance_x() -> None:
    """Ensure vertical data (zero x variance) raises ValueError."""
    with pytest.raises(ValueError, match="zero variance"):
        fit_linear_series([2.0, 2.0, 2.0], [1.0, 2.0, 3.0])


def test_fit_polynomial_series_quadratic() -> None:
    """Verify polynomial fit for y = x^2."""
    x = [-2.0, -1.0, 0.0, 1.0, 2.0]
    y = [4.0, 1.0, 0.0, 1.0, 4.0]
    result = fit_polynomial_series(x, y, degree=2)

    assert result.degree == 2
    assert math.isclose(result.r_squared, 1.0, abs_tol=1e-5)
    assert math.isclose(result.coefficients[2], 1.0, abs_tol=1e-4)


def test_render_ascii_sparkline() -> None:
    """Verify ASCII chart rendering outputs non-empty grid with title."""
    x = [0.0, 1.0, 2.0, 3.0, 4.0]
    y = [10.0, 20.0, 35.0, 25.0, 50.0]
    chart = render_ascii_sparkline(x, y, width=30, height=8, title="Test Plot")

    assert "Test Plot" in chart
    assert len(chart.splitlines()) >= 8


def test_render_svg_sparkline() -> None:
    """Verify SVG rendering outputs valid SVG markup with viewBox and paths."""
    x = [0.0, 1.0, 2.0, 3.0, 4.0]
    y = [1.0, 3.0, 5.0, 7.0, 9.0]
    svg = render_svg_sparkline(x, y, fit_x=x, fit_y=y, title="Linear SVG")

    assert svg.startswith("<svg")
    assert "</svg>" in svg
    assert "Linear SVG" in svg
    assert "circle" in svg
    assert "path" in svg
