# Copyright 2026 Capstone MCP contributors.
"""Deterministic unit and integration tests for the Physics Lab Report Engine."""

import math
from pathlib import Path

import pytest

from capstone_mcp.reports.generator import (
    ADIABATIC_INDEX_AIR,
    ELEMENTARY_CHARGE,
    PLANCK_CONSTANT,
    SPEED_OF_LIGHT,
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
from capstone_mcp.server import capstone_generate_lab_report


def test_models_instantiation_and_serialization() -> None:
    metadata = ExperimentMetadata(
        experiment_id="photoelectric_effect",
        title="Photoelectric Effect Experiment",
        date="2026-11-12",
        apparatus=["Mercury Lamp", "Photodiode Enclosure"],
        domain="Modern Physics",
        description="Measurement of Planck's constant",
    )
    summary = DataSummary(
        variable_name="Stopping Voltage",
        unit="V",
        count=5,
        mean=1.24,
        std_dev=0.15,
        min=0.45,
        max=1.85,
        peak_value=1.85,
    )
    reg = RegressionSummary(
        model_name="Linear Fit",
        slope=4.135e-15,
        intercept=-1.85,
        r_squared=0.998,
        slope_error=5e-17,
        intercept_error=0.02,
        equation="V_0 = 4.135e-15 * f - 1.85",
        x_variable="Frequency",
        y_variable="Stopping Voltage",
        x_unit="Hz",
        y_unit="V",
    )
    diff = abs(6.625e-34 - PLANCK_CONSTANT)
    error_row = ErrorAnalysisRow(
        parameter_name="Planck's Constant (h)",
        symbol="h",
        accepted_value=PLANCK_CONSTANT,
        experimental_value=6.625e-34,
        unit="J*s",
        absolute_error=diff,
        relative_error_percent=diff / PLANCK_CONSTANT * 100,
    )
    report = LabReport(
        metadata=metadata,
        theory_summary="Testing Einstein photoelectric equation",
        governing_equations=["eV_0 = hf - phi"],
        data_summaries=[summary],
        regression=reg,
        error_analysis=[error_row],
        ascii_plot="[Plot]",
        discussion_questions=["Why does cutoff frequency exist?"],
        conclusion="Planck's constant verified within experimental uncertainty.",
    )

    data = report.model_dump()
    assert data["metadata"]["experiment_id"] == "photoelectric_effect"
    assert data["regression"]["r_squared"] == 0.998
    assert len(data["error_analysis"]) == 1
    assert data["error_analysis"][0]["symbol"] == "h"


def test_compute_data_summary() -> None:
    values = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
    summary = compute_data_summary(values, "Voltage", "V")
    assert summary.variable_name == "Voltage"
    assert summary.unit == "V"
    assert summary.count == 8
    assert summary.mean == 5.0
    assert summary.min == 2.0
    assert summary.max == 9.0
    assert summary.peak_value == 9.0
    assert summary.std_dev == pytest.approx(math.sqrt(32.0 / 7.0))


def test_compute_data_summary_single_value() -> None:
    summary = compute_data_summary([42.0], "Single", "m")
    assert summary.count == 1
    assert summary.mean == 42.0
    assert summary.std_dev is None
    assert summary.min == 42.0
    assert summary.max == 42.0


def test_compute_data_summary_empty() -> None:
    summary = compute_data_summary([], "Empty")
    assert summary.count == 0
    assert summary.mean == 0.0
    assert summary.std_dev is None


def test_compute_linear_regression_exact_line() -> None:
    x = [0.0, 1.0, 2.0, 3.0, 4.0]
    y = [1.0, 3.0, 5.0, 7.0, 9.0]
    reg = compute_linear_regression(
        x,
        y,
        variable_names=("t", "x"),
        units=("s", "m"),
    )
    assert reg.slope == pytest.approx(2.0)
    assert reg.intercept == pytest.approx(1.0)
    assert reg.r_squared == pytest.approx(1.0)
    assert reg.slope_error == pytest.approx(0.0, abs=1e-12)
    assert "2.000" in reg.equation or "2" in reg.equation


def test_compute_linear_regression_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match="same length"):
        compute_linear_regression([1.0, 2.0], [1.0])


def test_compute_linear_regression_insufficient_points() -> None:
    with pytest.raises(ValueError, match="At least 2 points"):
        compute_linear_regression([1.0], [2.0])


def test_compute_error_analysis() -> None:
    row = compute_error_analysis(
        accepted_value=100.0,
        experimental_value=102.5,
        parameter_name="Test Parameter",
        symbol="T",
        unit="K",
    )
    assert row.parameter_name == "Test Parameter"
    assert row.symbol == "T"
    assert row.accepted_value == 100.0
    assert row.experimental_value == 102.5
    assert row.absolute_error == pytest.approx(2.5)
    assert row.relative_error_percent == pytest.approx(2.5)


def test_physical_constants_presence() -> None:
    assert pytest.approx(6.62607015e-34) == PLANCK_CONSTANT
    assert pytest.approx(2.99792458e8) == SPEED_OF_LIGHT
    assert pytest.approx(1.602176634e-19) == ELEMENTARY_CHARGE
    assert pytest.approx(1.40) == ADIABATIC_INDEX_AIR


