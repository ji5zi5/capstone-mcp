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
        "Please set up and run an acoustic/electrical resonance experiment in "
        "PASCO Capstone:\n"
        f"1. Turn on the 850/550 Signal Generator (capstone_set_signal_generator) "
        f"with a Sine wave at {frequency_hz} Hz and {amplitude_v} V amplitude.\n"
        "2. Add an Oscilloscope display (capstone_create_scope) to monitor the input "
        "and sensor output waveforms, and configure rising edge trigger "
        "(capstone_set_scope_trigger).\n"
        "3. Create an FFT display (capstone_create_fft) and extract the top "
        "harmonic frequency peaks (capstone_read_fft_peaks) to identify resonance.\n"
        "4. Report the measured peak frequency and amplitude comparison back to me."
    )


def collision_impulse_experiment(
    threshold_force_n: float = 0.5,
) -> str:
    """Guided prompt template for automated collision impulse measurement."""
    return (
        "Please set up a dynamics cart collision experiment in PASCO Capstone:\n"
        "1. Set an automated recording start condition "
        "(capstone_set_recording_condition) triggered when Force exceeds "
        f"{threshold_force_n} N.\n"
        "2. Arrange the page into a two-pane layout (capstone_set_page_layout "
        "with 'two_vertical') containing a Graph and a Table.\n"
        "3. Once collision data is recorded, integrate the area under the "
        "Force-Time curve (capstone_measure_graph_area) to compute the total "
        "impulse (integral of F dt).\n"
        "4. Extract summary statistics (capstone_toggle_graph_statistics) and "
        "display the resulting impulse and momentum values."
    )


def titration_keep_sample_workflow(
    volume_step_ml: float = 1.0,
) -> str:
    """Guided prompt template for manual point sampling (e.g. pH titration)."""
    return (
        "Please configure a manual point-by-point sampling workflow in PASCO "
        "Capstone:\n"
        "1. Switch the sampling mode to manual keep-sample "
        "(capstone_set_sampling_mode with mode='keep_sample').\n"
        "2. Create a Table display (capstone_create_table) and set columns "
        f"(capstone_set_table_columns) with 'Volume' (step {volume_step_ml} mL) "
        "and 'pH'.\n"
        "3. Guide me through recording each droplet measurement point using "
        "capstone_keep_sample(value=..., variable_name='Volume')."
    )


def sensor_calibration_workflow(
    sensor_name: str = "Force Sensor",
) -> str:
    """Guided prompt template for a guided 2-point sensor calibration wizard."""
    return (
        f"Please calibrate the connected '{sensor_name}' in PASCO Capstone:\n"
        "1. Open the calibration wizard (capstone_calibrate_sensor) using "
        "2-point calibration.\n"
        "2. Guide me through measuring Standard 1 (zero load) and Standard 2 "
        "(known calibration weight or buffer).\n"
        "3. Confirm calibration completion and verify sensor reading matches "
        "the reference value."
    )


def data_analysis_workflow(
    experiment_name: str = "generic",
    fit_model: str = "Linear",
) -> str:
    """Guided prompt template for automated physics curve fitting and lab analysis."""
    return (
        f"Please execute a structured data analysis workflow for '{experiment_name}' "
        "in PASCO Capstone:\n"
        "1. Inspect active displays and windows using capstone_windows and "
        "capstone_snapshot.\n"
        "2. Observe and read the primary graph display using "
        "capstone_manage_graph(action='read').\n"
        f"3. Apply a '{fit_model}' curve fit to the active data series using "
        f"capstone_manage_graph(action='fit', fit_type='{fit_model}').\n"
        "4. Extract fit parameters (slope, intercept, r_squared, etc.) and calculate "
        "residuals or theoretical percentage error.\n"
        "5. Compile the final experimental findings into a structured lab report with "
        "capstone_generate_lab_report."
    )


def display_layout_workflow(
    page_title: str = "New Analysis",
    layout: str = "two_vertical",
    target_measurements: str = "Time, Position",
) -> str:
    """Guided prompt template for workbook page creation and multi-display layout."""
    return (
        f"Please execute a workbook display layout workflow for '{page_title}' "
        "in PASCO Capstone:\n"
        "1. Check existing workbook pages and display widgets via the "
        "capstone://displays/active resource.\n"
        f"2. Add a new workbook page tab titled '{page_title}' using "
        f"capstone_manage_display(action='add_page', title='{page_title}').\n"
        f"3. Apply the desired grid split layout template '{layout}' using "
        f"capstone_manage_display(action='set_page_layout', layout='{layout}').\n"
        "4. Insert appropriate display widgets into layout placeholders: "
        "use capstone_manage_display with 'create_digits', 'create_table', "
        "'create_scope', or 'create_fft' (or capstone_manage_graph for graphs).\n"
        f"5. Bind target measurements ({target_measurements}) to display axes, "
        "columns, or readout channels.\n"
        "6. Verify the active display layout visually or via capstone_snapshot."
    )


def run_comparison_workflow(
    run1: str = "Run #1",
    run2: str = "Run #2",
) -> str:
    """Guided prompt template for multi-run comparison and percentage analysis."""
    return (
        "Please execute a multi-run comparison workflow in PASCO Capstone:\n"
        f"1. Verify recorded experimental runs ({run1}, {run2}) via the "
        "capstone://runs/active resource.\n"
        f"2. Inspect the summary statistics for both {run1} and {run2} using "
        "capstone_manage_graph(action='toolbox_statistics').\n"
        f"3. Compare key metric parameters (mean, standard deviation, peak values) "
        f"between {run1} and {run2}.\n"
        "4. Calculate percentage difference and evaluate experimental reproducibility "
        "or trendlines.\n"
        "5. Present a comparative Markdown table summarizing the differences and "
        "scientific conclusions."
    )


def hardware_setup_workflow(
    interface_type: str = "850 Universal Interface",
    target_sensor: str = "Force Sensor",
    sampling_rate: str = "100 Hz",
) -> str:
    """Guided prompt template for hardware setup, sensor zeroing, and calibration."""
    return (
        f"Please execute a hardware setup workflow for '{target_sensor}' "
        f"on '{interface_type}' in PASCO Capstone:\n"
        "1. Check hardware status and connected interfaces via the "
        "capstone://hardware/inventory resource.\n"
        "2. If using wireless sensors, scan and connect using "
        "capstone_manage_instrument(action='scan_wireless') and "
        "capstone_manage_instrument(action='connect_wireless', sensor_name=...).\n"
        f"3. Select sensor and configure sampling rate to '{sampling_rate}' using "
        f"capstone_manage_instrument(action='set_sampling_rate', "
        f"sensor_name='{target_sensor}', sampling_rate='{sampling_rate}').\n"
        "4. Zero or tare the sensor prior to data acquisition using "
        f"capstone_manage_instrument(action='zero_sensor', "
        f"sensor_name='{target_sensor}').\n"
        "5. If a signal generator is required, configure waveform and frequency using "
        "capstone_manage_instrument(action='set_signal_generator', ...).\n"
        "6. Confirm live sensor values and readiness using "
        "capstone_manage_instrument(action='read_signal_generator') or "
        "capstone_snapshot."
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
