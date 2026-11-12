# Copyright 2026 Capstone MCP contributors.
"""Interactive lesson generation and pedagogical tutor models."""

import json
import re
from html import escape
from pathlib import Path
from typing import Final

from pydantic import Field

from capstone_mcp.models import Model
from capstone_mcp.tutor.curriculum import (
    CANONICAL_EXPERIMENTS,
    ExperimentCurriculum,
    get_curriculum,
    list_experiments,
)


class TutorQuizQuestion(Model):
    """Interactive quiz question model crossing MCP boundaries."""

    question: str
    options: list[str]
    correct_index: int
    explanation: str


class TutorStep(Model):
    """Single procedural step with instructions, safety warnings, and checks."""

    step_index: int
    title: str
    instructions: str
    safety_notes: str
    safety_warnings: str
    capstone_action: str
    validation_check: str
    validation_checks: str


class LessonPlan(Model):
    """Complete syllabus, equipment, theory, procedure, and quiz for an experiment."""

    experiment_id: str
    title: str
    domain: str
    syllabus: str
    full_syllabus: str = ""
    equipment: list[str]
    equipment_list: list[str] = Field(default_factory=list)
    theory: str
    theory_summary: str
    equations: list[str]
    governing_equations: list[str] = Field(default_factory=list)
    capstone_setup: dict[str, str]
    steps: list[TutorStep]
    quiz: list[TutorQuizQuestion]
    quiz_questions: list[TutorQuizQuestion] = Field(default_factory=list)
    reference_file: str
    lesson_file: str = ""


class StepGuidance(Model):
    """Targeted instructions, safety warnings, and validation checks for one step."""

    experiment_id: str
    step_index: int
    title: str
    instructions: str
    targeted_instructions: str
    safety_warnings: str
    safety_notes: str
    capstone_action: str
    validation_checks: str
    validation_check: str
    total_steps: int


ALIAS_MAP: Final[dict[str, str]] = {
    "1": "photoelectric_effect",
    "0001": "photoelectric_effect",
    "photoelectric": "photoelectric_effect",
    "photoelectric_effect": "photoelectric_effect",
    "0001_photoelectric_effect": "photoelectric_effect",
    "0001-photoelectric-effect": "photoelectric_effect",
    "2": "rlc_resonance",
    "0002": "rlc_resonance",
    "rlc": "rlc_resonance",
    "rlc_resonance": "rlc_resonance",
    "0002_rlc_resonance": "rlc_resonance",
    "0002-rlc-resonance": "rlc_resonance",
    "3": "forced_harmonic_oscillation",
    "0003": "forced_harmonic_oscillation",
    "forced_oscillation": "forced_harmonic_oscillation",
    "forced-oscillation": "forced_harmonic_oscillation",
    "forced_harmonic_oscillation": "forced_harmonic_oscillation",
    "0003_forced_oscillation": "forced_harmonic_oscillation",
    "0003-forced-oscillation": "forced_harmonic_oscillation",
    "4": "adiabatic_gas",
    "0004": "adiabatic_gas",
    "adiabatic": "adiabatic_gas",
    "adiabatic_gas": "adiabatic_gas",
    "0004_adiabatic_gas": "adiabatic_gas",
    "0004-adiabatic-gas": "adiabatic_gas",
    "5": "slit_diffraction",
    "0005": "slit_diffraction",
    "slit": "slit_diffraction",
    "slit_diffraction": "slit_diffraction",
    "0005_slit_diffraction": "slit_diffraction",
    "0005-slit-diffraction": "slit_diffraction",
}


