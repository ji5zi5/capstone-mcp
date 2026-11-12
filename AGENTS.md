# Agent Guidelines for capstone-mcp

This repository contains the Model Context Protocol (MCP) server for PASCO Capstone automation, experiment data extraction, and numerical analysis.

## Development Environment & Commands

- Package manager & tool runner: `uv`
- Run test suite: `uv run --no-sync pytest`
- Run linter: `uv run --no-sync ruff check src tests`
- Run type checker: `uv run --no-sync basedpyright src`
- Python runtime: Python 3.12+ (Windows x64)

## Agent Operational Guidelines

- **Windows Process Lock Guard**: Always pass `--no-sync` to `uv run` during testing and linting commands to prevent `os error 32` file locking when background MCP server processes hold `capstone-mcp.exe`.
- **Pre-action Briefing**: Always output a brief 1-2 sentence message explaining what you are about to do before executing commands or launching tool sequences. Never run silent background actions without keeping the user informed.
- **Direct CLI Invocations**: Use direct binary commands (`uv run ...`, `git ...`, `gh ...`) rather than wrapping inside `powershell -Command "..."` to prevent IDE approval popup loops.
- **Offline Test Guards**: Live desktop GUI tests (e.g. `tests/test_protocol.py`) and external machine-dependent fixtures (e.g. `tests/test_golden_master.py`) must include fallback guards (`pytest.skip` / `pytestmark = pytest.mark.skipif(...)`), ensuring automated test suites pass deterministically in headless/CI environments.
- **Remote CI Verification (Definition of Done)**: Never report work complete or close a cycle immediately after `git push`. A build or fix is only done when `gh run watch` or `gh run list` explicitly confirms that GitHub Actions CI has finished with `completed: success`.
- **Branch Hygiene**: Merged or stale feature branches must be deleted locally (`git branch -d`) and on the remote (`git push origin --delete`) before closing a task.

## Agent skills

### Issue tracker

Issues and specs for this repo are tracked on GitHub Issues. See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical triage roles mapped to standard GitHub labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context repository layout (`GLOSSARY.md`, `docs/adr/`). See `docs/agents/domain.md`.

### Architecture & Module Map

FastMCP tool routers (`src/capstone_mcp/tools/`), deep numerics, and unified data sources. See `docs/architecture.md`.

### Review standards

Repo-specific judgement calls and review rules. See `CODING_STANDARDS.md`.
