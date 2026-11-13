# PASCO Capstone MCP Architecture Documentation

## 1. System Overview

`capstone-mcp` is a Model Context Protocol (MCP) server providing automated control, numerical analysis, experimental data extraction, and pedagogical tutoring for **PASCO Capstone**.

### Process Architecture & Concurrency Model

PASCO Capstone is a Windows desktop application automated through UI Automation (UIA) and Component Object Model (COM) interfaces. To ensure robust reliability and prevent COM apartment thread-affinity deadlocks from blocking the asynchronous MCP protocol transport:

```mermaid
flowchart LR
    Client["MCP Client / Agent"] <-->|"stdio / HTTP (JSON-RPC)"| Server["FastMCP Server (server.py)"]
    Server <-->|"IPC (JSON-Lines / pipes)"| Worker["AutomationWorker (STA Process)"]
    Worker <-->|"native_loop.py"| Desktop["Desktop Native Engine (pywinauto / UIA)"]
    Desktop <-->|"Windows API"| Capstone["PASCO Capstone App"]
```

1. **Async FastMCP Server (`server.py`)**: Runs on the primary asyncio event loop, handling JSON-RPC transport over stdio or Streamable HTTP.
2. **Process Boundary (`automation_worker.py`)**: Manages the child worker process lifecycle with Windows Job Objects for leak-free termination (`PROCESS_ATTACH_TO_JOB`).
3. **STA Worker Loop (`native_loop.py`)**: Dedicated Single-Threaded Apartment (STA) worker process executing COM/pywinauto calls deterministically, with frame receipts (`observe_graph`) guarding against race conditions.

---

## 2. Deep Numerics Engine (`capstone_mcp.numerics`)

Prior to Phase 4, ordinary least squares (OLS) linear regression, error residual calculations, descriptive statistics, and ASCII/SVG rendering were duplicated across `analysis.py`, `experiment_analysis.py`, `plotting.py`, and `reports/generator.py`. 

The Deep Numerics Engine consolidates these capabilities into a single leaf package with zero GUI or network dependencies.

```mermaid
classDiagram
    class NumericsEngine {
        +compute_series_summary(values) SeriesSummary
        +fit_linear_series(x, y) LinearRegressionResult
        +fit_polynomial_series(x, y, degree) PolynomialRegressionResult
        +render_ascii_sparkline(x, y, width, height, title) str
        +render_svg_sparkline(x, y, fit_x, fit_y) str
    }
    class SeriesSummary {
        +count: int
        +mean: float
        +std_dev: float
        +min: float
        +max: float
    }
    class LinearRegressionResult {
        +slope: float
        +intercept: float
        +r_squared: float
        +std_err_slope: float
        +std_err_intercept: float
        +predict(x): float
    }
    NumericsEngine --> SeriesSummary
    NumericsEngine --> LinearRegressionResult
```

### Key Modules:
- `summary.py`: Descriptive statistics computation (`mean`, sample standard deviation, minimum, maximum).
- `regression.py`: High-precision Ordinary Least Squares (OLS) linear and polynomial regression with standard error of estimate, slope uncertainty, and coefficient of determination ($R^2$).
- `sparklines.py`: Visual ascii sparkline diagrams for CLI logs and SVG vector plots with data points and trendlines for HTML lab reports.

---

## 3. Unified Experiment Data Source Seam (`capstone_mcp.data_sources`)

To eliminate ad-hoc format branching (`.cap` vs `.csv` vs live UI table) across reports and automation recipes, `capstone_mcp.data_sources` provides a single abstraction seam.

```mermaid
flowchart TD
    Caller["Report Generator / Macro Recipes"] -->|"get_experiment_series(source, x, y)"| Seam["Data Source Seam (seam.py)"]
    Seam --> Cap["CapArchiveAdapter (.cap files)"]
    Seam --> Csv["CsvTableAdapter (.csv files)"]
    Seam --> Live["LiveSessionAdapter (active table display)"]
    Cap --> ExpSeries["ExperimentSeries (paired x/y DataSeries)"]
    Csv --> ExpSeries
    Live --> ExpSeries
```

### Models & Protocols:
- **`DataSeries`**: Immutable container for named, unit-annotated numerical series with `clean_floats()` filtering of missing or sparse values.
- **`ExperimentSeries`**: Paired independent ($x$) and dependent ($y$) variables, run metadata, and provenance tags.
- **`DataSourceAdapter` Protocol**: Common interface implemented by `CapArchiveAdapter`, `CsvTableAdapter`, and `LiveSessionAdapter`.

---

## 4. Domain Tool Routers & Server Decomposition

`src/capstone_mcp/server.py` was decomposed from a 1,948-line monolith into focused domain routers in `src/capstone_mcp/tools/`, reducing `server.py` by over 72% while preserving 100% backward compatibility across all 75 registered MCP tools:

