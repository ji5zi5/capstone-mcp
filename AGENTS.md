# Agent Guidelines for capstone-mcp

This repository contains the Model Context Protocol (MCP) server for PASCO Capstone automation, experiment data extraction, and numerical analysis.

## Development Environment & Commands

- Package manager & tool runner: `uv`
- Run test suite: `uv run pytest`
- Python runtime: Python 3.12+ (Windows x64)

## Agent Operational Guidelines

- **Pre-action Briefing**: Always output a brief 1-2 sentence message explaining what you are about to do before executing commands or launching tool sequences. Never run silent background actions without keeping the user informed.
- **Direct CLI Invocations**: Use direct binary commands (`uv run ...`, `git ...`, `gh ...`) rather than wrapping inside `powershell -Command "..."` to prevent IDE approval popup loops.
- **Offline Test Guards**: Live desktop GUI tests (e.g. `tests/test_protocol.py`) must include fallback guards (`pytest.skip`) when no GUI instance is attached, ensuring automated test suites pass deterministically in headless/CI environments.

## Agent skills

### Issue tracker

Issues and specs for this repo are tracked on GitHub Issues. See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical triage roles mapped to standard GitHub labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context repository layout (`GLOSSARY.md`, `docs/adr/`). See `docs/agents/domain.md`.
