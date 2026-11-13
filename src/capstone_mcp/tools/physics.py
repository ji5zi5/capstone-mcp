# Copyright 2026 Capstone MCP contributors.
"""Tool router for physical calculations, numerical fitting, and lab reports."""

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal

import anyio
from mcp.server.fastmcp import FastMCP, Image
from mcp.types import ToolAnnotations
from pydantic import JsonValue

from capstone_mcp.agent_instructions import GuideTopic, guide
from capstone_mcp.analysis import (
    FitInput,
    LinearFit,
    RunComparison,
    RunSamples,
    compare_runs,
    linear_fit,
)
from capstone_mcp.automation_models import NativeRequest
from capstone_mcp.calculator import CreateCalculationResult
from capstone_mcp.plotting import PlotInput, render_plot
from capstone_mcp.recipes import (
    ExperimentMacroResult,
    run_experiment_macro,
)
from capstone_mcp.reports import (
    GenerateLabReportResult,
    generate_report,
    render_report,
)

type NativeCaller = Callable[..., Awaitable[Any]]


def _write_report_file(
    out_path: str,
    format_type: str,
    md_text: str | None,
    html_text: str | None,
) -> None:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if format_type == "html":
        p.write_text(html_text or "", encoding="utf-8")
    elif format_type == "both":
        if md_text:
            p.write_text(md_text, encoding="utf-8")
        if html_text:
            p.with_suffix(".html").write_text(html_text, encoding="utf-8")
    else:
        p.write_text(md_text or "", encoding="utf-8")


