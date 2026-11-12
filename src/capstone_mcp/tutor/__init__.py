# Copyright 2026 Capstone MCP contributors.
"""Interactive physics lab assistant and pedagogical tutor package."""

from capstone_mcp.tutor.curriculum import (
    ExperimentCurriculum,
    get_curriculum,
    list_experiments,
)
from capstone_mcp.tutor.manual_extractor import (
    extract_docx_text,
    extract_manual_text,
)

__all__ = [
    "ExperimentCurriculum",
    "extract_docx_text",
    "extract_manual_text",
    "get_curriculum",
    "list_experiments",
]
