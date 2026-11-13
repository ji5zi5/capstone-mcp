# Specification: Graph Subsystem Deepening & MCP Protocol Maturity (Phase 6)

## Problem Statement

From the perspective of AI agents and human researchers interacting with `capstone-mcp`, the system suffers from two interrelated architectural frictions:

1. **MCP Protocol Immaturity & Context Bloat**:
   - The MCP server exposes over 75 fine-grained tools directly to client context windows. When modern AI agents (Claude Desktop, Cursor, Antigravity) connect, injecting schemas for 75+ tools consumes excessive context tokens and elevates tool selection variance.
   - Safe inspection tools lack `readOnly` metadata, requiring tedious manual approval dialogs, while destructive operations lack `destructive` warnings.
   - Agents lack real-time dynamic MCP resources to inspect experiment state without running heavy RPC loops, and error reporting is inconsistent across tools.

2. **Internal Codebase Fragmentation in Graph Automation**:
   - The Graph domain is shattered across 7 shallow modules (>65KB) in the project root (`graph_control.py`, `graph_execution.py`, `graph_report.py`, `graph_requests.py`, `graph_state.py`, `graph_toolbox.py`, `graph_workflows.py`).
   - Callers in tool routers and the native loop must coordinate graph insertion, Qt toolbox clicking, curve fitting, and popup menu traversal across multiple disparate interfaces with leaky abstractions.

## Solution

A dual-pronged deepening and protocol maturity initiative:

1. **Deep Graph Domain Module (`src/capstone_mcp/graphs/`)**:
   - Consolidate the 7 shallow graph files into a cohesive, deep package anchored by a single unified seam (`manage_graph(app, GraphRequest) -> GraphResult`) and a `GraphManager` engine.
   - Encapsulate Qt smart toolbox manipulation, curve fitting, measurement popup navigation, and state inspection behind the seam.
   - Fully integrate with the centralized display harness primitives (`click_control`, `center_coords`).

2. **MCP Protocol Maturity Upgrade**:
   - Introduce `capstone_manage_graph` as a high-level compound MCP tool while preserving backward-compatible tool aliases.
   - Systematically annotate all MCP tools with `ToolAnnotations` (`readOnlyHint: true` for inspections, `destructiveHint: true` for destructive operations).
   - Expose dynamic real-time MCP resources: `capstone://status` and `capstone://runs/active`.
   - Standardize error envelopes across MCP tool boundaries with `isError=True` and structured remediation payloads.
   - Add universal MCP workflow prompts for automated data analysis and multi-run comparison.

## User Stories

1. As an AI agent connected via MCP, I want a single unified `capstone_manage_graph` compound tool, so that I can create, configure, fit, measure, and analyze graphs without juggling 7 disparate tool schemas in my context window.
2. As an AI agent, I want safe inspection tools (e.g. window listing, screenshotting, graph reading) to be explicitly annotated with `readOnlyHint: true`, so that the MCP client can auto-approve them without prompting the human user for every benign step.
3. As an experimenter, I want destructive actions (e.g. deleting runs, discarding unsaved experiments) to be annotated with `destructiveHint: true`, so that my client prompts me for explicit confirmation before irreversible state changes occur.
4. As an AI agent, I want to read the dynamic `capstone://status` resource, so that I can immediately observe the active Capstone connection PID, open window count, and active run state without executing multiple round-trip RPC calls.
5. As an AI agent, I want a dynamic `capstone://runs/active` resource, so that I can inspect the currently recorded runs and sensor series in a lightweight JSON format before deciding what analysis to run.
6. As an AI agent, I want every tool failure to return a structured error envelope with `isError=True` and a machine-readable `error_code`, so that I can reliably self-correct rather than attempting to parse unstructured Python tracebacks.
7. As a student or researcher, I want a `data_analysis_workflow` prompt template, so that I can trigger a complete end-to-end analysis (display verification, curve fitting, parameter extraction, report generation) in one guided interaction.
8. As a researcher comparing experimental trials, I want a `run_comparison_workflow` prompt template, so that I can automatically compute percentage differences and trendlines across multiple recorded runs.
9. As a core developer, I want the 7 fragmented graph modules collapsed into a single deep `graphs/` package, so that all graph UI automation, bounding box arithmetic, and popup menu interactions are encapsulated in one cohesive location.
10. As a tool router maintainer, I want `tools/displays.py` and `native_loop.py` to communicate through the single `manage_graph` seam, so that future changes to graph UI automation do not ripple across multiple server layers.
11. As an automation engineer, I want graph insertion and toolbox manipulation to exclusively leverage the centralized display harness primitives, so that coordinate math and click dispatching adhere to the project's coding standards.
12. As a CI engineer, I want all existing graph unit and integration tests to continue passing deterministically with zero regressions while introducing unified seam contract tests, so that remote CI remains green on every commit.

