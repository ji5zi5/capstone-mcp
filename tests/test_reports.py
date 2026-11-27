# Copyright 2026 Capstone MCP contributors.
"""Deterministic unit and integration tests for the Physics Lab Report Engine."""

import math
import os
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
from capstone_mcp.reports.output import write_report_file
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
        "Elapsed": [0, 1, 2, 3, 4],
        "Stopping Voltage": voltages,
        "Frequency": freqs,
    }
    report = generate_report(
        experiment_id="photoelectric_effect",
        data_series=series,
    )

    assert report.metadata.experiment_id == "photoelectric_effect"
    is_match = (
        "Photoelectric" in report.metadata.title or "광전 효과" in report.metadata.title
    )
    assert is_match
    assert report.regression is not None
    assert report.regression.r_squared == pytest.approx(1.0, rel=1e-4)

    assert len(report.error_analysis) >= 1
    h_row = next(r for r in report.error_analysis if r.symbol == "h")
    assert h_row.experimental_value == pytest.approx(PLANCK_CONSTANT, rel=1e-3)
    assert h_row.relative_error_percent < 1.0


def test_photoelectric_report_does_not_use_unidentified_axes() -> None:
    report = generate_report(
        experiment_id="photoelectric_effect",
        data_series={"Time": [1, 2, 3], "Current": [2, 4, 6]},
    )

    assert report.error_analysis == []
    assert report.regression is None
    assert report.plotted_data_points == {}


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


def test_adiabatic_cycle_is_summarized_without_a_spurious_gamma() -> None:
    report = generate_report(
        experiment_id="adiabatic_gas",
        data_series={"Volume": [30, 20, 10, 20, 30], "Pressure": [10, 20, 30, 22, 10]},
    )
    assert report.data_summaries[0].count == 5
    assert report.regression is None
    assert not report.error_analysis


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


def test_report_csv_fit_never_pairs_samples_from_different_rows(tmp_path: Path) -> None:
    path = tmp_path / "sparse.csv"
    _ = path.write_text("x;y\n0,0;0,0\n1,0;\n;200,0\n3,0;6,0\n", encoding="utf-8")

    report = generate_report(file_path_or_run=str(path))

    assert [summary.count for summary in report.data_summaries] == [3, 3]
    assert report.regression is not None
    assert report.regression.slope == pytest.approx(2.0)
    assert report.regression.intercept == pytest.approx(0.0)
    assert len(report.raw_data_points["x"]) == 4


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


def test_markdown_keeps_external_labels_inside_their_sections() -> None:
    report = generate_report(
        experiment_id="generic", data_series={"x": [1, 2], "y": [3, 4]},
        title="Trial\n# 2", apparatus=["Sensor <optical>"],
    )
    report.metadata.channels_or_sensors["A | B"] = "`meter`"
    report = report.model_copy(update={"ascii_plot": "trial\n```\nend"})
    md = render_markdown(report)
    assert "Trial &#35; 2" in md
    assert "Sensor &lt;optical&gt;" in md
    assert "| A &#124; B | &#96;meter&#96; |" in md
    assert "````text\ntrial\n```\nend\n````" in md


def test_additional_regressions_appear_in_both_report_formats() -> None:
    report = generate_report(experiment_id="generic", data_series={"x": [1, 2], "y": [3, 4]})
    extra = RegressionSummary(model_name="Second observation", slope=2.0, intercept=1.0)
    report.additional_regressions.append(extra)
    for rendered in (render_markdown(report), render_html(report)):
        assert rendered.index("Linear Fit") < rendered.index("Second observation")
    only_extra = report.model_copy(update={"regression": None})
    assert "Second observation" in render_markdown(only_extra)
    assert "Second observation" in render_html(only_extra)


def test_render_html_output() -> None:
    x = [1.0, 2.0, 3.0]
    y = [2.0, 4.0, 6.0]
    report = generate_report(
        experiment_id="generic",
        data_series={"x": x, "y": y},
        title="Custom Linear Experiment",
        apparatus=["Sensor <optical>"],
    )
    report = report.model_copy(update={"metadata": report.metadata.model_copy(
        update={"channels_or_sensors": {"Ch A": "Optical & position"}},
    )})
    html = render_html(report)
    assert "<!DOCTYPE html>" in html
    assert "<title>Laboratory Report: Custom Linear Experiment</title>" in html
    assert "<table" in html
    assert "<style>" in html
    assert "<h2>3. Apparatus &amp; Setup Configuration</h2>" in html
    assert "Sensor &lt;optical&gt;" in html
    assert "<td>Ch A</td><td>Optical &amp; position</td>" in html
    assert "<h2>4. Measured Data & Statistics</h2>" in html


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


@pytest.mark.parametrize(("count", "display"), [(2, "N/A"), (3, "0.000e+00")])
def test_report_preserves_standard_error_availability(count: int, display: str) -> None:
    x, y = [0.0, 1.0, 2.0][:count], [0.0, 2.0, 4.0][:count]
    report = generate_report(data_series={"x": x, "y": y})
    assert report.regression is not None
    expected = None if count == 2 else 0.0
    assert report.regression.slope_error == expected
    assert report.regression.intercept_error == expected
    assert render_markdown(report).count(f"std err: `{display}`") == 2
    assert render_html(report).count(f"std err: <code>{display}</code>") == 2


def test_report_svg_omits_nonfinite_points_and_bounds_its_output() -> None:
    report = generate_report(data_series={"x": [1, 2], "y": [2, 4]})
    values = [0.0] * 5_000
    values[503] = 100.0
    raw = {"x": [None, math.nan, math.inf, *range(5_000)], "y": [200.0] * 3 + values}
    html = render_html(report.model_copy(update={"raw_data_points": raw}))

    assert 2 <= html.count("<circle ") <= 1_000
    assert 'cy="30.0"' in html
    assert 'cx="nan"' not in html
    assert 'cx="inf"' not in html


