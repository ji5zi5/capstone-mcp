# Copyright 2026 Capstone MCP contributors.
"""Guided prompt templates for PASCO Capstone experiment workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def resonance_experiment_workflow(
    frequency_hz: float = 1000.0,
    amplitude_v: float = 2.0,
) -> str:
    """Guided prompt template for setting up an RLC/acoustic resonance experiment."""
    return (
        f"Inspect the selected 850/550 generator in capstone_manage_instrument using "
        f"configure_signal_generator with read_only=true. For the requested sine "
        f"wave at {frequency_hz} Hz and {amplitude_v} V, verify the target and "
        "authorized output first. Use capstone_manage_display actions create_scope, "
        "set_scope_trigger, create_fft and read_fft_peaks as needed. Report the "
        "observed spectrum and distinguish native settings from measured output."
    )


def collision_impulse_experiment(
    threshold_force_n: float = 0.5,
) -> str:
    """Guided prompt template for automated collision impulse measurement."""
    return (
        f"Analyze the cart collision when Force exceeds {threshold_force_n} N. "
        "Sensor-specific native trigger selection is unsupported. Use measured "
        "force/time samples to identify the crossing. Use capstone_manage_display "
        "action set_page_layout for a two_vertical layout and capstone_manage_graph "
        "actions toolbox_area and toolbox_statistics for the selected graph. Verify "
        "the integration limits and units before reporting impulse."
    )


def titration_keep_sample_workflow(
    volume_step_ml: float = 1.0,
) -> str:
    """Guided prompt template for manual point sampling (e.g. pH titration)."""
    return (
        "Configure manual sampling using capstone_manage_instrument action "
        "set_sampling_mode with mode='keep_sample'. Use capstone_manage_display "
        "actions create_table and set_table_columns for the observed Volume and pH "
        f"channels. After each measured {volume_step_ml} mL step, request keep_sample "
        "and check whether a new row actually appeared before advancing."
    )


def sensor_calibration_workflow(
    sensor_name: str = "Force Sensor",
) -> str:
    """Guided prompt template for a guided 2-point sensor calibration wizard."""
    return (
        f"Identify the connected '{sensor_name}' in PASCO Capstone and the two "
        "reference standards. Use capstone_manage_instrument action calibrate_sensor "
        "with the observed sensor_name, calibration_type='two_point', standard_1 and "
        "standard_2. Guide the operator through applying both standards. Compare the "
        "post-calibration reading with the reference before reporting accuracy."
    )


def data_analysis_workflow(
    experiment_name: str = "generic",
    fit_model: str = "Linear",
) -> str:
    """Guided prompt template for automated physics curve fitting and lab analysis."""
    return (
        f"Please execute a structured data analysis workflow for '{experiment_name}' "
        "in PASCO Capstone. Use capstone_windows and capstone_snapshot to locate "
        "the graph. Use capstone_manage_graph action read for the live data bindings, "
        "then observe for fresh pixels and a one-use frame_id. Apply the requested "
        f"'{fit_model}' using action analyze with the supported model enum in "
        "request.analyze.fitting.models, the observed anchors, frame_id and expected "
        "data signature. Report verified native fit status and available metrics. "
        "Use capstone_generate_lab_report with sourced measurements when requested."
    )


def display_layout_workflow(
    page_title: str = "New Analysis",
    layout: str = "two_vertical",
    target_measurements: str = "Time, Position",
) -> str:
    """Guided prompt template for workbook page creation and multi-display layout."""
    return (
        f"Review capstone://displays/active and create the page '{page_title}' "
        "with capstone_manage_display action add_page and request.add_page.title. "
        f"Select '{layout}' if present in the set_page_layout schema and provide it in "
        "request.set_page_layout.layout. Use create_digits, create_table, create_scope "
        f"or create_fft. Bind the observed {target_measurements} channels. "
        "Verify the result with capstone_snapshot."
    )


def run_comparison_workflow(
    run1: str = "Run #1",
    run2: str = "Run #2",
) -> str:
    """Guided prompt template for multi-run comparison and percentage analysis."""
    return (
        f"Locate the recorded runs '{run1}' and '{run2}' in the saved datasets or "
        "the visible Data Summary. capstone://runs/active reports server jobs. "
        "Verify the units and run visibility before using capstone_manage_graph "
        "action toolbox_statistics. Compare measured values with capstone_compare_runs "
        "and state the denominator for each percentage difference."
    )


def hardware_setup_workflow(
    interface_type: str = "850 Universal Interface",
    target_sensor: str = "Force Sensor",
    sampling_rate: str = "100 Hz",
) -> str:
    """Guided prompt template for hardware setup, sensor zeroing, and calibration."""
    return (
        f"Inspect '{interface_type}' via capstone://hardware/inventory and verify the "
        f"observed '{target_sensor}'. Use capstone_manage_instrument request actions. "
        "For wireless devices use scan_wireless and connect_wireless with the observed "
        f"sensor_id. For set_sampling_rate use sensor='{target_sensor}' and "
        f"target='{sampling_rate}'. If the operator requests a tare, use zero_sensor "
        f"with sensor_name='{target_sensor}' and check against a known reference. "
        "Read generator settings via configure_signal_generator with read_only=true. "
        "Use capstone://measurements/live to inspect available readings."
    )


def register_prompts(mcp: FastMCP[None]) -> None:
    """Register all guided experiment workflow prompts onto FastMCP."""
    mcp.prompt()(resonance_experiment_workflow)
    mcp.prompt()(collision_impulse_experiment)
    mcp.prompt()(titration_keep_sample_workflow)
    mcp.prompt()(sensor_calibration_workflow)
    mcp.prompt()(data_analysis_workflow)
    mcp.prompt()(display_layout_workflow)
    mcp.prompt()(run_comparison_workflow)
    mcp.prompt()(hardware_setup_workflow)


__all__ = [
    "collision_impulse_experiment",
    "data_analysis_workflow",
    "display_layout_workflow",
    "hardware_setup_workflow",
    "register_prompts",
    "resonance_experiment_workflow",
    "run_comparison_workflow",
    "sensor_calibration_workflow",
    "titration_keep_sample_workflow",
]
