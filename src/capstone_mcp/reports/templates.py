# Copyright 2026 Capstone MCP contributors.
"""Templates for publication-ready Markdown and HTML physics laboratory reports."""

from __future__ import annotations

import html
from typing import TYPE_CHECKING, Final, Literal

if TYPE_CHECKING:
    from capstone_mcp.reports.models import LabReport

MIN_DATA_POINTS_FOR_PLOT: Final[int] = 2


def _render_md_header(report: LabReport) -> list[str]:
    meta = report.metadata
    lines = [
        f"# Laboratory Report: {meta.title}",
        "",
        f"**Date:** {meta.date}  ",
        f"**Experiment ID:** `{meta.experiment_id}`  ",
        f"**Domain:** {meta.domain or 'Physics Laboratory'}  ",
    ]
    if meta.run_name:
        lines.append(f"**Run Name:** `{meta.run_name}`  ")
    lines.append("")
    return lines


def _render_md_theory(report: LabReport) -> list[str]:
    meta = report.metadata
    lines = [
        "## 1. Executive Summary",
        "",
        meta.description or report.theory_summary or "No summary provided.",
        "",
        "## 2. Theoretical Background & Governing Equations",
        "",
        report.theory_summary or "Theoretical framework and principles.",
        "",
    ]
    if report.governing_equations:
        lines.append("**Governing Physical Equations:**")
        lines.append("")
        lines.extend(f"- $${eq}$$" for eq in report.governing_equations)
        lines.append("")
    return lines


def _render_md_apparatus(report: LabReport) -> list[str]:
    meta = report.metadata
    lines = ["## 3. Apparatus & Setup Configuration", ""]
    if meta.apparatus:
        lines.append("**Equipment List:**")
        lines.extend(f"- {item}" for item in meta.apparatus)
        lines.append("")

    if meta.channels_or_sensors:
        lines.extend([
            "**Interface Channels & Sensor Bindings:**",
            "",
            "| Channel / Port | Sensor / Role |",
            "| :--- | :--- |",
        ])
        lines.extend(
            f"| `{ch}` | {sen} |"
            for ch, sen in meta.channels_or_sensors.items()
        )
        lines.append("")
    return lines