## Implementation Decisions

### 1. Deep Graph Domain Seam & Subsystem Architecture
- Establish `src/capstone_mcp/graphs/` containing:
  - `models.py`: Unified `GraphAction` enum covering 8 distinct actions (`CREATE`, `READ`, `FIT`, `SELECT_MEASUREMENT`, `TOOLBOX_DELTA`, `TOOLBOX_AREA`, `TOOLBOX_STATISTICS`, `ANALYZE`), alongside typed request and result models. No speculative variants.
  - `manager.py`: `GraphManager` engine and `manage_graph(app: Capstone, request: GraphRequest) -> GraphResult` seam.
  - `toolbox.py`: Dedicated floating smart toolbox controller (`ZSmartToolBox`) for delta coordinates, area integration, and statistics table.
  - `inspection.py`: Pure snapshot-based graph state reading, series detection, and analysis reporting.
  - `__init__.py`: Public seam exports and backward-compatible function aliases.
- Retire and delete the 7 shallow root files: `graph_control.py`, `graph_execution.py`, `graph_report.py`, `graph_requests.py`, `graph_state.py`, `graph_toolbox.py`, `graph_workflows.py`.

### 2. Compound MCP Tool with Deprecation Layer
- Register `capstone_manage_graph` in `tools/displays.py` as the primary, recommended compound tool for all graph operations.
- Retain existing individual tools (`capstone_create_graph`, `capstone_fit_graph`, etc.) as thin delegating adapters to `manage_graph`, marking their documentation as legacy to prevent client breakage while guiding agents toward the compound seam.

### 3. Systematic MCP Tool Annotations
- Audit all FastMCP tool registrations across `server.py`, `tools/displays.py`, `tools/instruments.py`, `tools/files.py`, and `tools/physics.py`.
- Apply `ToolAnnotations(readOnlyHint=True)` to all inspection and read-only tools:
  - `capstone_windows`, `capstone_snapshot`, `capstone_screenshot`, `capstone_read_graph`, `capstone_read_table`, `capstone_read_fft_peaks`, `capstone_inspect_file`, `capstone_file_datasets`, `capstone_tutor_get_lesson`.
- Apply `ToolAnnotations(destructiveHint=True)` to all state-destroying operations:
  - `capstone_delete_run`, `capstone_open_experiment` (when `discard_unsaved=True`).

### 4. Dynamic State Resources
- Register `capstone://status` in `server.py`: Returns a live JSON snapshot with `attached`, `process_id`, `main_window_handle`, `window_count`, `active_runs_count`, and `latest_error`.
- Register `capstone://runs/active` in `server.py`: Returns current run names and series from Data Summary.

### 5. Standardized Error Protocol
- Standardize tool error handling using FastMCP `CallToolResult(isError=True)` containing a consistent JSON error schema: `{"error_code": "...", "message": "...", "remediation": "..."}`.
- Prevent unhandled Python exceptions from leaking raw tracebacks over the wire.

### 6. Universal Workflow Prompts
- Implement `data_analysis_workflow` in `server.py`: Directs the agent to observe the graph, apply the appropriate curve fit, compute theoretical discrepancies, and generate a summary report.
- Implement `run_comparison_workflow` in `server.py`: Directs the agent to iterate over multiple recorded runs, overlay them, and output a comparison matrix.

## Testing Decisions

- **Seam-Centric Verification**: Tests exercise public seams (`manage_graph`, FastMCP tool handlers, resource readers), never internal private functions.
- **Regression Protection**: Existing test suites (`test_graph_workflows.py`, `test_graph_toolbox.py`, `test_graph_state.py`, `test_graph_fit.py`, `test_graph_report.py`, `test_graph_execution.py`) are preserved and updated to import from `capstone_mcp.graphs`.
- **Seam Contract Suite**: A dedicated test suite (`tests/test_graphs.py`) exercises all 8 `GraphAction` variants through `manage_graph`.
- **MCP Protocol Contract Suite**: A dedicated test suite (`tests/test_mcp_maturity.py`) verifies tool annotations, resource serialization, error formatting, and prompt rendering.
- **Headless & Offline CI**: All tests preserve offline guards (`pytest.mark.skipif`), guaranteeing deterministic CI runs in headless environments.

## Out of Scope

- Modifying the underlying Capstone binary or reverse-engineering new Qt widgets beyond the established `ZSmartToolBox`.
- Modifying mathematical algorithms in `numerics/` (the deep numerics engine from Phase 4 is complete).
- Modifying the binary record stream decoder in `capfiles/` (Phase 5 decoupled decoder is complete).

## Further Notes

- All changes adhere strictly to `CODING_STANDARDS.md` (no duplicate display shims, no speculative generality).
- All communications and documentation follow the project's language consistency guideline (Korean for user interactions).
