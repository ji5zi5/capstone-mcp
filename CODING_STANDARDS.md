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
