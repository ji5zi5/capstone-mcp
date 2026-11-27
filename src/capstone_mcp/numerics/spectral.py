# Copyright 2026 Capstone MCP contributors.
"""Pure-Python Fourier spectrum and window-gain analysis without GUI scraping."""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING, Final, Literal

if TYPE_CHECKING:
    from collections.abc import Sequence

MIN_SPECTRAL_SAMPLES: Final[int] = 4
MAX_SPECTRAL_SAMPLES: Final[int] = 16_384
MAX_DIRECT_DFT_SAMPLES: Final[int] = 2048
STEP_UNIFORMITY_TOLERANCE: Final[float] = 0.05


@dataclass(frozen=True)
class SpectralPeak:
    """Single-sided amplitude spectrum peak in physical Hz."""

    frequency_hz: float
    amplitude: float
    power_fraction: float


@dataclass(frozen=True)
class SpectralResult:
    """Single-sided DFT/FFT output over uniformly sampled real observations."""

    sample_count: int
    sample_rate_hz: float
    frequency_resolution_hz: float
    window: Literal["hann", "rectangular"]
    frequencies_hz: list[float]
    amplitudes: list[float]
    peaks: list[SpectralPeak]


def _radix2_fft(values: list[complex]) -> list[complex]:
    """Iterative Cooley-Tukey radix-2 FFT for power-of-two lengths."""
    n = len(values)
    out = values.copy()
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            out[i], out[j] = out[j], out[i]

    size = 2
    while size <= n:
        half = size >> 1
        step = -2.0j * math.pi / size
        for start in range(0, n, size):
            for k in range(half):
                twiddle = cmath.exp(step * k) * out[start + k + half]
                top = out[start + k]
                out[start + k] = top + twiddle
                out[start + k + half] = top - twiddle
        size <<= 1
    return out


def _direct_dft(values: list[float]) -> list[complex]:
    """Exact single-sided positive-frequency DFT bins for general N."""
    n = len(values)
    bins = n // 2 + 1
    angle_step = -2.0 * math.pi / n
    spectrum: list[complex] = []
    for k in range(bins):
        re = math.fsum(
            v * math.cos(angle_step * k * idx) for idx, v in enumerate(values)
        )
        im = math.fsum(
            v * math.sin(angle_step * k * idx) for idx, v in enumerate(values)
        )
        spectrum.append(complex(re, im))
    return spectrum


def _window_weights(n: int, window: Literal["hann", "rectangular"]) -> list[float]:
    if window == "rectangular":
        return [1.0] * n
    if n <= 1:
        return [1.0] * n
    return [0.5 * (1.0 - math.cos(2.0 * math.pi * idx / (n - 1))) for idx in range(n)]


def _validate_spectral_inputs(
    times_s: Sequence[float],
    values: Sequence[float],
    window: Literal["hann", "rectangular"],
    top_peaks: int,
) -> tuple[list[float], list[float], float]:
    """Validate spectral arrays and uniform timestamp spacing."""
    if len(times_s) != len(values):
        msg = "times_s and values must have identical lengths."
        raise ValueError(msg)
    n = len(times_s)
    if not MIN_SPECTRAL_SAMPLES <= n <= MAX_SPECTRAL_SAMPLES:
        msg = (
            f"Spectral analysis needs between {MIN_SPECTRAL_SAMPLES} "
            f"and {MAX_SPECTRAL_SAMPLES} samples."
        )
        raise ValueError(msg)
    if window not in {"hann", "rectangular"}:
        msg = "window must be 'hann' or 'rectangular'."
        raise ValueError(msg)
    if top_peaks < 1:
        msg = "top_peaks must be at least 1."
        raise ValueError(msg)

    ts = [float(t) for t in times_s]
    ys = [float(y) for y in values]
    if not all(math.isfinite(v) for v in (*ts, *ys)):
        msg = "Spectral inputs must be finite."
        raise ValueError(msg)

    dts = [b - a for a, b in pairwise(ts)]
    mean_dt = math.fsum(dts) / len(dts)
    if mean_dt <= 0 or min(dts) <= 0:
        msg = "Timestamps must be strictly increasing."
        raise ValueError(msg)
    if any(abs(dt - mean_dt) > STEP_UNIFORMITY_TOLERANCE * mean_dt for dt in dts):
        msg = "Spectral analysis requires nearly uniform sample spacing (within 5%)."
        raise ValueError(msg)
    return ts, ys, mean_dt


def _transform_real_spectrum(weighted: list[float]) -> list[complex]:
    """Select radix-2 FFT for power-of-two lengths or exact DFT otherwise."""
    n = len(weighted)
    if (n & (n - 1)) == 0:
        return _radix2_fft([complex(v, 0.0) for v in weighted])[: n // 2 + 1]
    if n <= MAX_DIRECT_DFT_SAMPLES:
        return _direct_dft(weighted)
    msg = (
        "Large arbitrary non-power-of-two FFT sizes above 2048 are not "
        "supported without zero-padding."
    )
    raise ValueError(msg)


def compute_power_spectrum(
    times_s: Sequence[float],
    values: Sequence[float],
    *,
    window: Literal["hann", "rectangular"] = "hann",
    remove_dc: bool = True,
    top_peaks: int = 5,
) -> SpectralResult:
    """Compute calibrated single-sided FFT/DFT amplitudes from uniform timestamps."""
    ts, ys, mean_dt = _validate_spectral_inputs(times_s, values, window, top_peaks)
    n = len(ts)
    centered = [y - (math.fsum(ys) / n) for y in ys] if remove_dc else ys
    weights = _window_weights(n, window)
    weight_sum = math.fsum(weights)
    weighted = [y * w for y, w in zip(centered, weights, strict=True)]
    bins = _transform_real_spectrum(weighted)

    sample_rate = 1.0 / mean_dt
    df = sample_rate / n
    freqs = [idx * df for idx in range(len(bins))]
    amplitudes: list[float] = []
    for idx, coeff in enumerate(bins):
        scale = 1.0 if idx == 0 or (n % 2 == 0 and idx == n // 2) else 2.0
        amplitudes.append((abs(coeff) * scale) / weight_sum)

    powers = [amp * amp for amp in amplitudes]
    total_power = math.fsum(powers)
    candidates = list(range(1, len(amplitudes)))
    ranked = sorted(candidates, key=amplitudes.__getitem__, reverse=True)[:top_peaks]
    peaks = [
        SpectralPeak(
            frequency_hz=freqs[idx],
            amplitude=amplitudes[idx],
            power_fraction=(powers[idx] / total_power) if total_power > 0 else 0.0,
        )
        for idx in ranked
    ]
    return SpectralResult(
        sample_count=n,
        sample_rate_hz=sample_rate,
        frequency_resolution_hz=df,
        window=window,
        frequencies_hz=freqs,
        amplitudes=amplitudes,
        peaks=peaks,
    )