| Domain Router | File | Responsibilities & Tools |
| :--- | :--- | :--- |
| **Files** | `src/capstone_mcp/tools/files.py` | Experiment save/open, CSV data export, dataset inspection, and file regression. |
| **Displays** | `src/capstone_mcp/tools/displays.py` | Graph creation, axis measurement assignment, graph screenshots, table displays, digits displays, workbook layout, and run management. |
| **Instruments** | `src/capstone_mcp/tools/instruments.py` | Hardware sensor configuration, discrete rate adjustments, repeat acquisition jobs, zero/tare, signal generator, oscilloscope, FFT, smart triggers, and wireless calibration. |
| **Physics** | `src/capstone_mcp/tools/physics.py` | Mathematical calculations, plotting, experiment macros (`recipes`), formal lab report generation, and interactive pedagogical tutors. |

### Retirement of `NativeDispatch` (Passing the Deletion Test)

The redundant 579-line pass-through layer `src/capstone_mcp/native_dispatch.py` was deleted. The STA worker command execution was consolidated directly into `src/capstone_mcp/native_loop.py`, removing an unnecessary intermediate abstraction layer and shortening call stacks.

---

## 5. Core Domain & Automation Deepening (Phase 5)

Phase 5 collapsed fragmented shallow utilities across run management, binary archive decoding, and display palette interactions into deep, cohesive modules with minimal external surface areas and high internal depth:

```mermaid
flowchart TD
    subgraph UIAutomation ["UI Automation & Displays"]
        Harness["DisplayHarness (displays/harness.py)"]
        Digits["Digits Display (digits_display.py)"]
        Table["Table Display (table_display.py)"]
        Scope["Oscilloscope & FFT (oscilloscope_fft.py)"]
        Workbook["Workbook Layout (workbook_layout.py)"]
        Digits --> Harness
        Table --> Harness
        Scope --> Harness
        Workbook --> Harness
    end

    subgraph RunManagement ["Deep Run Management"]
        RunMgr["RunManager (runs/manager.py)"]
        RunModels["RunRequest / RunResult (runs/models.py)"]
        RunMgr --> RunModels
        RunMgr --> Harness
    end

    subgraph BinaryDecoder ["Binary CapFile Subsystem"]
        Archive["Archive Parser (capfiles/archive.py)"]
        Records["Binary Decoder (capfiles/records.py)"]
        Archive --> Records
    end
```

### Key Subsystems:
1. **Deep Run Management Module (`src/capstone_mcp/runs/`)**:
   - Collapsed 4 shallow modules (`run_rename.py`, `run_delete.py`, `run_visibility.py`, `run_capture.py`) into a unified `RunManager` engine.
   - Provides a single `manage_run(app, RunRequest)` seam supporting `RENAME`, `DELETE`, `SET_VISIBILITY`, and `CAPTURE`.
   - Incorporates inline F2 keyboard renaming fallbacks, automated modal confirmation dialog dismissal, multi-display visibility toggling, and multi-cycle dataset acquisition snapshots with trendline comparisons.

2. **Decoupled Binary Record Decoder (`src/capstone_mcp/capfiles/records.py`)**:
   - Decoupled low-level little-endian 12-byte attribute/double scalar unpacking and 8-byte header UTF-16 text decoding from ZIP archive and XML traversal.
   - Provides pure byte-buffer decoding seams (`decode_numeric_payload`, `decode_text_records`, `decode_interval_coordinates`), enabling microsecond in-memory unit testing (`tests/test_capfile_records.py`) without synthetic zip file generation.
   - Preserves 100% backward compatibility for archive traversal in `src/capstone_mcp/capfiles/archive.py`.

3. **Consolidated Display Automation Harness (`src/capstone_mcp/displays/`)**:
   - Consolidates palette drag-and-drop operations, double-click insertion, container resolution, and click/invoke fallbacks into `DisplayHarness`.
   - Eliminated 6 duplicated `_click()` fallback definitions and repetitive `_find_*` control loops across `digits_display.py`, `table_display.py`, `workbook_layout.py`, `oscilloscope_fft.py`, and `runs/manager.py`.

---

## 6. Quality & Verification Guardrails

1. **Automated Test Coverage**: 457 unit and integration tests across 54 test suites, executed with `uv run --no-sync pytest` (100% pass rate).
2. **Deterministic Offline CI**: Hardware-dependent and live GUI tests include fallback guards (`pytest.mark.skipif`), allowing CI pipelines to pass deterministically in headless environments.
3. **Windows Process Lock Guard**: Tool and test runner commands strictly enforce `--no-sync` to avoid `os error 32` file locking when background MCP processes hold `capstone-mcp.exe`.
4. **Strict Type Safety & Linting**: Ruff compliance across all rulesets (`ruff check src tests`) with 0 errors, and Basedpyright type validation (`basedpyright src`) with 0 errors, 0 warnings.
