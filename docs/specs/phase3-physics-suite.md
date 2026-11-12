# Specification: Capstone Physics Suite (Phase 3: Automation Recipes, Lab Reports, Golden Tests, and Pedagogical Tutor)

## Problem Statement

While `capstone-mcp` provides 22 granular MCP tools for low-level Capstone GUI manipulation (pages, tables, digits, graphs, signal generators, scope/FFT, recording conditions, bluetooth calibration), orchestrating complete university-level physics experiments currently requires multi-step manual coordination by the AI agent or human user. Furthermore:
1. Conducting complex experiments (such as Photoelectric Effect stopping potential sweeps, RLC resonance sweeps, forced harmonic oscillation resonance curves, or adiabatic gas cycle integrations) requires executing dozens of interdependent configuration and acquisition steps.
2. Generating formal post-experiment physics laboratory reports requires tedious manual calculation of regression slopes, theoretical comparisons, error percentages, and formatting.
3. Regression testing against real-world multi-run PASCO `.cap` files with sparse table cells and complex binary records lacks a deterministic golden master test suite.
4. Students and lab researchers lack an interactive pedagogical assistant (`/teach`) grounded in primary-source Korean physics lab manuals (`.hwp`, `.docx`, `.pdf`) that can guide them step-by-step through apparatus setup, data acquisition, and conceptual troubleshooting.

## Solution

Build the **Capstone Physics Suite (Phase 3)** encompassing four integrated pillars:
1. **Experiment Automation Macro Engine (`capstone_mcp.recipes`)**: Pre-packaged, high-level automation workflows for canonical physics experiments (`photoelectric_effect`, `rlc_resonance`, `forced_harmonic_oscillation`, `adiabatic_gas`, `slit_diffraction`) exposed via `capstone_run_experiment_macro`.
2. **Automated Lab Report Engine (`capstone_mcp.reports`)**: Ingests `.cap` datasets or active experiment runs, calculates physical constants ($h, \phi, f_0, Q, b, \gamma$), evaluates percentage errors against theory, and formats publication-ready Markdown and HTML/PDF laboratory reports.
3. **Golden Master Test Suite (`tests/test_golden_master.py`)**: A comprehensive test suite using curated, real-world Capstone experiment files to verify data decoding, sparse record parsing, numerical extraction, and curve fitting integrity.
4. **Interactive Pedagogical Tutor (`/teach` & `capstone_mcp.tutor`)**: Grounded in Korean physics lab manuals (`.hwp`, `.docx`, `.pdf`) parsed via `rhwp` MCP server and document extractors, establishing a stateful learning workspace (`MISSION.md`, `RESOURCES.md`, `./lessons/*.html`, `./reference/*.html`) and MCP tools (`capstone_tutor_get_lesson`, `capstone_tutor_guide_step`).

## User Stories

1. As a physics student, I want to run a photoelectric effect macro with a single MCP call, so that Capstone automatically configures the amplifier channels, sets up the stopping voltage table, and guides the mercury lamp wavelength sampling.
2. As a physics student, I want the system to calculate Planck's constant ($h$) and the work function ($\phi$) from stopping voltage vs frequency data, so that I can immediately compare my experimental results to accepted physical values.
3. As a lab instructor, I want an automated RLC resonance recipe that commands the 850 signal generator through a frequency sweep and records peak voltages, so that students can observe resonance curves without manual knob adjustments.
4. As a researcher, I want to calculate the quality factor ($Q$) and resonant frequency ($f_0$) automatically from RLC circuit voltage response data, so that I can evaluate circuit damping accurately.
5. As an educator, I want a forced harmonic oscillation macro that pairs Smart Cart sensors with a 480-second automatic stop condition, so that resonance and magnetic eddy-current damping can be measured deterministically.
6. As a student, I want an adiabatic gas macro that integrates the $P$-$V$ curve to calculate the thermodynamic work $\oint P dV$ of a heat engine cycle, so that I can evaluate heat engine efficiency.
7. As a student, I want to generate a formal Markdown laboratory report directly from a `.cap` file, so that I have formatted data tables, regression statistics, error analysis, and discussion sections ready for submission.
8. As a lab TA, I want the report generator to include ASCII and SVG plots of fitted curves, so that the report can be read and reviewed in any standard terminal, browser, or markdown viewer.
9. As a software developer maintaining `capstone-mcp`, I want a golden master test suite evaluating all 12 canonical physics experiments, so that future parser changes never break decoding of real-world `.cap` archives.
10. As a software developer, I want regression tests ensuring sparse Capstone tables with record type 0 empty cells never throw unhandled exceptions, so that real user datasets always parse smoothly.
11. As a student starting an unfamiliar experiment, I want to use `/teach` to open an interactive HTML lesson grounded in the actual Korean lab manual for my apparatus, so that I can understand the governing theory before touching the equipment.
12. As a student, I want printable Tufte-style reference sheets in `./reference/*.html`, so that I have quick-reference wiring diagrams, sensor channels, and formulas beside my experimental bench.
13. As an AI agent assisting a student in real-time, I want to call `capstone_tutor_guide_step` to retrieve the current step's instructions, safety precautions, and validation checks from the primary-source manual, so that I can guide the user without hallucinating equipment details.
14. As an AI agent, I want access to `capstone://resources/manuals` FastMCP resource, so that I can query Korean lab manuals on demand.

## Implementation Decisions

