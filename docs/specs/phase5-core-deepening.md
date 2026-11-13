# Specification: Core Domain & Automation Deepening (Phase 5)

## Problem Statement

Following Phase 4's successful decomposition of `server.py` and establishment of the Numerics and Data Source seams, architectural friction remains concentrated in three core automation areas:

1. **Run Management Fragmentation**: The fundamental domain concept of a **Run (회차)** in Capstone's Data Summary tree is fragmented across 4 separate shallow modules (`src/capstone_mcp/run_rename.py`, `run_delete.py`, `run_visibility.py`, `run_capture.py`). Each module independently duplicates the regex pattern `run\s*#?\s*\d+`, snapshot control filtering, TreeItem node traversal, and modal confirmation dialog dismissal. Callers must import 4 different modules and 8 different request/result model classes to perform basic lifecycle operations on runs.
2. **Entangled CapFile Archive & Binary Record Decoding**: `src/capstone_mcp/capfiles.py` has grown into a 772-line monolith conjoining ZIP archive safety checks, defusedxml recursive DOM traversal, binary byte record unpacking (types 0, 1, 2), and domain model assembly. Unit tests validating low-level 8-byte record offsets are forced to construct synthetic ZIP files and XML envelopes, obscuring failure causes and slowing test execution.
3. **Scattered Display Automation Mechanics**: Six display modules (`digits_display.py`, `table_display.py`, `workbook_layout.py`, `oscilloscope_fft.py`, `graph_toolbox.py`) independently duplicate palette drag-and-drop mechanics, container resolution, and `hasattr(app, 'click')` fallback dispatch. Bugs fixed in one display's click helper do not propagate to the others.

## Solution

Deepen the architecture by applying deep module design principles (small interface, deep implementation, clean seams, high locality, and caller leverage):

1. **Deep Run Management Module (`capstone_mcp.runs`)**: Collapse the 4 shallow `run_*.py` modules into a single deep `runs` module. Provide a unified `manage_run` interface that encapsulates TreeItem lookup, regex matching, modal confirmation auto-dismissal, and visibility toggling behind a concise interface.
2. **Decoupled Binary Record Decoder (`capstone_mcp.capfiles.records`)**: Establish a clean internal seam between pure byte stream unpacking (`decode_records(data: bytes, ...) -> list[CapRecord]`) and high-level archive/XML extraction, isolating low-level byte decoding for rapid, deterministic unit testing without ZIP mocks.
3. **Unified Display Automation Harness (`capstone_mcp.displays.harness`)**: Consolidate palette dragging, display container resolution, and resilient control action dispatch into a single deep display harness, eliminating duplicated `_click` and `_find` helpers across all display modules.

## User Stories

1. As an AI agent controlling Capstone, I want a single unified `manage_run` interface for renaming, deleting, capturing, and toggling visibility of runs, so that I do not need to coordinate 4 different modules to manage experimental trials.
2. As a software developer, I want all Data Summary TreeItem search and regex matching logic concentrated in one module, so that changes to Capstone's UI tree structure only require modifying a single file.
3. As an automation engineer, I want run deletion confirmation modal dialogs to be automatically detected and dismissed within the run management module, so that unexpected modal popups never freeze the automation pipeline.
4. As a test author, I want to test binary `.cap` record unpacking directly with raw byte buffers, so that I do not have to write verbose synthetic ZIP archives to verify byte offset handling.
5. As a data pipeline maintainer, I want binary record decoding decoupled from defusedxml DOM traversal, so that changes to archive safety limits or XML schemas cannot inadvertently break numeric decoding.
6. As a UI automation maintainer, I want palette drag-and-drop operations for tables, graphs, digits displays, and oscilloscopes to share a single verified implementation, so that drag coordinate calculation is reliable across all display types.
7. As a desktop automation author, I want control click and invoke dispatch (`hasattr(app, 'click')` vs `app.act`) consolidated in one place, so that UI interaction fallbacks are handled uniformly throughout the codebase.
8. As an MCP client, I want all existing 75 MCP tools to maintain 100% backward compatibility, so that external consumers experience no breaking changes during refactoring.
9. As a review agent, I want 4 shallow files retired under the Deletion Test, so that codebase navigability and architectural locality are significantly improved.
10. As a CI engineer, I want the full test suite to execute deterministically in headless environments with offline test guards preserved, so that every commit passes remote CI without flakes.

