# Copyright 2026 Capstone MCP contributors.
"""Tests for FFT/DFT power spectrum analysis and weighted linear regression."""

from __future__ import annotations

import math

import pytest

from capstone_mcp.numerics import (
    compute_power_spectrum,
    fit_linear_series,
    fit_weighted_linear_series,
)


def test_compute_power_spectrum_radix2_recovers_exact_tones() -> None:
    sample_count = 128
    sample_rate_hz = 64.0
    dt = 1.0 / sample_rate_hz
    times = [idx * dt for idx in range(sample_count)]
    # Exact bin-centered tones at 5 Hz (amp 3.0) and 12 Hz (amp 1.2) + DC offset 2.5
    signal = [
        2.5
        + 3.0 * math.cos(2.0 * math.pi * 5.0 * t)
        + 1.2 * math.sin(2.0 * math.pi * 12.0 * t)
        for t in times
    ]
    result = compute_power_spectrum(
        times,
        signal,
        window="rectangular",
        remove_dc=True,
        top_peaks=3,
    )

    assert result.sample_count == sample_count
    assert result.sample_rate_hz == pytest.approx(sample_rate_hz)
    assert result.frequency_resolution_hz == pytest.approx(0.5)
    assert result.amplitudes[0] == pytest.approx(0.0, abs=1e-12)
    assert result.peaks[0].frequency_hz == pytest.approx(5.0)
    assert result.peaks[0].amplitude == pytest.approx(3.0, rel=1e-6)
    assert result.peaks[1].frequency_hz == pytest.approx(12.0)
    assert result.peaks[1].amplitude == pytest.approx(1.2, rel=1e-6)
    assert 0.8 < result.peaks[0].power_fraction < 0.9


def test_compute_power_spectrum_non_power_of_two_dft_and_hann_window() -> None:
    sample_count = 100
    dt = 0.01  # 100 Hz, df = 1.0 Hz
    times = [idx * dt for idx in range(sample_count)]
    signal = [4.0 * math.cos(2.0 * math.pi * 10.0 * t) for t in times]

    rect = compute_power_spectrum(times, signal, window="rectangular")
    hann = compute_power_spectrum(times, signal, window="hann")

    assert rect.peaks[0].frequency_hz == pytest.approx(10.0)
    assert rect.peaks[0].amplitude == pytest.approx(4.0, rel=1e-4)
    assert hann.window == "hann"
    assert hann.peaks[0].frequency_hz == pytest.approx(10.0)
    assert hann.peaks[0].amplitude > 3.5


def test_compute_power_spectrum_preserves_dc_when_requested() -> None:
    times = [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75]
    signal = [5.0 + math.cos(2.0 * math.pi * 1.0 * t) for t in times]
    res = compute_power_spectrum(times, signal, window="rectangular", remove_dc=False)
    assert res.amplitudes[0] == pytest.approx(5.0, abs=1e-9)


def test_compute_power_spectrum_rejects_invalid_spacing_and_sizes() -> None:
    with pytest.raises(ValueError, match="between 4 and"):
        compute_power_spectrum([0.0, 0.1, 0.2], [1.0, 2.0, 3.0])

    with pytest.raises(ValueError, match="strictly increasing"):
        compute_power_spectrum([0.0, 0.1, 0.1, 0.2], [1.0, 2.0, 3.0, 4.0])

    with pytest.raises(ValueError, match="nearly uniform"):
        compute_power_spectrum([0.0, 0.1, 0.2, 0.6], [1.0, 2.0, 3.0, 4.0])


def test_weighted_linear_regression_matches_ols_and_downweights_outliers() -> None:
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    y = [2.0, 4.0, 6.0, 8.0, 12.0]  # Last point has excess noise

    ols = fit_linear_series(x, y)
    equal_w = fit_weighted_linear_series(x, y, [1.0] * 5)
    assert equal_w.slope == pytest.approx(ols.slope)
    assert equal_w.intercept == pytest.approx(ols.intercept)
    assert equal_w.r_squared == pytest.approx(ols.r_squared)

    # Low weight on noisy point x=5 recovers true y = 2*x slope closely.
    weighted = fit_weighted_linear_series(x, y, [100.0, 100.0, 100.0, 100.0, 0.01])
    assert abs(weighted.slope - 2.0) < abs(ols.slope - 2.0)
    assert weighted.slope == pytest.approx(2.0, abs=1e-3)
    assert weighted.intercept == pytest.approx(0.0, abs=2e-3)


def test_weighted_linear_regression_validation_errors() -> None:
    with pytest.raises(ValueError, match="matching lengths"):
        fit_weighted_linear_series([1.0, 2.0], [1.0, 2.0], [1.0])

    with pytest.raises(ValueError, match="strictly positive weights"):
        fit_weighted_linear_series([1.0, 2.0], [1.0, 2.0], [1.0, 0.0])

    with pytest.raises(ValueError, match="zero variance"):
        fit_weighted_linear_series([3.0, 3.0, 3.0], [1.0, 2.0, 3.0], [1.0, 1.0, 1.0])