def normalize_experiment_id(experiment_id: str) -> str:
    """Normalize input experiment string or alias to canonical ID.

    Args:
        experiment_id: Raw string identifier (e.g. '0001-photoelectric-effect', 'rlc').

    Returns:
        Canonical experiment ID.

    Raises:
        KeyError: If identifier cannot be mapped to any known canonical experiment.
    """
    raw = experiment_id.strip()
    if raw in CANONICAL_EXPERIMENTS:
        return raw

    cleaned = raw.lower().removesuffix(".html").strip()
    normalized = cleaned.replace("-", "_")
    stripped = re.sub(r"^\d+_", "", normalized)

    candidates = [cleaned, normalized, stripped]
    for cand in candidates:
        if cand in CANONICAL_EXPERIMENTS:
            return cand
        if cand in ALIAS_MAP:
            return ALIAS_MAP[cand]

    for key, curr in CANONICAL_EXPERIMENTS.items():
        ref_stem = curr.reference_file.removesuffix(".html")
        if ref_stem == cleaned or cleaned in key or key in cleaned:
            return key

    available = list(CANONICAL_EXPERIMENTS.keys())
    msg = f"Unknown experiment '{experiment_id}'. Available: {available}"
    raise KeyError(msg)


def get_lesson_plan(experiment_id: str) -> LessonPlan:
    """Retrieve full pedagogical lesson plan for an experiment.

    Args:
        experiment_id: Canonical ID or alias.

    Returns:
        Populated LessonPlan instance.
    """
    canonical_id = normalize_experiment_id(experiment_id)
    curr = get_curriculum(canonical_id)

    steps = [
        TutorStep(
            step_index=s.step_index,
            title=s.title,
            instructions=s.instructions,
            safety_notes=s.safety_notes,
            safety_warnings=s.safety_notes,
            capstone_action=s.capstone_action,
            validation_check=s.validation_check,
            validation_checks=s.validation_check,
        )
        for s in curr.steps
    ]

    quiz = [
        TutorQuizQuestion(
            question=q.question,
            options=list(q.options),
            correct_index=q.correct_index,
            explanation=q.explanation,
        )
        for q in curr.quiz_questions
    ]

    syllabus = (
        f"실험 과목: {curr.title}\n"
        f"물리 도메인: {curr.domain}\n"
        f"학습 목표: {curr.theory_summary}\n"
        f"실험 절차: 총 {len(steps)}단계 절차\n"
        f"형성 평가: 총 {len(quiz)}문항 인터랙티브 퀴즈"
    )

    return LessonPlan(
        experiment_id=curr.experiment_id,
        title=curr.title,
        domain=curr.domain,
        syllabus=syllabus,
        full_syllabus=syllabus,
        equipment=list(curr.equipment),
        equipment_list=list(curr.equipment),
        theory=curr.theory_summary,
        theory_summary=curr.theory_summary,
        equations=list(curr.governing_equations),
        governing_equations=list(curr.governing_equations),
        capstone_setup=dict(curr.capstone_setup),
        steps=steps,
        quiz=quiz,
        quiz_questions=quiz,
        reference_file=curr.reference_file,
        lesson_file=f"./lessons/{curr.reference_file}",
    )


def guide_lesson_step(experiment_id: str, step_index: int) -> StepGuidance:
    """Retrieve targeted instructions and validation checks for a single procedural step.

    Args:
        experiment_id: Canonical ID or alias.
        step_index: 1-based procedural step index.

    Returns:
        StepGuidance instance.

    Raises:
        ValueError: If step_index is out of range.
    """
    canonical_id = normalize_experiment_id(experiment_id)
    curr = get_curriculum(canonical_id)

    step = next((s for s in curr.steps if s.step_index == step_index), None)
    if step is None:
        valid_indices = [s.step_index for s in curr.steps]
        msg = (
            f"Step index {step_index} is invalid for experiment '{curr.experiment_id}'. "
            f"Valid step indices are: {valid_indices} (1 to {len(curr.steps)})."
        )
        raise ValueError(msg)

    return StepGuidance(
        experiment_id=curr.experiment_id,
        step_index=step.step_index,
        title=step.title,
        instructions=step.instructions,
        targeted_instructions=step.instructions,
        safety_warnings=step.safety_notes,
        safety_notes=step.safety_notes,
        capstone_action=step.capstone_action,
        validation_checks=step.validation_check,
        validation_check=step.validation_check,
        total_steps=len(curr.steps),
    )


