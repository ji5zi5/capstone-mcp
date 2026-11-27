# Copyright 2026 Capstone MCP contributors.
"""Deep Numerics Engine: statistics, linear/polynomial regressions, and sparklines."""

from capstone_mcp.numerics.regression import (
    LinearRegressionResult,
    PolynomialRegressionResult,
    fit_linear_series,
    fit_polynomial_series,
    fit_weighted_linear_series,
)
from capstone_mcp.numerics.sparklines import (
    render_ascii_sparkline,
    render_svg_sparkline,
)
from capstone_mcp.numerics.spectral import (
    SpectralPeak,
    SpectralResult,
    compute_power_spectrum,
)
from capstone_mcp.numerics.summary import (
    SeriesSummary,
    compute_series_summary,
)

__all__ = [
    "LinearRegressionResult",
    "PolynomialRegressionResult",
    "SeriesSummary",
    "SpectralPeak",
    "SpectralResult",
    "compute_power_spectrum",
    "compute_series_summary",
    "fit_linear_series",
    "fit_polynomial_series",
    "fit_weighted_linear_series",
    "render_ascii_sparkline",
    "render_svg_sparkline",
]