def register_physics_tools(mcp: FastMCP, native: NativeCaller) -> dict[str, Any]:
    """Register all math analysis, plotting, and recipe macro tools."""

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Read Capstone workflow rules",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    def capstone_guide(topic: GuideTopic | None = None) -> str:
        """Return targeted instructions for common Capstone workflow scenarios.

        Clients may truncate the server instructions, which therefore carry only
        the essentials. Topics: workflow, files, graphs, graph_contract, windows,
        sensors, save_export, recording, recovery. Omit topic for all of them.
        """
        return guide(topic)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Plot numerical samples",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    def capstone_plot(samples: PlotInput) -> Image:
        """Render a scatter/line plot of labeled numerical samples as a PNG image.

        Generates an inline plot directly from numeric data points, without
        modifying the Capstone document workspace.
        """
        return Image(data=render_plot(samples), format="png")

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Run OLS linear regression",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    def capstone_linear_fit(samples: FitInput) -> LinearFit:
        """Run standard OLS linear regression (y = slope*x + intercept) on points."""
        return linear_fit(samples)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Compare experiment runs",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    def capstone_compare_runs(
        runs: list[RunSamples],
    ) -> list[RunComparison]:
        """Group and compare sample metrics across multiple named experimental runs."""
        return compare_runs(runs)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Create calculator expression",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def capstone_create_calculation(
        expression: str,
        handle: int = 0,
        *,
        unit: str | None = None,
        allow_foreground: bool = True,
        keep_open: bool = False,
    ) -> CreateCalculationResult:
        """Register a formula and optional unit in Capstone Calculator with auto-cleanup.

        Args:
            expression: Mathematical formula (e.g. 'KE = 0.5 * [Mass] * [Velocity]^2').
            handle: Capstone main window handle (0 for active window).
            unit: Optional physical unit string for the computed variable (e.g. 'J').
            allow_foreground: Bring window to foreground for UI automation.
            keep_open: Leave calculator side drawer open after registration.

        Returns:
            CreateCalculationResult with created variable name, formula, and status.
        """
        return CreateCalculationResult.model_validate(
            await native(
                NativeRequest(
                    operation="create_calculation",
                    handle=handle,
                    expression=expression,
                    unit=unit,
                    allow_foreground=allow_foreground,
                    keep_open=keep_open,
                ),
                mutates=True,
            ),
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Generate physics lab report",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def capstone_generate_lab_report(
        file_path_or_run: str,
        experiment_id: str = "generic",
        *,
        output_path: str | None = None,
        format: Literal["markdown", "html", "both"] = "markdown",  # noqa: A002
    ) -> GenerateLabReportResult:
        """Generate a formal physics laboratory report from experiment data.

        Ingests data from a .cap archive, CSV file, JSON payload, or active run,
        computes summary statistics, regression parameters (slope, intercept, R^2),
        performs error analysis against accepted theoretical physical constants
        (e.g. Planck's constant h, resonant frequency f_0, adiabatic index gamma),
        generates ASCII plots, and renders publication-ready Markdown and HTML.

        Args:
            file_path_or_run: Path to a .cap archive, CSV/JSON file, or active run name.
            experiment_id: Canonical experiment identifier ('photoelectric_effect',
                'rlc_resonance', 'forced_harmonic_oscillation', 'adiabatic_gas',
                'slit_diffraction', or 'generic').
            output_path: Optional path to save the generated report file.
            format: Output format ('markdown', 'html', or 'both').

        Returns:
            GenerateLabReportResult containing report model, rendered text, and status.
        """
        report = generate_report(
            file_path_or_run=file_path_or_run,
            experiment_id=experiment_id,
        )
        rendered = render_report(report, report_format=format)
        md_text = rendered.get("markdown")
        html_text = rendered.get("html")

        if output_path:
            await anyio.to_thread.run_sync(
                _write_report_file,
                output_path,
                format,
                md_text,
                html_text,
            )

        summary_text = (
            f"Generated {format} report for '{report.metadata.title}' with "
            f"{len(report.data_summaries)} data summaries and "
            f"{len(report.error_analysis)} error analyses."
        )

        return GenerateLabReportResult(
            experiment_id=experiment_id,
            title=report.metadata.title,
            format=format,
            output_path=output_path,
            report_markdown=md_text,
            report_html=html_text,
            summary=summary_text,
            lab_report=report,
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Run experiment macro",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def capstone_run_experiment_macro(
        experiment_id: str,
        action: str = "run",
        parameters: dict[str, JsonValue] | None = None,
    ) -> ExperimentMacroResult:
        """Execute high-level automation macro for canonical physics experiments.

        Supported experiments:
        - 'photoelectric_effect': Mercury lamp wavelength sweep (365, 405, 436, 546,
          577 nm), DC amplifier Ch A / DC power supply Ch B, Keep Sample stopping
          potential acquisition, and h/e linear fit.
        - 'rlc_resonance': 850 Signal generator sine sweep (10Hz-10kHz), Scope/FFT
          peak measurement, resonant frequency f_0, and Q-factor calculation.
        - 'forced_harmonic_oscillation' / 'forced_oscillation': Smart Cart 100Hz
          position, 480s stop condition, resonance amplitude curve, and damping b.
        - 'adiabatic_gas': 1000Hz sampling, cyclic work area integration (oint P dV),
          and adiabatic index gamma fit (PV^gamma = const).
        - 'slit_diffraction': Light intensity vs position scan, diffraction
          minima/maxima extraction, and slit geometry (width a, separation d).

        Actions:
        - 'setup': Configure apparatus sensors, displays, and excitation sources.
        - 'acquire': Record or sample experimental datasets.
        - 'analyze': Perform numerical regression, peak detection, and error metrics.
        - 'run': Sequentially execute setup, acquire, and analyze phases.
        """
        params = dict(parameters or {})
        return run_experiment_macro(
            experiment_id=experiment_id,
            action=action,
            parameters=params,
        )

    return {
        "capstone_guide": capstone_guide,
        "capstone_plot": capstone_plot,
        "capstone_linear_fit": capstone_linear_fit,
        "capstone_compare_runs": capstone_compare_runs,
        "capstone_create_calculation": capstone_create_calculation,
        "capstone_generate_lab_report": capstone_generate_lab_report,
        "capstone_run_experiment_macro": capstone_run_experiment_macro,
    }