def generate_lesson_html(curr: ExperimentCurriculum) -> str:
    """Generate a responsive HTML document with interactive quiz widgets.

    Args:
        curr: ExperimentCurriculum data.

    Returns:
        Self-contained HTML string with interactive quiz widget logic.
    """
    lesson_prefix = curr.reference_file.split("-")[0] if "-" in curr.reference_file else "0001"
    escaped_title = escape(curr.title)
    escaped_domain = escape(curr.domain)
    escaped_theory = escape(curr.theory_summary)

    eq_items = "".join(f"<li><code>{escape(eq)}</code></li>" for eq in curr.governing_equations)
    equip_items = "".join(
        f'<li class="equip-item"><label><input type="checkbox" class="equip-checkbox"> {escape(item)}</label></li>'
        for item in curr.equipment
    )

    setup_rows = "".join(
        f"<tr><td><code>{escape(k)}</code></td><td>{escape(v)}</td></tr>"
        for k, v in curr.capstone_setup.items()
    )

    step_cards = "".join(
        f"""
        <div class="step-card" id="step-{s.step_index}">
          <div class="step-badge">단계 {s.step_index}</div>
          <h3 class="step-title">{escape(s.title)}</h3>
          <p class="step-instructions">{escape(s.instructions)}</p>
          <div class="safety-box">
            <span class="box-icon">⚠️</span>
            <strong>주의사항:</strong> {escape(s.safety_notes)}
          </div>
          <div class="action-box">
            <span class="box-icon">⚙️</span>
            <strong>Capstone 제어 동작:</strong>
            <code>{escape(s.capstone_action)}</code>
          </div>
          <div class="validation-box">
            <span class="box-icon">✅</span>
            <strong>검증 기준:</strong> {escape(s.validation_check)}
          </div>
        </div>
        """
        for s in curr.steps
    )

    # Build interactive quiz cards
    quiz_cards = []
    quiz_data_items = []
    for q_idx, q in enumerate(curr.quiz_questions):
        quiz_data_items.append(
            {
                "correctIndex": q.correct_index,
                "explanation": q.explanation,
            },
        )
        options_html = "".join(
            f"""
            <button type="button" class="quiz-option-btn" data-qidx="{q_idx}" data-oidx="{o_idx}" onclick="handleQuizOption({q_idx}, {o_idx})">
              <span class="opt-label">{chr(65 + o_idx)}</span>
              <span class="opt-text">{escape(opt)}</span>
            </button>
            """
            for o_idx, opt in enumerate(q.options)
        )
        quiz_cards.append(
            f"""
            <div class="quiz-card" data-qidx="{q_idx}">
              <div class="quiz-question-header">
                <span class="quiz-badge">문항 {q_idx + 1}</span>
                <span class="quiz-question-text">{escape(q.question)}</span>
              </div>
              <div class="quiz-options">
                {options_html}
              </div>
              <div class="quiz-feedback" id="feedback-{q_idx}" style="display:none;"></div>
              <div class="quiz-explanation" id="explanation-{q_idx}" style="display:none;">
                <strong>💡 해설:</strong> {escape(q.explanation)}
              </div>
            </div>
            """,
        )

    all_quiz_cards = "".join(quiz_cards)
    quiz_json = json.dumps(quiz_data_items, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Lesson {lesson_prefix}: {escaped_title} - Capstone MCP Physics Tutor</title>
  <link rel="stylesheet" href="../assets/style.css">
  <style>
    :root {{
      --bg-color: #fcfcf9;
      --card-bg: #ffffff;
      --text-main: #1f2328;
      --text-muted: #59636e;
      --primary: #0969da;
      --accent: #8b1111;
      --success: #1a7f37;
      --warning: #9a6700;
      --danger: #cf222e;
      --border: #d0d7de;
      --code-bg: #f6f8fa;
    }}
    body {{
      background-color: var(--bg-color);
      color: var(--text-main);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans KR", sans-serif;
      line-height: 1.68;
      max-width: 880px;
      margin: 36px auto;
      padding: 0 20px;
    }}
    .lesson-header {{
      border-bottom: 2px solid var(--accent);
      padding-bottom: 16px;
      margin-bottom: 28px;
    }}
    .lesson-meta {{
      display: flex;
      gap: 12px;
      align-items: center;
      margin-bottom: 8px;
    }}
    .badge {{
      display: inline-block;
      padding: 3px 10px;
      font-size: 0.85em;
      font-weight: 600;
      border-radius: 12px;
      background: #eef2ff;
      color: var(--primary);
      border: 1px solid #c7d2fe;
    }}
    .badge-domain {{
      background: #fdf2f2;
      color: var(--accent);
      border-color: #fecaca;
    }}
    h1 {{
      font-size: 2em;
      margin: 8px 0;
      color: #111827;
    }}
    h2 {{
      font-size: 1.4em;
      border-bottom: 1px solid var(--border);
      padding-bottom: 6px;
      margin-top: 36px;
      margin-bottom: 14px;
      color: #1f2937;
    }}
    p, li {{
      font-size: 1.02em;
    }}
    code {{
      font-family: "Consolas", "Courier New", monospace;
      background: var(--code-bg);
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 0.92em;
      border: 1px solid #e1e4e8;
    }}
    .equation-list {{
      list-style-type: none;
      padding-left: 0;
    }}
    .equation-list li {{
      background: #f8fafc;
      border-left: 4px solid var(--primary);
      padding: 8px 14px;
      margin: 6px 0;
      border-radius: 0 4px 4px 0;
    }}
    .equip-item {{
      list-style-type: none;
      padding: 4px 0;
    }}
    .equip-checkbox {{
      margin-right: 8px;
      cursor: pointer;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 16px 0;
      background: var(--card-bg);
    }}
    th, td {{
      border: 1px solid var(--border);
      padding: 10px 14px;
      text-align: left;
    }}
    th {{
      background: #f3f4f6;
      font-weight: 600;
    }}
    .step-card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 20px;
      margin-bottom: 20px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.03);
    }}
    .step-badge {{
      display: inline-block;
      font-weight: 700;
      color: white;
      background: var(--accent);
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 0.85em;
      margin-bottom: 6px;
    }}
    .step-title {{
      margin: 4px 0 10px 0;
      font-size: 1.2em;
      color: #111827;
    }}
    .safety-box, .action-box, .validation-box {{
      padding: 10px 14px;
      border-radius: 6px;
      margin-top: 10px;
      font-size: 0.95em;
    }}
    .safety-box {{
      background: #fffbeb;
      border-left: 4px solid var(--warning);
      color: #78350f;
    }}
    .action-box {{
      background: #eff6ff;
      border-left: 4px solid var(--primary);
      color: #1e3a8a;
    }}
    .validation-box {{
      background: #f0fdf4;
      border-left: 4px solid var(--success);
      color: #14532d;
    }}
    .box-icon {{
      margin-right: 4px;
    }}
    /* Interactive Quiz Widget Styles */
    .quiz-section {{
      background: #f9fafb;
      border: 2px solid #e5e7eb;
      border-radius: 10px;
      padding: 24px;
      margin-top: 36px;
    }}
    .quiz-card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 18px;
      margin-bottom: 20px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.02);
    }}
    .quiz-question-header {{
      display: flex;
      align-items: baseline;
      gap: 10px;
      margin-bottom: 14px;
    }}
    .quiz-badge {{
      background: #4f46e5;
      color: white;
      font-size: 0.8em;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 4px;
      flex-shrink: 0;
    }}
    .quiz-question-text {{
      font-weight: 600;
      font-size: 1.05em;
      color: #1f2937;
    }}
    .quiz-options {{
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}
    .quiz-option-btn {{
      display: flex;
      align-items: center;
      gap: 12px;
      width: 100%;
      text-align: left;
      padding: 12px 16px;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: #ffffff;
      cursor: pointer;
      font-size: 0.98em;
      color: #374151;
      transition: all 0.15s ease-in-out;
    }}
    .quiz-option-btn:hover {{
      background: #f3f4f6;
      border-color: #9ca3af;
    }}
    .opt-label {{
      font-weight: 700;
      width: 24px;
      height: 24px;
      border-radius: 50%;
      background: #e5e7eb;
      color: #4b5563;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 0.85em;
      flex-shrink: 0;
    }}
    .quiz-option-btn.selected {{
      border-width: 2px;
    }}
    .quiz-option-btn.correct {{
      background: #ecfdf5;
      border-color: var(--success);
      color: #065f46;
    }}
    .quiz-option-btn.correct .opt-label {{
      background: var(--success);
      color: white;
    }}
    .quiz-option-btn.incorrect {{
      background: #fef2f2;
      border-color: var(--danger);
      color: #991b1b;
    }}
    .quiz-option-btn.incorrect .opt-label {{
      background: var(--danger);
      color: white;
    }}
    .quiz-option-btn.reveal-correct {{
      border-color: var(--success);
      background: #f0fdf4;
    }}
    .quiz-feedback {{
      margin-top: 14px;
      padding: 10px 14px;
      border-radius: 6px;
      font-size: 0.95em;
      font-weight: 500;
    }}
    .feedback-correct {{
      background: #dcfce7;
      color: #14532d;
      border-left: 4px solid var(--success);
    }}
    .feedback-incorrect {{
      background: #fee2e2;
      color: #991b1b;
      border-left: 4px solid var(--danger);
    }}
    .quiz-explanation {{
      margin-top: 8px;
      padding: 10px 14px;
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 6px;
      font-size: 0.92em;
      color: #334155;
    }}
    .quiz-controls {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-top: 20px;
      padding-top: 16px;
      border-top: 1px solid #e5e7eb;
    }}
    .score-tracker {{
      font-weight: 600;
      color: #374151;
    }}
    .quiz-reset-btn {{
      padding: 8px 16px;
      background: #ffffff;
      border: 1px solid var(--border);
      border-radius: 6px;
      cursor: pointer;
      font-weight: 500;
      transition: background 0.15s;
    }}
    .quiz-reset-btn:hover {{
      background: #f3f4f6;
    }}
    .lesson-footer {{
      margin-top: 50px;
      padding-top: 20px;
      border-top: 1px solid var(--border);
      color: var(--text-muted);
      font-size: 0.9em;
      text-align: center;
    }}
  </style>
