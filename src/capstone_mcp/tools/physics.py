# Copyright 2026 Capstone MCP contributors.
"""Tool router for physical calculations, numerical fitting, and lab reports."""

from collections.abc import Awaitable, Callable
from functools import partial
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
from capstone_mcp.reports.output import write_report_file as _write_report_file

type NativeCaller = Callable[..., Awaitable[Any]]


def register_physics_tools(mcp: FastMCP, native: NativeCaller) -> dict[str, Any]:
    """Register all math analysis, plotting, and recipe macro tools."""

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Read Capstone workflow guidance", readOnlyHint=True,
            destructiveHint=False, idempotentHint=True, openWorldHint=False,
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
    async def capstone_plot(samples: PlotInput) -> Image:
        """Render a scatter/line plot of labeled numerical samples as a PNG image.

        Generates an inline plot directly from numeric data points, without
        modifying the Capstone document workspace.
        """
        return Image(data=await anyio.to_thread.run_sync(render_plot, samples), format="png")

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Run OLS linear regression",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def capstone_linear_fit(samples: FitInput) -> LinearFit:
        """Run standard OLS linear regression (y = slope*x + intercept) on points."""
        return await anyio.to_thread.run_sync(linear_fit, samples)

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Compare experiment runs",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def capstone_compare_runs(
        runs: list[RunSamples],
    ) -> list[RunComparison]:
        """Group and compare sample metrics across multiple named experimental runs."""
        return await anyio.to_thread.run_sync(compare_runs, runs)

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
    async def capstone_generate_lab_report(  # noqa: PLR0913
        file_path_or_run: str,
        experiment_id: str = "generic",
        *,
        output_path: str | None = None,
        run_id: str | None = None,
        axes: tuple[str, str] | None = None,
        format: Literal["markdown", "html", "both"] = "markdown",  # noqa: A002
    ) -> GenerateLabReportResult:
        """Generate a formal physics laboratory report from experiment data.

        Ingests data from a .cap archive, CSV file, or JSON payload,
        computes summary statistics, regression parameters (slope, intercept, R^2),
        performs error analysis against accepted theoretical physical constants
        (e.g. Planck's constant h, resonant frequency f_0, adiabatic index gamma),
        generates ASCII plots, and renders publication-ready Markdown and HTML.

        Args:
            file_path_or_run: .cap archive, CSV/JSON file, inline JSON, or 'sample'.
            experiment_id: Canonical experiment identifier ('photoelectric_effect',
                'rlc_resonance', 'forced_harmonic_oscillation', 'adiabatic_gas',
                'slit_diffraction', or 'generic').
            output_path: Optional new path to save the report without overwriting files.
            run_id: Saved run name or number for a .cap file with multiple runs.
            axes: Explicit (x, y) series for linear regression from a saved .cap file.
            format: Output format ('markdown', 'html', or 'both').

        Returns:
            Report, rendered text, and status. Large sample arrays are returned as
            aligned prefixes with original_point_counts. Fits use all input samples.
        """
        report = await anyio.to_thread.run_sync(
            partial(
                generate_report, file_path_or_run, experiment_id,
                run_id=run_id, axes=axes,
            ),
        )
        rendered = await anyio.to_thread.run_sync(
            partial(render_report, report, report_format=format),
        )
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
            lab_report=report.transport_preview(),
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
        """Analyze supplied measurements for a supported physics experiment.

        Use action='analyze' with measured arrays in parameters. The supported
        experiment IDs are photoelectric_effect, rlc_resonance,
        forced_harmonic_oscillation (alias forced_oscillation), adiabatic_gas
        and slit_diffraction. For example, photoelectric_effect accepts
        wavelengths_nm and stopping_voltages_v.

        'acquire' accepts previously recorded inputs. Automatic apparatus setup
        and live acquisition are unavailable. 'run' stops at the first failed
        phase. Inspect success, phase_results and error before reporting results.
        """
        params = dict(parameters or {})
        return await anyio.to_thread.run_sync(
            partial(
                run_experiment_macro,
                experiment_id=experiment_id,
                action=action,
                parameters=params,
            ),
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

