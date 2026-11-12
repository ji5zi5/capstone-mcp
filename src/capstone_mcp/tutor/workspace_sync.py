# Copyright 2026 Capstone MCP contributors.
"""Synchronize and populate Matt Pocock teaching workspace files."""

from pathlib import Path

from capstone_mcp.tutor.curriculum import CANONICAL_EXPERIMENTS, ExperimentCurriculum

MISSION_TEMPLATE = """# Mission: University Physics Laboratory Mastery with PASCO Capstone & MCP Automation

## Why
Master classical and modern physics experimental principles by combining hands-on PASCO Capstone data acquisition with AI-guided computational analysis. Build the capability to automate instrument control, extract real-time experimental data, and generate publication-quality scientific reports with rigorous statistical and error analyses.

## Success looks like
- Autonomously configure Capstone hardware interfaces (850 Universal Interface, Smart Cart, Photogates, Signal Generators) for 5 canonical experiments.
- Execute automated measurement workflows (frequency sweeps, stopping voltage detection, cyclic P-V area integration).
- Derive fundamental physical constants (Planck's constant $h$, resonant frequency $f_0$, adiabatic index $\\gamma$, slit dimensions $a, d$) within 5% of theoretical values.
- Produce comprehensive laboratory reports adhering to peer-reviewed publication standards.

## Constraints
- Windows x64 laboratory workstation with PASCO Capstone installed.
- Must operate deterministically in headless/CI test environments when physical hardware is disconnected.
- Primary source laboratory manuals in Korean (.hwp, .docx, .pdf) serve as the ground truth.

## Out of scope
- Hardware component soldering or PCB electrical repairs.
- Proprietary PASCO firmware flashing outside standard Capstone software controls.
"""


RESOURCES_TEMPLATE = """# Physics Laboratory & Capstone Automation Resources

## Knowledge

### Primary Source Korean Laboratory Manuals
- `[현대물리]광전효과(EX-5549A, 850, CS)[9].hwp`
  - High-trust primary source for photoelectric effect theory, circuit wiring, and stopping voltage measurement.
- `[전자기] LRC 회로(CI-6512) - 공명진동수.docx`
  - Primary source for RLC resonance frequency, impedance minimization, and phase angle shifts.
- `[역학]강제 조화 진동(EX-5551A, Smart Cart, CS)[5].hwp`
  - Canonical manual for driven harmonic motion, eddy current magnetic damping, and resonance response curves.
- `[열역학]단열 기체 법칙(TD-8565)[13].hwp` & `[열역학]열기관(EX-5530B, 850, CS).pdf`
  - Theoretical basis for adiabatic compression ($PV^\\gamma = \\text{const}$) and cyclic work integration ($\\oint P dV$).
- `[광학] 빛의 간섭과 회절(OS-8441, CS)[1].hwp`
  - Manual for Fraunhofer single/double slit diffraction and intensity profiling with optical rotary translation.

### Physics Theory References
- Halliday, Resnick, Walker: *Fundamentals of Physics*, 12th Ed.
  - Used for governing differential equations and accepted physical constants ($h = 6.62607015 \\times 10^{-34} \\text{ J}\\cdot\\text{s}$, $\\gamma_{\\text{air}} = 1.40$).

## Wisdom (Communities)

- PASCO Scientific Teacher Community & Physics Forums:
  - Forum for sensor troubleshooting, experiment design tips, and Capstone workbook sharing.
- Korean Physical Society (KPS) Education Division:
  - University physics undergraduate laboratory standards and curriculum guidance.
"""