</head>
<body>
  <div class="lesson-header">
    <div class="lesson-meta">
      <span class="badge">Lesson {lesson_prefix}</span>
      <span class="badge badge-domain">{escaped_domain}</span>
      <code>{escape(curr.experiment_id)}</code>
    </div>
    <h1>{escaped_title}</h1>
  </div>

  <h2>1. 실험 이론 및 지배 방정식</h2>
  <p>{escaped_theory}</p>
  <ul class="equation-list">
    {eq_items}
  </ul>

  <h2>2. 필요 실험 장비 구성</h2>
  <ul class="equipment-list">
    {equip_items}
  </ul>

  <h2>3. PASCO Capstone 하드웨어 및 소프트웨어 설정</h2>
  <table>
    <thead>
      <tr>
        <th style="width: 35%;">설정 파라미터</th>
        <th>구성 내용</th>
      </tr>
    </thead>
    <tbody>
      {setup_rows}
    </tbody>
  </table>

  <h2>4. 단계별 실험 절차 (Step-by-Step Guide)</h2>
  {step_cards}

  <section class="quiz-section">
    <h2>5. 형성 평가 인터랙티브 퀴즈 (Interactive Quiz Widget)</h2>
    <div id="quiz-container">
      {all_quiz_cards}
    </div>
    <div class="quiz-controls">
      <div class="score-tracker" id="score-display">
        진행 상황: <span id="solved-count">0</span> / {len(curr.quiz_questions)} 문항 응시 (<span id="correct-count">0</span> 정답)
      </div>
      <button type="button" class="quiz-reset-btn" onclick="resetQuiz()">다시 풀기 (Reset Quiz)</button>
    </div>
  </section>

  <div class="lesson-footer">
    <p>PASCO Capstone Model Context Protocol Pedagogical Lab Tutor &bull; Automated Lesson Engine</p>
  </div>

  <script>
    const QUIZ_DATA = {quiz_json};
    const answers = {{}};

    function handleQuizOption(qIdx, selectedOptIdx) {{
      const card = document.querySelector(`.quiz-card[data-qidx="${{qIdx}}"]`);
      if (!card) return;
      const qInfo = QUIZ_DATA[qIdx];
      const buttons = card.querySelectorAll('.quiz-option-btn');
      const feedbackEl = document.getElementById(`feedback-${{qIdx}}`);
      const explanationEl = document.getElementById(`explanation-${{qIdx}}`);

      answers[qIdx] = (selectedOptIdx === qInfo.correctIndex);

      buttons.forEach((btn, idx) => {{
        btn.classList.remove('selected', 'correct', 'incorrect', 'reveal-correct');
        if (idx === selectedOptIdx) {{
          btn.classList.add('selected');
          if (idx === qInfo.correctIndex) {{
            btn.classList.add('correct');
          }} else {{
            btn.classList.add('incorrect');
          }}
        }}
        if (idx === qInfo.correctIndex && selectedOptIdx !== qInfo.correctIndex) {{
          btn.classList.add('reveal-correct');
        }}
      }});

      feedbackEl.style.display = 'block';
      explanationEl.style.display = 'block';

      if (selectedOptIdx === qInfo.correctIndex) {{
        feedbackEl.className = 'quiz-feedback feedback-correct';
        feedbackEl.innerHTML = '🎉 <strong>정답입니다!</strong> 물리적 원리를 정확히 이해하셨습니다.';
      }} else {{
        feedbackEl.className = 'quiz-feedback feedback-incorrect';
        feedbackEl.innerHTML = '❌ <strong>오답입니다.</strong> 아래 해설을 읽고 개념을 다시 점검해보세요.';
      }}

      updateScore();
    }}

    function resetQuiz() {{
      for (const k of Object.keys(answers)) {{
        delete answers[k];
      }}
      document.querySelectorAll('.quiz-card').forEach((card, qIdx) => {{
        const buttons = card.querySelectorAll('.quiz-option-btn');
        buttons.forEach(btn => btn.classList.remove('selected', 'correct', 'incorrect', 'reveal-correct'));
        const feedbackEl = document.getElementById(`feedback-${{qIdx}}`);
        const explanationEl = document.getElementById(`explanation-${{qIdx}}`);
        if (feedbackEl) feedbackEl.style.display = 'none';
        if (explanationEl) explanationEl.style.display = 'none';
      }});
      updateScore();
    }}

    function updateScore() {{
      const answeredCount = Object.keys(answers).length;
      let correctCount = 0;
      for (const val of Object.values(answers)) {{
        if (val) correctCount++;
      }}
      const solvedEl = document.getElementById('solved-count');
      const correctEl = document.getElementById('correct-count');
      if (solvedEl) solvedEl.textContent = answeredCount;
      if (correctEl) correctEl.textContent = correctCount;
    }}
  </script>
</body>
</html>
"""


def generate_all_lessons(output_dir: str | Path = "lessons") -> list[Path]:
    """Generate all 5 canonical interactive HTML lessons in the specified directory.

    Args:
        output_dir: Destination path (default: './lessons').

    Returns:
        List of generated file paths.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []

    for curr in list_experiments():
        target_file = out / curr.reference_file
        html_content = generate_lesson_html(curr)
        target_file.write_text(html_content, encoding="utf-8")
        generated.append(target_file)

    return generated
