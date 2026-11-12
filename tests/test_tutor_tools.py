# Copyright 2026 Capstone MCP contributors.
"""Tests for tutor MCP tools, resources, prompts, and lesson HTML generation."""

import json
from pathlib import Path

import pytest

from capstone_mcp.server import (
    MCP,
    capstone_tutor_get_lesson,
    capstone_tutor_guide_step,
    capstone_tutor_lessons_resource,
    physics_lab_tutor,
)
from capstone_mcp.tutor import (
    generate_all_lessons,
    get_curriculum,
)

CANONICAL_IDS = [
    "photoelectric_effect",
    "rlc_resonance",
    "forced_harmonic_oscillation",
    "adiabatic_gas",
    "slit_diffraction",
]


@pytest.mark.anyio
async def test_tutor_tools_and_resource_registered_on_fastmcp() -> None:
    """Verify tutor tools, resources, and prompts are properly registered."""
    tools = await MCP.list_tools()
    tool_names = {t.name for t in tools}
    assert "capstone_tutor_get_lesson" in tool_names
    assert "capstone_tutor_guide_step" in tool_names

    resources = await MCP.list_resources()
    resource_uris = {str(r.uri) for r in resources}
    assert "capstone://tutor/lessons" in resource_uris

    prompts = await MCP.list_prompts()
    prompt_names = {p.name for p in prompts}
    assert "physics_lab_tutor" in prompt_names


def test_tutor_get_lesson_all_canonical_experiments() -> None:
    """Ensure get_lesson returns complete syllabus, equipment, theory, and quiz."""
    for exp_id in CANONICAL_IDS:
        lesson = capstone_tutor_get_lesson(exp_id)
        assert lesson.experiment_id == exp_id
        assert len(lesson.title) > 0
        assert len(lesson.domain) > 0
        assert len(lesson.syllabus) > 0
        assert len(lesson.equipment) > 0
        assert len(lesson.equipment_list) > 0
        assert len(lesson.theory) > 0
        assert len(lesson.equations) > 0
        assert len(lesson.steps) >= 3
        assert len(lesson.quiz) >= 2
        assert len(lesson.reference_file) > 0

        # Verify steps details
        for idx, step in enumerate(lesson.steps, start=1):
            assert step.step_index == idx
            assert len(step.title) > 0
            assert len(step.instructions) > 0
            assert len(step.safety_warnings) > 0
            assert len(step.capstone_action) > 0
            assert len(step.validation_checks) > 0

        # Verify quiz details
        for q in lesson.quiz:
            assert len(q.question) > 0
            assert len(q.options) >= 2
            assert 0 <= q.correct_index < len(q.options)
            assert len(q.explanation) > 0


def test_tutor_get_lesson_aliases() -> None:
    """Verify robust experiment ID lookup via filenames, numbers, and aliases."""
    test_cases = [
        ("0001-photoelectric-effect", "photoelectric_effect"),
        ("0001-photoelectric-effect.html", "photoelectric_effect"),
        ("1", "photoelectric_effect"),
        ("photoelectric", "photoelectric_effect"),
        ("0002-rlc-resonance", "rlc_resonance"),
        ("rlc", "rlc_resonance"),
        ("forced_oscillation", "forced_harmonic_oscillation"),
        ("0003-forced-oscillation", "forced_harmonic_oscillation"),
        ("adiabatic", "adiabatic_gas"),
        ("slit", "slit_diffraction"),
    ]
    for alias, expected_id in test_cases:
        lesson = capstone_tutor_get_lesson(alias)
        assert lesson.experiment_id == expected_id


def test_tutor_get_lesson_unknown_raises() -> None:
    """Verify unknown experiment identifier raises KeyError."""
    with pytest.raises(KeyError, match="Unknown experiment"):
        capstone_tutor_get_lesson("quantum_teleportation_nonexistent")


def test_tutor_guide_step_valid_all_experiments() -> None:
    """Ensure guide_step provides targeted instructions and safety warnings."""
    for exp_id in CANONICAL_IDS:
        curr = get_curriculum(exp_id)
        for s in curr.steps:
            guidance = capstone_tutor_guide_step(exp_id, s.step_index)
            assert guidance.experiment_id == exp_id
            assert guidance.step_index == s.step_index
            assert guidance.title == s.title
            assert guidance.instructions == s.instructions
            assert guidance.targeted_instructions == s.instructions
            assert guidance.safety_warnings == s.safety_notes
            assert guidance.capstone_action == s.capstone_action
            assert guidance.validation_checks == s.validation_check
            assert guidance.total_steps == len(curr.steps)