### 1. Macro Recipe Engine (`capstone_mcp.recipes`)
- A modular recipe architecture with a base `ExperimentRecipe` interface and concrete implementations:
  - `PhotoelectricEffectRecipe`: Mercury lamp wavelengths (365, 405, 436, 546, 577 nm), DC amplifier Ch A / DC power supply Ch B, Keep Sample stopping potential acquisition, $V = \frac{h}{e}f - \frac{\phi}{e}$ regression.
  - `RLCResonanceRecipe`: 850 Signal generator sine wave sweep (10 Hz - 10 kHz), analog voltage Ch A (resistor), Ch B (inductor), Ch C (capacitor), peak voltage extraction, $f_0 = \frac{1}{2\pi\sqrt{LC}}$ and $Q$-factor calculation.
  - `ForcedOscillationRecipe`: Smart Cart position/force sensors, 100 Hz sampling, 480 s stop condition, photogate pendulum timer, resonance amplitude vs driver frequency response.
  - `AdiabaticGasRecipe`: 1000 Hz high-speed pressure & volume acquisition, $PV^\gamma = \text{const}$ curve fit, cyclic work integration $\oint P dV$.
  - `SlitDiffractionRecipe`: Linear translator position vs light intensity, diffraction minima/maxima peak detection, slit geometry derivation.
- Expose MCP tool: `capstone_run_experiment_macro(experiment_id: str, action: str, parameters: dict | None)`.

### 2. Automated Lab Report Engine (`capstone_mcp.reports`)
- Ingests data from either parsed `.cap` files or live active runs via `NativeDispatch`.
- Compares experimental datasets with theoretical physical constants ($h = 6.626 \times 10^{-34} \text{ J}\cdot\text{s}$, $c = 2.998 \times 10^8 \text{ m/s}$, $\gamma_{\text{air}} \approx 1.40$).
- Generates structured `LabReport` objects containing:
  - Metadata (experiment title, date, apparatus models).
  - Theoretical background and equations extracted from manuals.
  - Experimental configuration (channels, sensors, sampling rates).
  - Data tables with mean, standard deviation, and peak values.
  - Linear/polynomial/nonlinear regression parameters and $R^2$ correlation.
  - Error analysis table (theoretical value, experimental value, absolute error, relative error %).
  - Discussion prompts based on manual questions.
  - Visualization: ASCII terminal graphs and standalone HTML/SVG plots.
- Expose MCP tool: `capstone_generate_lab_report(file_path_or_run: str, experiment_id: str, output_path: str | None, format: str)`.

### 3. Golden Master Test Suite (`tests/fixtures/` & `tests/test_golden_master.py`)
- Curate clean, minimal fixture files representing the 12 canonical physics experiments.
- Test matrix covering:
  - Optics: Single/double slit diffraction, polarization with wireless sensors.
  - Mechanics: Driven harmonic oscillation, gyroscope angular momentum, rotational inertia.
  - Thermodynamics: Heat engine cycle, adiabatic gas law.
  - Electromagnetism: RLC resonance frequency and phase relations, Ohm's law.
  - Modern Physics: Photoelectric effect stopping voltages, blackbody radiation.
- Tests verify deterministic extraction of datasets, units, timestamps, curve fit coefficients, and zero corruption on empty/sparse record types.

### 4. Interactive Pedagogical Tutor (`/teach` & `capstone_mcp.tutor`)
- Primary-Source Document Ingestion:
  - Connect with lazy `rhwp` MCP server (`hwp_export_text`) to extract text and tables from `.hwp` files in `C:\Users\Jio\Downloads\(2026)캡스톤 실험별 파일`.
  - Built-in `.docx` XML parser using Python's standard `zipfile` and `xml.etree`.
  - PDF text extractor using Python standard or available libraries.
- Matt Pocock Teaching Workspace (`./lessons/`, `./reference/`, `./assets/`):
  - `MISSION.md`: Grounds learning in mastery of physics lab automation and computational data analysis.
  - `RESOURCES.md`: Indexes all Korean lab manuals, equipment models, and data archives.
  - `./reference/*.html`: Tufte-style reference cheat-sheets for formulas, circuit diagrams, and Capstone wiring.
  - `./lessons/*.html`: Self-contained interactive lesson modules with quizzes, real-world steps, and retrieval practice.
  - `./assets/`: Reusable CSS typography and quiz widgets.
- Expose MCP tools:
  - `capstone_tutor_get_lesson(experiment_id: str)`: Returns full curriculum, equipment list, theory, and steps.
  - `capstone_tutor_guide_step(experiment_id: str, step_index: int)`: Returns specific step guidance, safety notes, and verification checks.
- Expose FastMCP Resource: `capstone://tutor/lessons`.

## Testing Decisions

- **External Behavior Focus**: All recipe and report tests must assert external API contracts and physical calculations without coupling to internal private state.
- **Headless & Offline CI Safety**: Recipes and tutor tools must execute with deterministic mocks when no live Capstone GUI instance is present, complying with `AGENTS.md` offline test guards.
- **Precision Tolerances**: Physical constant fits must verify mathematical convergence (e.g. Planck's constant regression slope within expected order of magnitude $10^{-34}$).
- **Prior Art**: Follow the patterns established in `tests/test_analysis.py`, `tests/test_capfiles.py`, and `tests/test_protocol.py`.

## Out of Scope

- Controlling physical hardware or proprietary USB interface firmware outside of PASCO Capstone software APIs.
- Replacing commercial grading software or automated exam generation systems.
- Supporting non-Capstone document formats (e.g. DataStudio `.ds` files) in this phase.

## Further Notes

- All Korean lab manual extracts are validated against primary-source documents in `C:\Users\Jio\Downloads\(2026)캡스톤 실험별 파일`.
- The tutor lessons and reference materials follow Edward Tufte's informational design principles for clarity, typography, and high data-ink ratios.
