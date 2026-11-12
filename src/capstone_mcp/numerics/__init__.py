# Copyright 2026 Capstone MCP contributors.
"""Deep Numerics Engine: statistics, linear/polynomial regressions, and sparklines."""

from capstone_mcp.numerics.regression import (
    LinearRegressionResult,
    PolynomialRegressionResult,
    fit_linear_series,
    fit_polynomial_series,
)
from capstone_mcp.numerics.sparklines import (
    render_ascii_sparkline,
    render_svg_sparkline,
)
from capstone_mcp.numerics.summary import (
    SeriesSummary,
    compute_series_summary,
)

__all__ = [
    "LinearRegressionResult",
    "PolynomialRegressionResult",
    "SeriesSummary",
    "compute_series_summary",
    "fit_linear_series",
    "fit_polynomial_series",
    "render_ascii_sparkline",
    "render_svg_sparkline",
]
