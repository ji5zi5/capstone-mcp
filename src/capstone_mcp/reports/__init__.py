# Copyright 2026 Capstone MCP contributors.
"""Automated physics lab report generation engine."""

from capstone_mcp.reports.generator import (
    ADIABATIC_INDEX_AIR,
    ELEMENTARY_CHARGE,
    PLANCK_CONSTANT,
    SPEED_OF_LIGHT,
    STANDARD_GRAVITY,
    compute_data_summary,
    compute_error_analysis,
    compute_linear_regression,
    generate_ascii_plot,
    generate_report,
)
from capstone_mcp.reports.models import (
    DataSummary,
    ErrorAnalysisRow,
    ExperimentMetadata,
    GenerateLabReportResult,
    LabReport,
    RegressionSummary,
)
from capstone_mcp.reports.templates import (
    render_html,
    render_markdown,
    render_report,
)

__all__ = [
    "ADIABATIC_INDEX_AIR",
    "ELEMENTARY_CHARGE",
    "PLANCK_CONSTANT",
    "SPEED_OF_LIGHT",
    "STANDARD_GRAVITY",
    "DataSummary",
    "ErrorAnalysisRow",
    "ExperimentMetadata",
    "GenerateLabReportResult",
    "LabReport",
    "RegressionSummary",
    "compute_data_summary",
    "compute_error_analysis",
    "compute_linear_regression",
    "generate_ascii_plot",
    "generate_report",
    "render_html",
    "render_markdown",
    "render_report",
]
