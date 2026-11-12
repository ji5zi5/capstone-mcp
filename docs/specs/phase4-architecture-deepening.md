# Specification: Codebase Architecture Deepening & Modularity (Phase 4)

## Problem Statement

As `capstone-mcp` evolved to support comprehensive physics automation (404 tests, 26+ MCP tools, macro recipes, lab report generators, and pedagogical tutors), architectural friction has accumulated across three critical layers:
1. **Mathematical & Plotting Duplication**: Linear regression (OLS), $R^2$, descriptive statistics (mean, std, min, max), and ASCII/SVG rendering are duplicated across `src/capstone_mcp/analysis.py`, `src/capstone_mcp/experiment_analysis.py`, `src/capstone_mcp/plotting.py`, and `src/capstone_mcp/reports/generator.py`. Improvements to numerical stability or error propagation in one file do not benefit the others.
2. **Scattered Data Ingestion Seams**: Multiple modules (`reports/generator.py`, `recipes/base.py`, and CLI tools) branch independently based on file extension (`.cap`, `.csv`, JSON, or live desktop tables) to obtain raw `(x, y)` numerical arrays, resulting in repeated parsing and validation code across callers.
3. **Monolithic Server & Shallow Pass-Through Dispatch**: `src/capstone_mcp/server.py` has grown into a 1,948-line monolith coupling FastMCP transport, tool registration, docstrings, and error handling. Concurrently, `src/capstone_mcp/native_dispatch.py` (579 lines) serves as a shallow pass-through adapter that merely re-exposes methods of 10 underlying automation modules without adding meaningful depth.

## Solution

Deepen the architecture by applying the deep module design principles (small interface, deep implementation, clean seams, high locality, and caller leverage):
1. **Deep Numerics Engine (`capstone_mcp.numerics`)**: Consolidate all OLS regression, polynomial fitting, statistical summary calculations, error residual analysis, and ASCII/SVG chart generation into a single unified numerical core with a compact interface.
2. **Unified Experiment Data Source Seam (`capstone_mcp.data_sources`)**: Introduce a single `ExperimentDataSource` seam with a clean `get_series(source, x_name, y_name)` interface, hiding binary `.cap` parsing, `.csv` reading, and live table exports behind interchangeable adapters.
3. **Domain Tool Routers & Elimination of Pass-Through Dispatch**: Decompose `server.py` into focused domain tool bundles (`tools/files.py`, `tools/displays.py`, `tools/instruments.py`, `tools/physics.py`), and retire the redundant `NativeDispatch` pass-through layer, slimming `server.py` to under 200 lines.

## User Stories

1. As a physics automation developer, I want all linear regression, residual analysis, and $R^2$ calculations in `reports` and `analysis` to share a single verified numerical engine, so that mathematical results and precision tolerances are identical across all tools.
2. As a physics researcher, I want regression fits to provide standardized standard errors and confidence intervals, so that my automated lab reports have rigorous uncertainty metrics.
3. As a lab instructor, I want ASCII sparkline and SVG chart generation consolidated in one module, so that both terminal reports and web lessons render graphs with uniform visual styling.
4. As a report generator maintainer, I want to query numerical series via `get_series(source, x_col, y_col)` without checking whether the input is a `.cap` file, `.csv` file, or live session, so that data ingestion logic is decoupled from report formatting.
5. As an MCP client or AI agent navigating the codebase, I want tool definitions grouped by domain into clean submodules under 300 lines each, so that I can inspect and edit specific tools without loading a 2,000-line monolith.
6. As a test author, I want to unit-test display or instrument tool handlers in isolation without instantiating the entire FastMCP server application, so that testing is fast and deterministic.
7. As a software architect, I want pass-through boilerplate in `NativeDispatch` eliminated, so that call stacks are direct and code maintainability is maximized.
8. As a CI engineer, I want the expand-contract refactoring to maintain 100% green test passes at every step, so that existing contracts are never broken.

## Implementation Decisions

### 1. Deep Numerics Engine (`src/capstone_mcp/numerics/`)
- Create `capstone_mcp.numerics` as a leaf domain module with zero external GUI or network dependencies.
- Consolidate:
  - `compute_series_summary(values: Sequence[float]) -> SeriesSummary`
  - `fit_linear_series(x: Sequence[float], y: Sequence[float]) -> LinearRegressionResult`
  - `fit_polynomial_series(x: Sequence[float], y: Sequence[float], degree: int) -> PolynomialRegressionResult`
  - `render_ascii_sparkline(x: Sequence[float], y: Sequence[float], width: int, height: int, title: str) -> str`
  - `render_svg_sparkline(x: Sequence[float], y: Sequence[float], fit_x: Sequence[float] | None, fit_y: Sequence[float] | None) -> str`
- Deprecate duplicate OLS math in `reports/generator.py` and `experiment_analysis.py`, redirecting callers to the unified engine.

### 2. Unified Data Source Seam (`src/capstone_mcp/data_sources/`)
- Create `capstone_mcp.data_sources` defining:
  - `DataSeries(name: str, units: str, values: list[float | None])`
  - `ExperimentSeries(x: DataSeries, y: DataSeries, run_id: str | None, metadata: dict[str, str])`
  - Interface: `get_series(source: str | Path, x_name: str, y_name: str, run_id: str | None = None) -> ExperimentSeries`
- Concrete adapters behind the seam:
  - `CapFileSource`: Wraps `capfiles.py` archive extraction.
  - `CsvFileSource`: Wraps `csv_data.py` table extraction.
  - `LiveDesktopSource`: Wraps active session table reads.
- Callers in `reports/generator.py` and `recipes/base.py` use this single seam.

### 3. Server Modularization & Retiring NativeDispatch (`src/capstone_mcp/tools/`)
- Establish `src/capstone_mcp/tools/`:
  - `files.py`: File inspection, dataset queries, CSV export, and snapshot tools.
  - `displays.py`: Tables, digits monitors, graph statistics, area integrals, and delta measures.
  - `instruments.py`: Signal generators, oscilloscopes, FFTs, smart triggers, Keep Sample, and wireless calibration.
  - `physics.py`: Experiment automation macros, lab report generation, and pedagogical tutor tools.
- Each router registers tools onto the FastMCP server via a clean registration function `register_*(mcp: FastMCP) -> None`.
- `server.py` retains FastMCP lifecycle management, initialization instructions, resources, and prompts, reduced from 1,948 lines to ~180 lines.
- `native_dispatch.py` is removed; tool handlers invoke domain controllers directly.

## Testing Decisions

- **Preserve Existing 404 Tests**: The entire existing test suite must remain 100% green without modifying test assertions.
- **Seam-Level Unit Tests**:
  - `tests/test_numerics.py`: Dedicated unit tests for linear/polynomial regression, residual diagnostics, zero-division, and sparklines.
  - `tests/test_data_sources.py`: Tests verifying uniform extraction across `.cap`, `.csv`, and live table mocks.
  - `tests/test_tool_routers.py`: Tests ensuring each domain router registers expected tools and validates inputs.
- **Prior Art**: Follow the patterns in `tests/test_analysis.py` and `tests/test_golden_master.py`.

## Out of Scope

- Modifying the external MCP tool names or JSON schemas (all 26+ tool interfaces remain 100% backward compatible for clients).
- Adding new hardware protocols or third-party cloud integrations in this refactoring phase.

## Further Notes

- Refactoring follows the expand-contract pattern: new deep modules are introduced and tested alongside existing ones before callers are migrated, ensuring CI remains continuously green.