def _render_md_data(report: LabReport) -> list[str]:
    lines = ["## 4. Experimental Data & Summary Statistics", ""]
    if not report.data_summaries:
        return lines

    lines.extend([
        "| Variable | Unit | Count | Mean | Std Dev | Min | Max | Peak |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ])
    for s in report.data_summaries:
        sd_str = f"{s.std_dev:.4g}" if s.std_dev is not None else "N/A"
        peak_str = f"{s.peak_value:.4g}" if s.peak_value is not None else "N/A"
        lines.append(
            f"| **{s.variable_name}** | {s.unit or '-'} | {s.count} | "
            f"{s.mean:.4g} | {sd_str} | {s.min:.4g} | {s.max:.4g} | "
            f"{peak_str} |",
        )
    lines.append("")
    return lines


def _render_md_regression(report: LabReport) -> list[str]:
    lines = ["## 5. Regression & Curve Fitting", ""]
    if report.regression:
        reg = report.regression
        se_m = f"`{reg.slope_error:.3e}`" if reg.slope_error else "'N/A'"
        se_b = f"`{reg.intercept_error:.3e}`" if reg.intercept_error else "'N/A'"
        r2_s = f"`{reg.r_squared:.4f}`" if reg.r_squared is not None else "'N/A'"
        lines.extend([
            f"**Model:** {reg.model_name}  ",
            f"**Fitted Equation:** `{reg.equation}`  ",
            f"- **Slope ($m$):** `{reg.slope:.5e}` (std err: {se_m})  ",
            f"- **Intercept ($b$):** `{reg.intercept:.5e}` (std err: {se_b})  ",
            f"- **Coefficient of Determination ($R^2$):** {r2_s}  ",
            "",
        ])
    if report.ascii_plot:
        lines.extend([
            "### Visual Data Fit (ASCII Plot)",
            "",
            "```text",
            report.ascii_plot,
            "```",
            "",
        ])
    return lines


def _render_md_errors(report: LabReport) -> list[str]:
    lines = ["## 6. Error Analysis & Accepted Physical Constants", ""]
    if not report.error_analysis:
        lines.extend(["No constant comparisons configured for this experiment.", ""])
        return lines

    lines.extend([
        (
            "| Parameter | Symbol | Accepted Value | Experimental Value | "
            "Unit | Absolute Error | Relative Error |"
        ),
        "| :--- | :---: | :--- | :--- | :--- | :--- | :---: |",
    ])
    lines.extend(
        f"| **{r.parameter_name}** | `${r.symbol}$` | "
        f"`{r.accepted_value:.4e}` | `{r.experimental_value:.4e}` | "
        f"{r.unit or '-'} | `{r.absolute_error:.3e}` | "
        f"**{r.relative_error_percent:.2f}%** |"
        for r in report.error_analysis
    )
    lines.append("")
    return lines


def render_markdown(report: LabReport) -> str:
    """Render a structured LabReport into publication-ready Markdown."""
    lines: list[str] = []
    lines.extend(_render_md_header(report))
    lines.extend(_render_md_theory(report))
    lines.extend(_render_md_apparatus(report))
    lines.extend(_render_md_data(report))
    lines.extend(_render_md_regression(report))
    lines.extend(_render_md_errors(report))

    if report.discussion_questions:
        lines.extend(["## 7. Discussion & Conceptual Analysis", ""])
        lines.extend(
            f"{i}. **{q}**"
            for i, q in enumerate(report.discussion_questions, start=1)
        )
        lines.append("")

    lines.extend([
        "## 8. Conclusion",
        "",
        report.conclusion or "Analysis complete.",
        "",
    ])
    return "\n".join(lines)


def _render_svg_plot(
    report: LabReport,
    width: int = 640,
    height: int = 340,
) -> str:
    if (
        not report.raw_data_points
        or len(report.raw_data_points) < MIN_DATA_POINTS_FOR_PLOT
    ):
        return ""

    keys = list(report.raw_data_points.keys())
    x_vals = report.raw_data_points[keys[0]]
    y_vals = report.raw_data_points[keys[1]]

    if (
        len(x_vals) < MIN_DATA_POINTS_FOR_PLOT
        or len(x_vals) != len(y_vals)
    ):
        return ""

    min_x, max_x = min(x_vals), max(x_vals)
    min_y, max_y = min(y_vals), max(y_vals)
    span_x = max_x - min_x or 1.0
    span_y = max_y - min_y or 1.0

    margin_left, margin_right = 60, 30
    margin_top, margin_bottom = 30, 50
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom

    def map_x(val: float) -> float:
        return margin_left + ((val - min_x) / span_x) * plot_w

    def map_y(val: float) -> float:
        return margin_top + plot_h - ((val - min_y) / span_y) * plot_h

    svg_elements: list[str] = [
        (
            f'<svg viewBox="0 0 {width} {height}" class="report-svg" '
            'xmlns="http://www.w3.org/2000/svg">'
        ),
        f'<rect width="{width}" height="{height}" fill="#fafbfc" rx="6"/>',
        (
            f'<line x1="{margin_left}" y1="{margin_top}" '
            f'x2="{margin_left}" y2="{margin_top + plot_h}" '
            'stroke="#cbd5e1" stroke-width="1.5"/>'
        ),
        (
            f'<line x1="{margin_left}" y1="{margin_top + plot_h}" '
            f'x2="{margin_left + plot_w}" y2="{margin_top + plot_h}" '
            'stroke="#cbd5e1" stroke-width="1.5"/>'
        ),
    ]

    if report.regression and report.regression.slope is not None:
        slope = report.regression.slope
        intercept = report.regression.intercept
        y1_fit = slope * min_x + intercept
        y2_fit = slope * max_x + intercept
        svg_elements.append(
            f'<line x1="{map_x(min_x):.1f}" y1="{map_y(y1_fit):.1f}" '
            f'x2="{map_x(max_x):.1f}" y2="{map_y(y2_fit):.1f}" '
            'stroke="#2563eb" stroke-width="2.5" stroke-dasharray="4,2"/>',
        )

    for px, py in zip(x_vals, y_vals, strict=True):
        svg_elements.append(
            f'<circle cx="{map_x(px):.1f}" cy="{map_y(py):.1f}" r="4.5" '
            'fill="#dc2626" stroke="#ffffff" stroke-width="1.5"/>',
        )

    x_mid = margin_left + plot_w / 2
    y_mid = margin_top + plot_h / 2
    svg_elements.extend([
        (
            f'<text x="{margin_left}" y="{height - 15}" font-size="12" '
            f'fill="#64748b" text-anchor="middle">{min_x:.2e}</text>'
        ),
        (
            f'<text x="{margin_left + plot_w}" y="{height - 15}" '
            f'font-size="12" fill="#64748b" text-anchor="middle">'
            f'{max_x:.2e}</text>'
        ),
        (
            f'<text x="{x_mid}" y="{height - 12}" font-size="13" '
            'font-weight="600" fill="#334155" text-anchor="middle">'
            f'{html.escape(keys[0])}</text>'
        ),
        (
            f'<text x="{margin_left - 10}" y="{margin_top + plot_h}" '
            f'font-size="12" fill="#64748b" text-anchor="end">{min_y:.2e}</text>'
        ),
        (
            f'<text x="{margin_left - 10}" y="{margin_top + 10}" '
            f'font-size="12" fill="#64748b" text-anchor="end">{max_y:.2e}</text>'
        ),
        (
            f'<text x="20" y="{y_mid}" font-size="13" font-weight="600" '
            'fill="#334155" text-anchor="middle" '
            f'transform="rotate(-90 20 {y_mid})">{html.escape(keys[1])}</text>'
        ),
        "</svg>",
    ])
    return "\n".join(svg_elements)


def _render_html_css() -> str:
    return """
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      line-height: 1.65;
      color: #1e293b;
      max-width: 880px;
      margin: 0 auto;
      padding: 40px 24px;
    }
    h1 {
      font-size: 2.2rem;
      font-weight: 700;
      color: #0f172a;
      border-bottom: 2px solid #e2e8f0;
      padding-bottom: 12px;
    }
    h2 {
      font-size: 1.4rem;
      font-weight: 600;
      margin-top: 32px;
      border-bottom: 1px solid #e2e8f0;
      padding-bottom: 6px;
    }
    .meta-bar {
      display: flex;
      flex-wrap: wrap;
      gap: 16px;
      background: #f8fafc;
      padding: 12px 18px;
      border-radius: 6px;
      border: 1px solid #e2e8f0;
      margin-bottom: 24px;
    }
    .meta-label { font-weight: 600; color: #64748b; }
    table { width: 100%; border-collapse: collapse; margin: 16px 0; }
    th, td { padding: 8px 12px; border: 1px solid #e2e8f0; text-align: left; }
    th { background-color: #f8fafc; font-weight: 600; }
    .text-right { text-align: right; }
    .text-center { text-align: center; }
    .card {
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 16px 20px;
      margin: 16px 0;
    }
    .equation-card {
      background: #f1f5f9;
      padding: 8px 14px;
      border-left: 4px solid #2563eb;
      margin: 8px 0;
      font-family: monospace;
      font-weight: bold;
    }
    pre.ascii-plot {
      background: #0f172a;
      color: #38bdf8;
      padding: 14px;
      border-radius: 6px;
      overflow-x: auto;
      font-family: monospace;
      font-size: 0.85rem;
    }
    .report-svg {
      width: 100%;
      max-width: 640px;
      height: auto;
      display: block;
      margin: 16px auto;
      border: 1px solid #e2e8f0;
      border-radius: 6px;
    }
    .badge {
      padding: 3px 8px;
      border-radius: 4px;
      font-size: 0.85rem;
      font-weight: 600;
      background: #e0f2fe;
      color: #0369a1;
    }
    """


def _render_html_body_header(report: LabReport) -> list[str]:
    meta = report.metadata
    sections = [
        f"  <h1>Laboratory Report: {html.escape(meta.title)}</h1>",
        '  <div class="meta-bar">',
        (
            f'    <div><span class="meta-label">Date:</span> '
            f'{html.escape(meta.date)}</div>'
        ),
        (
            f'    <div><span class="meta-label">Experiment ID:</span> '
            f'<code>{html.escape(meta.experiment_id)}</code></div>'
        ),
        (
            f'    <div><span class="meta-label">Domain:</span> '
            f'{html.escape(meta.domain or "Physics")}</div>'
        ),
    ]
    if meta.run_name:
        sections.append(
            f'    <div><span class="meta-label">Run:</span> '
            f'<code>{html.escape(meta.run_name)}</code></div>',
        )
    sections.extend([
        "  </div>",
        "  <h2>1. Executive Summary</h2>",
        f"  <p>{html.escape(meta.description or report.theory_summary)}</p>",
        "  <h2>2. Theoretical Background & Equations</h2>",
        f"  <p>{html.escape(report.theory_summary)}</p>",
    ])
    sections.extend(
        f'  <div class="equation-card">{html.escape(eq)}</div>'
        for eq in report.governing_equations
    )
    return sections


def _render_html_body_data(report: LabReport) -> list[str]:
    sections = [
        "  <h2>3. Measured Data & Statistics</h2>",
        "  <table>",
        (
            "    <thead><tr><th>Variable</th><th>Unit</th><th>Count</th>"
            "<th>Mean</th><th>Std Dev</th><th>Min</th><th>Max</th><th>Peak</th>"
            "</tr></thead>"
        ),
        "    <tbody>",
    ]
    for s in report.data_summaries:
        sd = f"{s.std_dev:.4g}" if s.std_dev is not None else "N/A"
        pk = f"{s.peak_value:.4g}" if s.peak_value is not None else "N/A"
        sections.append(
            f"      <tr><td><strong>{html.escape(s.variable_name)}</strong></td>"
            f"<td>{html.escape(s.unit or '-')}</td>"
            f'<td class="text-right">{s.count}</td>'
            f'<td class="text-right">{s.mean:.4g}</td>'
            f'<td class="text-right">{sd}</td>'
            f'<td class="text-right">{s.min:.4g}</td>'
            f'<td class="text-right">{s.max:.4g}</td>'
            f'<td class="text-right">{pk}</td></tr>',
        )
    sections.extend(["    </tbody>", "  </table>"])
    return sections


def _render_html_body_regression(report: LabReport) -> list[str]:
    sections = ["  <h2>4. Regression & Curve Fitting</h2>"]
    if report.regression:
        reg = report.regression
        r2 = f"{reg.r_squared:.4f}" if reg.r_squared is not None else "N/A"
        sections.extend([
            '  <div class="card">',
            f"    <p><strong>Model:</strong> {html.escape(reg.model_name)}</p>",
            f'    <div class="equation-card">{html.escape(reg.equation)}</div>',
            (
                f"    <p><strong>Slope:</strong> <code>{reg.slope:.5e}</code> | "
                f"<strong>Intercept:</strong> <code>{reg.intercept:.5e}</code></p>"
            ),
            f'    <p><strong>R²:</strong> <span class="badge">{r2}</span></p>',
            "  </div>",
        ])

    svg = _render_svg_plot(report)
    if svg:
        sections.extend(["  <h3>Vector Visualization</h3>", svg])
    if report.ascii_plot:
        sections.extend([
            "  <h3>ASCII Plot</h3>",
            f'  <pre class="ascii-plot">{html.escape(report.ascii_plot)}</pre>',
        ])
    return sections


def _render_html_body_errors(report: LabReport) -> list[str]:
    sections = [
        "  <h2>5. Error Analysis</h2>",
        "  <table>",
        (
            "    <thead><tr><th>Parameter</th><th>Symbol</th><th>Accepted</th>"
            "<th>Experimental</th><th>Unit</th><th>Absolute Error</th>"
            "<th>Relative Error</th></tr></thead>"
        ),
        "    <tbody>",
    ]
    sections.extend(
        f"      <tr><td><strong>{html.escape(r.parameter_name)}</strong></td>"
        f'<td class="text-center"><code>{html.escape(r.symbol)}</code></td>'
        f'<td class="text-right"><code>{r.accepted_value:.4e}</code></td>'
        f'<td class="text-right"><code>{r.experimental_value:.4e}</code></td>'
        f"<td>{html.escape(r.unit or '-')}</td>"
        f'<td class="text-right"><code>{r.absolute_error:.3e}</code></td>'
        f'<td class="text-right"><span class="badge">'
        f"{r.relative_error_percent:.2f}%</span></td></tr>"
        for r in report.error_analysis
    )
    sections.extend(["    </tbody>", "  </table>"])
    return sections


def render_html(report: LabReport) -> str:
    """Render a structured LabReport into a publication-ready HTML5 document."""
    meta = report.metadata
    title_esc = html.escape(meta.title)

    sections = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '  <meta charset="utf-8">',
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0">',
        f"  <title>Laboratory Report: {title_esc}</title>",
        f"  <style>{_render_html_css()}</style>",
        "</head>",
        "<body>",
    ]
    sections.extend(_render_html_body_header(report))
    sections.extend(_render_html_body_data(report))
    sections.extend(_render_html_body_regression(report))
    sections.extend(_render_html_body_errors(report))

    if report.discussion_questions:
        sections.append("  <h2>6. Discussion Questions</h2>")
        sections.append("  <ol>")
        sections.extend(
            f"    <li>{html.escape(q)}</li>"
            for q in report.discussion_questions
        )
        sections.append("  </ol>")

    sections.extend([
        "  <h2>7. Conclusion</h2>",
        f"  <p>{html.escape(report.conclusion or 'Analysis complete.')}</p>",
        "</body>",
        "</html>",
    ])
    return "\n".join(sections)


def render_report(
    report: LabReport,
    *,
    report_format: Literal["markdown", "html", "both"] = "markdown",
) -> dict[str, str]:
    """Render report into markdown, html, or both formats."""
    result: dict[str, str] = {}
    if report_format in ("markdown", "both"):
        result["markdown"] = render_markdown(report)
    if report_format in ("html", "both"):
        result["html"] = render_html(report)
    return result