SHARED_CSS = """/* Tufte-inspired minimal clean typography for physics lessons and references */
:root {
  --bg-color: #fffff8;
  --text-color: #111111;
  --accent-color: #a00000;
  --border-color: #dcdcd0;
  --code-bg: #f4f4ea;
  --font-body: -apple-system, BlinkMacSystemFont, "Segoe UI", "Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans KR", sans-serif;
  --font-serif: "Georgia", "Nanum Myeongjo", serif;
  --font-mono: "Consolas", "Courier New", monospace;
}

body {
  background-color: var(--bg-color);
  color: var(--text-color);
  font-family: var(--font-body);
  line-height: 1.68;
  max-width: 840px;
  margin: 40px auto;
  padding: 0 24px;
}

h1, h2, h3 {
  font-family: var(--font-serif);
  color: #1a1a1a;
  font-weight: 700;
  margin-top: 1.6em;
  margin-bottom: 0.5em;
}

h1 {
  font-size: 2.2em;
  border-bottom: 2px solid var(--accent-color);
  padding-bottom: 8px;
}

h2 {
  font-size: 1.5em;
  border-bottom: 1px solid var(--border-color);
  padding-bottom: 4px;
}

p, li {
  font-size: 1.05em;
}

code {
  font-family: var(--font-mono);
  background: var(--code-bg);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.92em;
}

pre {
  background: var(--code-bg);
  border: 1px solid var(--border-color);
  padding: 14px 18px;
  border-radius: 6px;
  overflow-x: auto;
}

blockquote {
  margin: 20px 0;
  padding: 12px 20px;
  background: #fdf6e2;
  border-left: 4px solid var(--accent-color);
  font-style: italic;
}

table {
  width: 100%;
  border-collapse: collapse;
  margin: 20px 0;
}

th, td {
  border: 1px solid var(--border-color);
  padding: 10px 14px;
  text-align: left;
}

th {
  background-color: #f2f2e6;
  font-weight: 600;
}

.step-card {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 18px;
  margin-bottom: 18px;
  background: #ffffff;
  box-shadow: 0 2px 5px rgba(0,0,0,0.02);
}

.step-header {
  font-weight: 700;
  color: var(--accent-color);
  margin-bottom: 8px;
  font-size: 1.15em;
}

.quiz-container {
  background: #f7f9f7;
  border: 1px solid #c8d8c8;
  border-radius: 8px;
  padding: 20px;
  margin: 24px 0;
}

.quiz-btn {
  display: block;
  width: 100%;
  text-align: left;
  margin: 8px 0;
  padding: 10px 14px;
  border: 1px solid #b0c0b0;
  border-radius: 6px;
  background: white;
  cursor: pointer;
  font-size: 1em;
  transition: all 0.2s;
}

.quiz-btn:hover {
  background: #eef6ee;
  border-color: #2b7a2b;
}

.footer {
  margin-top: 60px;
  padding-top: 20px;
  border-top: 1px solid var(--border-color);
  font-size: 0.9em;
  color: #666;
}
"""


def generate_reference_html(curr: ExperimentCurriculum) -> str:
    """Generate a clean printable Tufte-style HTML reference sheet."""
    eqs = "".join(f"<li><code>{eq}</code></li>" for eq in curr.governing_equations)
    equip = "".join(f"<li>{item}</li>" for item in curr.equipment)
    steps_html = "".join(
        f'<div class="step-card">'
        f'<div class="step-header">단계 {s.step_index}: {s.title}</div>'
        f"<p>{s.instructions}</p>"
        f"<p><strong>주의사항:</strong> {s.safety_notes}</p>"
        f"<p><strong>Capstone 설정:</strong> <code>{s.capstone_action}</code></p>"
        f"<p><strong>검증 기준:</strong> {s.validation_check}</p>"
        f"</div>"
        for s in curr.steps
    )
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>{curr.title} - 실험 레퍼런스 시트</title>
  <link rel="stylesheet" href="../assets/style.css">
</head>
<body>
  <h1>{curr.title}</h1>
  <p><strong>분야:</strong> {curr.domain} | <strong>식별자:</strong> <code>{curr.experiment_id}</code></p>

  <h2>기본 물리 이론 및 지배 방정식</h2>
  <p>{curr.theory_summary}</p>
  <ul>{eqs}</ul>

  <h2>실험 장비 구성</h2>
  <ul>{equip}</ul>

  <h2>실험 절차 및 Capstone 제어 지침</h2>
  {steps_html}

  <div class="footer">
    <p>PASCO Capstone MCP Pedagogical Tutor Reference Sheet</p>
  </div>
</body>
</html>
"""


def sync_teaching_workspace(workspace_root: str | Path) -> dict[str, list[str]]:
    """Initialize or update the teaching workspace files.

    Creates MISSION.md, RESOURCES.md, ./assets/style.css, and ./reference/*.html.

    Args:
        workspace_root: Root directory of the repository/workspace.

    Returns:
        Dictionary of created or updated file lists.
    """
    root = Path(workspace_root)
    created: list[str] = []

    # 1. Root files
    mission_file = root / "MISSION.md"
    if not mission_file.exists():
        mission_file.write_text(MISSION_TEMPLATE, encoding="utf-8")
        created.append(str(mission_file))

    resources_file = root / "RESOURCES.md"
    if not resources_file.exists():
        resources_file.write_text(RESOURCES_TEMPLATE, encoding="utf-8")
        created.append(str(resources_file))

    # 2. Assets directory
    assets_dir = root / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    css_file = assets_dir / "style.css"
    css_file.write_text(SHARED_CSS, encoding="utf-8")
    created.append(str(css_file))

    # 3. Reference directory
    ref_dir = root / "reference"
    ref_dir.mkdir(parents=True, exist_ok=True)

    for curr in CANONICAL_EXPERIMENTS.values():
        ref_path = ref_dir / f"{curr.experiment_id}.html"
        ref_html = generate_reference_html(curr)
        ref_path.write_text(ref_html, encoding="utf-8")
        created.append(str(ref_path))

    return {"created_or_updated": created}