def test_tutor_guide_step_invalid_indices_raise() -> None:
    """Ensure out-of-range step indices raise ValueError."""
    with pytest.raises(ValueError, match="is invalid for experiment"):
        capstone_tutor_guide_step("photoelectric_effect", 0)

    with pytest.raises(ValueError, match="is invalid for experiment"):
        capstone_tutor_guide_step("photoelectric_effect", 999)

    with pytest.raises(ValueError, match="is invalid for experiment"):
        capstone_tutor_guide_step("photoelectric_effect", -1)


def test_tutor_guide_step_unknown_experiment_raises() -> None:
    """Ensure unknown experiment identifier raises KeyError."""
    with pytest.raises(KeyError, match="Unknown experiment"):
        capstone_tutor_guide_step("invalid_id", 1)


def test_capstone_tutor_lessons_resource() -> None:
    """Verify tutor lessons resource returns valid JSON with all experiments."""
    resource_text = capstone_tutor_lessons_resource()
    catalog = json.loads(resource_text)

    assert isinstance(catalog, list)
    assert len(catalog) >= 5

    catalog_ids = {item["experiment_id"] for item in catalog}
    for exp_id in CANONICAL_IDS:
        assert exp_id in catalog_ids

    for item in catalog:
        assert "title" in item
        assert "domain" in item
        assert "theory_summary" in item
        assert "governing_equations" in item
        assert "equipment" in item
        assert item["total_steps"] >= 3
        assert item["total_quiz_questions"] >= 2
        assert item["reference_file"].endswith(".html")
        assert item["lesson_file"].startswith("./lessons/")


def test_physics_lab_tutor_prompt_default() -> None:
    """Verify physics_lab_tutor prompt with default arguments."""
    prompt_str = physics_lab_tutor()
    assert "Photoelectric Effect" in prompt_str
    assert "Theory Summary" in prompt_str
    assert "Governing Equations" in prompt_str
    assert "Required Equipment" in prompt_str
    assert "Target Step" in prompt_str
    assert "Validation Check" in prompt_str


def test_physics_lab_tutor_prompt_custom_step() -> None:
    """Verify physics_lab_tutor prompt for specific experiment and step."""
    prompt_str = physics_lab_tutor("rlc_resonance", step_index=2)
    assert "RLC" in prompt_str
    assert "공진" in prompt_str
    assert "주파수 스윕" in prompt_str
    assert "Target Step (2/3)" in prompt_str


def test_generated_html_lessons_exist_in_workspace() -> None:
    """Verify lessons exist in workspace with complete interactive widgets."""
    lessons_dir = Path("lessons")
    assert lessons_dir.is_dir()

    expected_files = [
        "0001-photoelectric-effect.html",
        "0002-rlc-resonance.html",
        "0003-forced-oscillation.html",
        "0004-adiabatic-gas.html",
        "0005-slit-diffraction.html",
    ]

    for fname in expected_files:
        html_file = lessons_dir / fname
        assert html_file.exists(), f"Lesson file {fname} was not found in ./lessons"
        content = html_file.read_text(encoding="utf-8")

        # Basic HTML validity
        assert "<!DOCTYPE html>" in content
        assert '<html lang="ko">' in content
        assert "<title>" in content

        # Sections
        assert "1. 실험 이론 및 지배 방정식" in content
        assert "2. 필요 실험 장비 구성" in content
        assert "3. PASCO Capstone 하드웨어 및 소프트웨어 설정" in content
        assert "4. 단계별 실험 절차" in content
        assert "5. 형성 평가 인터랙티브 퀴즈" in content

        # Interactive Quiz Widget verification
        assert "quiz-section" in content
        assert "quiz-card" in content
        assert "quiz-option-btn" in content
        assert "quiz-feedback" in content
        assert "quiz-explanation" in content
        assert "handleQuizOption" in content
        assert "resetQuiz" in content
        assert "QUIZ_DATA" in content
        assert "score-tracker" in content

        # Step cards
        assert "step-card" in content
        assert "safety-box" in content
        assert "action-box" in content
        assert "validation-box" in content


def test_generate_all_lessons_in_temp_directory(tmp_path: Path) -> None:
    """Verify generate_all_lessons can output to arbitrary target directory."""
    generated_paths = generate_all_lessons(tmp_path)
    assert len(generated_paths) == 5
    for p in generated_paths:
        assert p.exists()
        assert p.stat().st_size > 1000