def test_report_svg_clips_regression_outside_sample_bounds() -> None:
    report = generate_report(data_series={"x": [0, 1, 2], "y": [0, 0, 1]})
    rendered = render_html(report)

    assert (
        '<clipPath id="report-plot-clip"><rect x="60" y="30" '
        'width="550" height="260"/></clipPath>'
    ) in rendered
    assert 'y1="333.3"' in rendered
    assert 'stroke-dasharray="4,2" clip-path="url(#report-plot-clip)"' in rendered


def test_html_report_without_constant_comparisons_omits_empty_table() -> None:
    report = generate_report(data_series={"x": [0, 1], "y": [0, 2]})
    section = render_html(report).split("<h2>6. Error Analysis</h2>", 1)[1]
    section = section.split("<h2>", 1)[0]

    assert "No constant comparisons configured for this experiment." in section
    assert "<table>" not in section


@pytest.mark.parametrize("source", [None, "missing_run_sample"])
def test_report_requires_explicit_sample_request(source: str | None) -> None:
    with pytest.raises(ValueError, match="No experimental"):
        generate_report(file_path_or_run=source, experiment_id="photoelectric_effect")


@pytest.mark.parametrize("column", ["x", "Velocity (m/s)"])
def test_inline_report_json_is_data_not_a_run_name(column: str) -> None:
    source = f'{{"{column}": [1, 2], "y": [2, 4]}}'
    report = generate_report(file_path_or_run=source)
    assert report.metadata.run_name is None
    assert [summary.variable_name for summary in report.data_summaries] == [column, "y"]


@pytest.mark.anyio
async def test_capstone_generate_lab_report_tool(tmp_path: Path) -> None:
    out_file = tmp_path / "test_report.md"
    result = await capstone_generate_lab_report(
        file_path_or_run="sample",
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
    assert "Sample / Demonstration" in saved_text


@pytest.mark.anyio
async def test_large_tool_report_preserves_statistics_and_declares_preview_lengths(
    tmp_path: Path,
) -> None:
    count = 9_000
    path = tmp_path / "observations.csv"
    path.write_text("x,y\n" + "".join(f"{i},{2 * i}\n" for i in range(count)))
    result = await capstone_generate_lab_report(file_path_or_run=str(path))
    report = result.lab_report
    assert report.original_point_counts == {"raw_data_points": {"x": count, "y": count}}
    x, y = report.raw_data_points["x"], report.raw_data_points["y"]
    assert 0 < len(x) < count
    assert len(x) == len(y)
    assert y == [2 * i for i in range(len(x))]
    assert report.data_summaries[1].max == 2 * (count - 1)
    assert report.data_summaries[0].count == count


@pytest.mark.parametrize("invalid", [0.0, -1.0, float("nan"), float("inf")])
def test_adiabatic_report_rejects_invalid_absolute_pressure(invalid: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        generate_report(
            experiment_id="adiabatic_gas",
            data_series={"Volume": [1.0, 2.0, 3.0], "Pressure": [100.0, invalid, 50.0]},
        )


def test_explicit_sample_is_labeled_as_demonstration() -> None:
    with pytest.raises(ValueError, match="No experimental data"):
        generate_report(experiment_id="photoelectric_effect")
    report = generate_report(
        file_path_or_run="sample", experiment_id="photoelectric_effect",
    )
    assert "Sample / Demonstration" in report.metadata.title
def test_report_output_preserves_existing_html(tmp_path: Path) -> None:
    markdown = tmp_path / "report.md"
    html = markdown.with_suffix(".html")
    html.write_text("Existing report", encoding="utf-8")

    with pytest.raises(FileExistsError):
        write_report_file(str(markdown), "both", "# Report", "<p>New report</p>")

    assert html.read_text(encoding="utf-8") == "Existing report"
    assert not markdown.exists()


def test_report_write_failure_leaves_no_partial_output(tmp_path: Path) -> None:
    markdown = tmp_path / "report.md"
    html = markdown.with_suffix(".html")

    with pytest.raises(UnicodeEncodeError):
        write_report_file(str(markdown), "both", "# Report", "\ud800")

    assert not markdown.exists()
    assert not html.exists()
    write_report_file(str(markdown), "both", "# Report", "<p>Report</p>")
    assert markdown.read_text(encoding="utf-8") == "# Report"
    assert html.read_text(encoding="utf-8") == "<p>Report</p>"


@pytest.mark.skipif(os.name != "nt", reason="Windows exclusive rename")
def test_report_preserves_file_created_during_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    markdown = tmp_path / "report.md"
    html = markdown.with_suffix(".html")
    rename = Path.rename

    def race(source: Path, target: Path) -> Path:
        if target == html:
            html.write_text("Concurrent report", encoding="utf-8")
        return rename(source, target)

    monkeypatch.setattr(Path, "rename", race)

    with pytest.raises(FileExistsError):
        write_report_file(str(markdown), "both", "# Report", "<p>Report</p>")

    assert list(tmp_path.iterdir()) == [html]
    assert html.read_text(encoding="utf-8") == "Concurrent report"


@pytest.mark.skipif(os.name != "nt", reason="Windows alternate data stream")
def test_report_rejects_an_alternate_data_stream(tmp_path: Path) -> None:
    existing = tmp_path / "existing.md"
    existing.write_text("Existing report", encoding="utf-8")
    stream = f"{existing}:report"

    with pytest.raises(ValueError, match="ordinary filesystem path"):
        write_report_file(stream, "markdown", "# Report", None)

    assert existing.read_text(encoding="utf-8") == "Existing report"
