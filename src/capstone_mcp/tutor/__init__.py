# Copyright 2026 Capstone MCP contributors.
"""Interactive physics lab assistant and pedagogical tutor package."""

from capstone_mcp.tutor.curriculum import (
    ExperimentCurriculum,
    ExperimentStep,
    QuizQuestion,
    get_curriculum,
    list_experiments,
)
from capstone_mcp.tutor.lesson_generator import (
    LessonPlan,
    StepGuidance,
    TutorQuizQuestion,
    TutorStep,
    generate_all_lessons,
    generate_lesson_html,
    get_lesson_plan,
    guide_lesson_step,
    normalize_experiment_id,
)
from capstone_mcp.tutor.manual_extractor import (
    extract_docx_text,
    extract_manual_text,
)
from capstone_mcp.tutor.workspace_sync import sync_teaching_workspace

__all__ = [
    "ExperimentCurriculum",
    "ExperimentStep",
    "LessonPlan",
    "QuizQuestion",
    "StepGuidance",
    "TutorQuizQuestion",
    "TutorStep",
    "extract_docx_text",
    "extract_manual_text",
    "generate_all_lessons",
    "generate_lesson_html",
    "get_curriculum",
    "get_lesson_plan",
    "guide_lesson_step",
    "list_experiments",
    "normalize_experiment_id",
    "sync_teaching_workspace",
]
