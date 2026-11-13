# Coding Standards for capstone-mcp

This document guides the review agent (`/code-review`) on repo-specific judgement calls that automated linters (`ruff`, `basedpyright`) cannot mechanically enforce.

---

## 1. Protocol Adapter & Error Code Stability

- **Immutable Error Codes**: Error codes (`code="..."`) across `native_loop.py`, `automation_models.py`, and domain tool routers are rigid external contracts. Never rename, alter casing, or repurpose existing error codes (e.g., `FRAME_REQUIRED`, `AUTOMATION_ERROR`, `STALE_FRAME`) without a formal ADR and versioned migration plan.
- **Fail-Fast Input Validation**: Protocol requests must reject missing handles or invalid bounds before dispatching across thread boundaries or waking GUI automation workers.

---

## 2. Tool Router & State Accessor Patterns

- **Dynamic Accessors for Mutable Globals**: When domain routers (`src/capstone_mcp/tools/*.py`) register FastMCP tools, mutable server state (such as `AcquisitionJobs` or `AutomationWorker`) must be accessed through dynamic callables (`jobs: Callable[[], AcquisitionJobs] = lambda: JOBS`) rather than static value captures. This guarantees lifecycle resets and test monkeypatching remain fully operational.
- **Pure Domain Isolation**: Domain routers should contain tool signature adapters and schema annotations only. Numerical algorithms, physics calculations, and data parsing must reside in dedicated deep modules (`numerics/`, `data_sources/`, `tutor/`).

---

## 3. Headless & Offline Test Guards

- **Deterministic CI Execution**: All tests interacting with desktop GUI windows, hardware interfaces, or golden sample fixtures must implement offline fallback guards (`pytest.mark.skipif(...)` or `pytest.skip(...)`), ensuring 100% deterministic test execution in headless environments.
- **Windows Process Lock Discipline**: Test fixtures that launch or inspect background worker processes must terminate child threads and processes cleanly in `finally` blocks or fixture teardowns.

---

## 4. UI Automation & Display Harness Primitives

- **Direct Display Harness Primitives**: UI automation modules (`digits_display.py`, `table_display.py`, `workbook_layout.py`, `runs/manager.py`) must invoke shared display harness primitives (`click_control`, `double_click_control`, `drag_control`, `center_coords`) directly from `capstone_mcp.displays`. Never define one-line forwarding wrapper functions (`_click`, `_click_control`) within individual domain files.
- **Coordinate Centralization**: Bounding box center calculations must use `center_coords(bounds)` rather than ad-hoc coordinate arithmetic.

---

## 5. Unified Seam Cohesion & No Speculative Generality

- **Action Dispatch Completeness**: Unified request models and action enums (`RunRequest`, `RunAction`) must only declare variants actively and immediately handled by the dispatcher. Never introduce speculative enum values or request fields that trigger unhandled branches.
- **Stateful vs Stateless Boundary**: Multi-cycle, stateful workflows (such as `CaptureSession` or acquisition jobs) must remain encapsulated in dedicated session classes rather than being mixed into discrete, single-shot request/result dispatchers.
- **Dispatcher Integration Test Synchronization**: When migrating discrete native operations into a unified domain seam (e.g., `manage_instrument` or `manage_graph`), update the dispatch integration suites (`tests/test_full_automation_suite.py`) within the same ticket to mock the unified seam rather than deleted discrete handler functions.

---

## 6. Native Deserialization & Reverse-Engineered Schema Fidelity

- **Exact Schema & Tag Preservation**: When decoding native desktop serialization formats (such as Capstone clipboard XML, COM property bags, or binary archive streams), never substitute hypothetical, sanitized, or speculative attribute names (`ActualParameter`, `ZBundleInputIndex`) for verified native identifiers. Always preserve the exact tags, attributes (`BundleMeasID`, `ZCFDICurveFitParameterDefinition`), and boolean representation conventions (`"TRUE"`/`"FALSE"`, `"1"`/`"0"`) discovered from primary sources and IDA disassembly.
- **Fail-Closed on Unknown Constructs**: Parser logic must validate element counts and schema bounds strictly, raising domain-specific parse errors rather than returning incomplete or corrupted state models.

---

## 7. FastMCP Protocol Envelopes & Backward Compatibility

- **Structured Error Envelopes**: Tool execution failures must never leak raw Python exception tracebacks across the protocol boundary. All tool errors must return `CallToolResult(isError=True)` with consistent JSON payloads containing `error_code`, `message`, and actionable `remediation` instructions.
- **Pydantic Model Field Aliasing**: When refining or deepening field names on public domain models (e.g., `renderers` vs legacy `groups`), always maintain backward compatibility for existing callers and test suites by exposing `@computed_field @property` aliases.
- **Table-Driven Normalization Pattern**: When supporting ergonomic flat payload arguments alongside nested models on compound requests (e.g., `InstrumentRequest`, `GraphRequest`), use a static table mapping (`_FLAT_FIELD_MAPPINGS`) rather than verbose `if/elif` branches. Populate child model dictionaries strictly when flat arguments are non-empty (`if flat:`) to prevent spurious missing-field validation errors.
- **FastMCP Tool Handler Mocking Convention**: When writing unit contract tests for registered FastMCP tools, mock execution at the worker boundary (`patch.object(server.WORKER, "call", ...)`) rather than patching `server._native`. Because tool registration captures the `native` callable at startup, patching `server._native` after registration has no effect.