def test_generate_ascii_plot() -> None:
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    y = [10.0, 20.0, 30.0, 40.0, 50.0]
    plot = generate_ascii_plot(
        x,
        y,
        fit=(10.0, 0.0),
        size=(40, 10),
    )
    assert isinstance(plot, str)
    assert len(plot.splitlines()) >= 10
    assert "*" in plot or "o" in plot


def test_generate_report_photoelectric_effect() -> None:
    freqs = [5.19e14, 5.49e14, 6.88e14, 7.41e14, 8.22e14]
    phi_ev = 1.85
    h_over_e = PLANCK_CONSTANT / ELEMENTARY_CHARGE
    voltages = [h_over_e * f - phi_ev for f in freqs]

    series = {
        "Frequency": freqs,
        "Stopping Voltage": voltages,
    }
    report = generate_report(
        experiment_id="photoelectric_effect",
        data_series=series,
    )

    assert report.metadata.experiment_id == "photoelectric_effect"
    is_match = (
        "Photoelectric" in report.metadata.title
        or "광전 효과" in report.metadata.title
    )
    assert is_match
    assert report.regression is not None
    assert report.regression.r_squared == pytest.approx(1.0, rel=1e-4)

    assert len(report.error_analysis) >= 1
    h_row = next(r for r in report.error_analysis if r.symbol == "h")
    assert h_row.experimental_value == pytest.approx(PLANCK_CONSTANT, rel=1e-3)
    assert h_row.relative_error_percent < 1.0


def test_generate_report_rlc_resonance() -> None:
    frequencies = [100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0]
    voltages = [0.1, 0.3, 0.7, 1.5, 3.2, 1.4, 0.6, 0.2]
    series = {
        "Frequency": frequencies,
        "Resistor Voltage": voltages,
    }
    report = generate_report(
        experiment_id="rlc_resonance",
        data_series=series,
    )
    assert report.metadata.experiment_id == "rlc_resonance"
    assert any(r.symbol in ("f_0", "f0") for r in report.error_analysis)


def test_generate_report_adiabatic_gas() -> None:
    volumes = [100.0, 80.0, 60.0, 40.0]
    pressures = [100.0 * ((100.0 / v) ** 1.4) for v in volumes]
    series = {"Volume": volumes, "Pressure": pressures}
    report = generate_report(
        experiment_id="adiabatic_gas",
        data_series=series,
    )
    assert report.metadata.experiment_id == "adiabatic_gas"
    assert len(report.error_analysis) >= 1
    gamma_row = next(r for r in report.error_analysis if r.symbol == "gamma")
    assert gamma_row.experimental_value == pytest.approx(1.40, rel=1e-3)


def test_generate_report_from_csv_file(tmp_path: Path) -> None:
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("x,y\n1.0,2.0\n2.0,4.0\n3.0,6.0\n", encoding="utf-8")
    report = generate_report(
        file_path_or_run=str(csv_file),
        experiment_id="generic",
    )
    assert len(report.data_summaries) == 2
    assert report.regression is not None
    assert report.regression.slope == pytest.approx(2.0)


def test_render_markdown_output() -> None:
    x = [1.0, 2.0, 3.0]
    y = [2.0, 4.0, 6.0]
    report = generate_report(
        experiment_id="generic",
        data_series={"x": x, "y": y},
        title="Custom Linear Experiment",
    )
    md = render_markdown(report)
    assert "# Laboratory Report: Custom Linear Experiment" in md
    assert "## 1. Executive Summary" in md
    assert "## 4. Experimental Data & Summary Statistics" in md
    assert "## 5. Regression & Curve Fitting" in md
    assert "```text" in md


def test_render_html_output() -> None:
    x = [1.0, 2.0, 3.0]
    y = [2.0, 4.0, 6.0]
    report = generate_report(
        experiment_id="generic",
        data_series={"x": x, "y": y},
        title="Custom Linear Experiment",
    )
    html = render_html(report)
    assert "<!DOCTYPE html>" in html
    assert "<title>Laboratory Report: Custom Linear Experiment</title>" in html
    assert "<table" in html
    assert "<style>" in html


def test_render_report_formats() -> None:
    report = generate_report(
        experiment_id="generic",
        data_series={"x": [1.0, 2.0], "y": [3.0, 4.0]},
    )
    res_md = render_report(report, report_format="markdown")
    assert "markdown" in res_md
    assert "html" not in res_md

    res_html = render_report(report, report_format="html")
    assert "html" in res_html
    assert "markdown" not in res_html

    res_both = render_report(report, report_format="both")
    assert "markdown" in res_both
    assert "html" in res_both


@pytest.mark.anyio
async def test_capstone_generate_lab_report_tool(tmp_path: Path) -> None:
    out_file = tmp_path / "test_report.md"
    result = await capstone_generate_lab_report(
        file_path_or_run="photoelectric_effect_sample",
        experiment_id="photoelectric_effect",
        output_path=str(out_file),
        format="markdown",
    )
    assert isinstance(result, GenerateLabReportResult)
    assert result.experiment_id == "photoelectric_effect"
    assert result.report_markdown is not None
    assert out_file.exists()
    saved_text = out_file.read_text(encoding="utf-8")
    assert "Laboratory Report" in saved_text
