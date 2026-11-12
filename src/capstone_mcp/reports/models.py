# Copyright 2026 Capstone MCP contributors.
"""Data models for automated physics laboratory report generation."""

from typing import Literal

from pydantic import Field

from capstone_mcp.models import Model


class ExperimentMetadata(Model):
    """Provenance and apparatus metadata for a laboratory experiment."""

    experiment_id: str
    title: str
    date: str
    apparatus: list[str] = Field(default_factory=list)
    domain: str = ""
    description: str = ""
    channels_or_sensors: dict[str, str] = Field(default_factory=dict)
    run_name: str | None = None


class DataSummary(Model):
    """Summary statistics for one measured or derived physical variable."""

    variable_name: str
    unit: str = ""
    count: int
    mean: float
    std_dev: float | None = None
    min: float
    max: float
    peak_value: float | None = None
    samples_preview: list[float] = Field(default_factory=list)


class RegressionSummary(Model):
    """Numerical regression parameters and goodness-of-fit metrics."""

    model_name: str = "Linear Fit"
    slope: float
    intercept: float
    r_squared: float | None = None
    slope_error: float | None = None
    intercept_error: float | None = None
    equation: str = ""
    x_variable: str = "x"
    y_variable: str = "y"
    x_unit: str = ""
    y_unit: str = ""


class ErrorAnalysisRow(Model):
    """Comparison between experimental result and theoretical physical constant."""

    parameter_name: str
    symbol: str = ""
    accepted_value: float
    experimental_value: float
    unit: str = ""
    absolute_error: float
    relative_error_percent: float


class LabReport(Model):
    """Comprehensive post-experiment physics laboratory report."""

    metadata: ExperimentMetadata
    theory_summary: str = ""
    governing_equations: list[str] = Field(default_factory=list)
    data_summaries: list[DataSummary] = Field(default_factory=list)
    regression: RegressionSummary | None = None
    additional_regressions: list[RegressionSummary] = Field(default_factory=list)
    error_analysis: list[ErrorAnalysisRow] = Field(default_factory=list)
    ascii_plot: str = ""
    raw_data_points: dict[str, list[float]] = Field(default_factory=dict)
    discussion_questions: list[str] = Field(default_factory=list)
    conclusion: str = ""


class GenerateLabReportResult(Model):
    """Tool invocation result returned by capstone_generate_lab_report."""

    experiment_id: str
    title: str
    format: Literal["markdown", "html", "both"]
    output_path: str | None = None
    report_markdown: str | None = None
    report_html: str | None = None
    summary: str = ""
    lab_report: LabReport
