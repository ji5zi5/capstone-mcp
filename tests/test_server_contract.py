# Copyright 2026 Capstone MCP contributors.
"""Regression contract test for capstone_mcp.server public exports."""

from capstone_mcp import server
from capstone_mcp.acquisition import RecordingStatus
from capstone_mcp.repetition import (
    AcquisitionJob,
    JobStatus,
    RepeatPlan,
)


class DummyBackend:
    """Dummy backend for job contract testing."""

    def __init__(self) -> None:
        self.uncertain = False

    def observe(self) -> RecordingStatus:
        return RecordingStatus(running=True, text="Recording")

    def save(self, _path: str) -> None:
        pass

    def close(self) -> None:
        pass


def test_server_public_exports_complete() -> None:
    """Verify all symbols in __all__ exist and match expected callable/object types."""
    assert hasattr(server, "__all__")
    assert len(server.__all__) > 0

    for name in server.__all__:
        assert hasattr(server, name), f"server.__all__ declares {name!r}, but module does not export it"
        obj = getattr(server, name)
        assert obj is not None


def test_acquisition_job_delegation_to_jobs_instance() -> None:
    """Verify that module-level capstone_acquisition_job delegates dynamically to server.JOBS."""
    plan = RepeatPlan(process_id=1, window_handle=1, duration_seconds=1)
    job = AcquisitionJob(plan, DummyBackend())

    server.JOBS.jobs["test_contract_job"] = job
    try:
        retrieved = server.capstone_acquisition_job("test_contract_job")
        status = JobStatus.model_validate(retrieved)
        assert status.job_id == "test_contract_job"
        assert status.state == "running"
    finally:
        server.JOBS.jobs.pop("test_contract_job", None)


def test_fastmcp_tool_count_contract() -> None:
    """Ensure FastMCP tool count does not regress below full capacity."""
    tools = server.MCP._tool_manager.list_tools()
    tool_names = {t.name for t in tools}
    assert len(tool_names) >= 75
    assert "capstone_attach" in tool_names
    assert "capstone_export_data" in tool_names
    assert "capstone_create_calculation" in tool_names
    assert "capstone_linear_fit" in tool_names