## Implementation Decisions

### 1. Deep Run Management Module (`src/capstone_mcp/runs/`)
- Create `src/capstone_mcp/runs/` containing:
  - `models.py`: Unified `RunAction` enum (`RENAME`, `DELETE`, `SET_VISIBILITY`), `RunRequest`, and `RunResult`.
  - `manager.py`: `RunManager` encapsulating TreeItem discovery, regex matching (`run\s*#?\s*\d+`), modal dialog auto-dismissal, and snapshot synchronization.
  - Seam: `manage_run(app: Capstone, request: RunRequest) -> RunResult`
- Delete shallow files: `src/capstone_mcp/run_rename.py`, `src/capstone_mcp/run_delete.py`, `src/capstone_mcp/run_visibility.py`, `src/capstone_mcp/run_capture.py`.
- Maintain backward-compatible adapter functions in `tools/instruments.py` and `tools/displays.py`.

### 2. Decoupled Binary Record Decoder (`src/capstone_mcp/capfiles/`)
- Establish internal seam in `src/capstone_mcp/capfiles/`:
  - `records.py`: Pure byte-level record decoder with zero XML/ZIP dependencies.
    - Seam: `decode_numeric_payload(data: bytes, storage_type: int) -> list[Decimal | int | float | None]`
  - `archive.py`: Archive boundary validation, ZIP bomb guards, and defusedxml schema crawler.
  - High-level interface in `__init__.py`: `read_cap_file` and `extract_cap_datasets` preserve existing public contracts.

### 3. Unified Display Automation Harness (`src/capstone_mcp/displays/`)
- Create `src/capstone_mcp/displays/harness.py`:
  - `DisplayHarness` providing:
    - `drag_palette_item(app: Capstone, handle: int, item_name: str) -> None`
    - `locate_display_control(controls: list[Control], display_type: str) -> Control`
    - `resilient_click(app: Capstone, handle: int, control: Control, allow_foreground: bool = True) -> None`
- Refactor `digits_display.py`, `table_display.py`, `workbook_layout.py`, and `oscilloscope_fft.py` to consume `DisplayHarness`, deleting duplicated `_click` and `_find` helpers.

## Testing Decisions

- **External Behavior Testing**: Tests will verify end-to-end behavior across public interfaces rather than checking internal private helpers.
- **Run Management Tests (`tests/test_runs.py`)**: Exercise run renaming, deletion with mock dialogs, visibility toggles, and metadata capture against the unified `manage_run` seam.
- **Binary Record Tests (`tests/test_capfile_records.py`)**: High-speed, focused unit tests passing byte literals directly into `decode_numeric_payload` without ZIP wrappers.
- **Display Harness Tests (`tests/test_display_harness.py`)**: Unit tests validating palette dragging, container resolution, and resilient click fallbacks.
- **Full Suite Regression**: All 428 existing tests must pass with 0 failures, 0 ruff errors, and 0 basedpyright errors.

## Out of Scope

- Modifying MCP tool schemas, tool names, or JSON wire contracts (100% backward compatibility preserved).
- Hardware direct USB/serial protocol implementation (remains deferred to future phases).
- Modifying numerical algorithms in `capstone_mcp.numerics` or data sources in `capstone_mcp.data_sources`.

## Further Notes

- Execution will proceed via sequential tracer-bullet tickets:
  - Ticket 1: Deep Run Management Module (Collapse `run_*.py` cluster)
  - Ticket 2: Decouple Binary Record Stream Decoder from CapFile Parsing
  - Ticket 3: Consolidate Display Automation into Deep Display Harness
  - Ticket 4: Verification, Architecture Documentation & Production Release
