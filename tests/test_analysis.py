# Copyright 2026 Capstone MCP contributors.
"""Deterministic numerical checks for analysis of measured samples."""

import math

import pytest
from pydantic import ValidationError

from capstone_mcp.analysis import (
    AnalysisError,
    FitInput,
    RunSamples,
    compare_runs,
    linear_fit,
)


def test_fit_recovers_exact_line() -> None:
    # Given
    samples = FitInput(x=[0, 1, 2, 3], y=[3, 5, 7, 9])
    # When
    result = linear_fit(samples)
    # Then
    assert result.slope == 2
    assert result.intercept == 3
    assert result.slope_standard_error == 0
    assert result.r_squared == 1
    assert result.diagnostics.residuals == [0, 0, 0, 0]
    assert result.diagnostics.leverage == pytest.approx([0.7, 0.3, 0.3, 0.7])
    assert result.diagnostics.cooks_distance == [None, None, None, None]
    assert result.diagnostics.influential_indices == []
    assert result.diagnostics.lag1_residual_correlation is None


def test_fit_reports_residual_based_standard_error() -> None:
    # Given: centered x, and a residual orthogonal to x and the constant vector.
    samples = FitInput(x=[-1, 0, 1], y=[0, -2, 2])
    # When
    result = linear_fit(samples)
    # Then
    assert result.slope == 1
    assert result.intercept == 0
    assert result.slope_standard_error == pytest.approx(math.sqrt(3))
    assert result.intercept_standard_error == pytest.approx(math.sqrt(2))
    assert result.r_squared == pytest.approx(0.25)


def test_fit_reports_descriptive_influence_diagnostics() -> None:
    # Given: exact hand-calculated OLS and Cook's-distance fixtures.
    samples = FitInput(x=[0, 1, 2, 3, 4], y=[0, 1, 2, 3, 10])
    # When
    result = linear_fit(samples)
    # Then
    assert result.diagnostics.leverage == pytest.approx([0.6, 0.3, 0.2, 0.3, 0.6])
    assert result.diagnostics.cooks_distance == pytest.approx([
        0.5625,
        0,
        0.046875,
        18 / 49,
        2.25,
    ])
    assert result.diagnostics.influential_indices == [4]
    assert result.diagnostics.lag1_residual_correlation == pytest.approx(
        -1 / math.sqrt(7),
    )


def test_fit_keeps_residuals_in_supplied_pair_order() -> None:
    # Given: the same fitted pairs in a deliberately non-monotonic order.
    samples = FitInput(x=[4, 0, 3, 1, 2], y=[10, 0, 3, 1, 2])
    # When
    result = linear_fit(samples)
    # Then
    assert result.diagnostics.residuals == pytest.approx([2.4, 1.2, -2.4, 0, -1.2])


def test_diagnostics_are_bounded_without_truncating_the_fit() -> None:
    # Given: an influential sample beyond the returned diagnostic window.
    values = [float(index) for index in range(300)]
    samples = FitInput(x=values, y=[*values[:-1], values[-1] + 200])
    # When
    result = linear_fit(samples)
    # Then: all samples influence OLS and the influence scan, not only the prefix.
    assert result.count == result.diagnostics.sample_count == 300
    assert result.slope == pytest.approx(1 + 200 * 149.5 / (300 * (300**2 - 1) / 12))
    assert result.diagnostics.truncated
    assert len(result.diagnostics.residuals) == 256
    assert len(result.diagnostics.cooks_distance) == 256
    assert 299 in result.diagnostics.influential_indices


def test_unit_leverage_has_undefined_cooks_distance() -> None:
    # Given: one sample uniquely determines its fitted value.
    result = linear_fit(FitInput(x=[-1, -1, 2], y=[0, 1, 2]))
    # Then: division by (1-h)^2 is not disguised as a finite influence measure.
    assert result.diagnostics.leverage[2] == 1
    assert result.diagnostics.cooks_distance[2] is None


@pytest.mark.parametrize(
    ("x", "y"),
    [([1, 1, 1], [1, 2, 3]), ([1, 2, 3], [1, 2, 3, 4])],
)
def test_fit_rejects_unusable_pairing(x: list[float], y: list[float]) -> None:
    # Given
    samples = FitInput(x=x, y=y)
    # When / Then
    with pytest.raises(AnalysisError):
        _ = linear_fit(samples)


def test_fit_keeps_large_finite_magnitudes_usable() -> None:
    # Given
    base = 1e150
    step = math.ulp(base)
    values = [base + index * step for index in range(4)]
    samples = FitInput(x=values, y=values)
    # When
    result = linear_fit(samples)
    # Then
    assert result.slope == 1
    assert result.intercept == 0
    assert result.residual_standard_error == 0
    assert result.r_squared == 1


def test_input_rejects_nonfinite_samples() -> None:
    # Given / When / Then
    with pytest.raises(ValidationError):
        _ = FitInput(x=[0, 1, 2], y=[1, float("nan"), 3])


def test_constant_y_has_no_defined_r_squared() -> None:
    # Given
    samples = FitInput(x=[0, 1, 2], y=[4, 4, 4])
    # When
    result = linear_fit(samples)
    # Then
    assert result.slope == 0
    assert result.intercept == 4
    assert result.r_squared is None


def test_run_comparison_keeps_unequal_sample_counts() -> None:
    # Given
    runs = [
        RunSamples(name="first", values=[1, 2, 3]),
        RunSamples(name="second", values=[5]),
    ]
    # When
    results = compare_runs(runs)
    # Then
    assert results[0].sample_standard_deviation == 1
    assert results[1].sample_standard_deviation is None
    assert results[1].mean_difference_from_first == 3
    assert [result.count for result in results] == [3, 1]
