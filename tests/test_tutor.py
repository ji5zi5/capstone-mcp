# Copyright 2026 Capstone MCP contributors.
"""Tests for tutor manual extraction, curriculum modeling, and workspace setup."""

import zipfile
from pathlib import Path

import pytest

from capstone_mcp.tutor.curriculum import (
    get_curriculum,
    list_experiments,
)
from capstone_mcp.tutor.manual_extractor import (
    extract_docx_text,
    extract_manual_text,
)
from capstone_mcp.tutor.workspace_sync import sync_teaching_workspace


def test_list_canonical_experiments() -> None:
    """Ensure canonical physics experiments are defined."""
    experiments = list_experiments()
    assert len(experiments) >= 5
    ids = {exp.experiment_id for exp in experiments}
    assert "photoelectric_effect" in ids
    assert "rlc_resonance" in ids
    assert "forced_harmonic_oscillation" in ids
    assert "adiabatic_gas" in ids
    assert "slit_diffraction" in ids


def test_get_curriculum_photoelectric_effect() -> None:
    """Verify detailed curriculum content for photoelectric effect."""
    curr = get_curriculum("photoelectric_effect")
    assert curr is not None
    assert curr.title == "광전 효과 (Photoelectric Effect)"
    assert "hf - phi" in curr.theory_summary or "h" in curr.theory_summary
    assert len(curr.equipment) > 0
    assert len(curr.steps) >= 5
    assert len(curr.quiz_questions) >= 2


def test_get_curriculum_unknown_raises() -> None:
    """Verify KeyError when requesting non-existent experiment curriculum."""
    with pytest.raises(KeyError, match="Unknown experiment"):
        get_curriculum("quantum_teleportation_nonexistent")


def test_extract_manual_missing_file_raises(tmp_path: Path) -> None:
    """Ensure missing manual files raise FileNotFoundError."""
    non_existent = tmp_path / "does_not_exist.hwp"
    with pytest.raises(FileNotFoundError):
        extract_manual_text(non_existent)


def test_extract_docx_text_valid(tmp_path: Path) -> None:
    """Ensure DOCX text extraction functions properly with XML document."""
    docx_path = tmp_path / "sample.docx"
    doc_xml = (
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        b'<w:document xmlns:w="http://schemas.openxmlformats.org/'
        b'wordprocessingml/2006/main">'
        b"<w:body>"
        b"<w:p><w:r><w:t>LRC \xed\x9a\x8c\xeb\xa1\x9c"
        b" - \xea\xb3\xb5\xeb\xaa\x85\xec\xa7\x84\xeb\x8f\x99\xec\x88\x98"
        b"</w:t></w:r></w:p>"
        b"<w:p><w:r><w:t>Sample text paragraph.</w:t></w:r></w:p>"
        b"</w:body></w:document>"
    )
    with zipfile.ZipFile(docx_path, "w") as z:
        z.writestr("word/document.xml", doc_xml)

    extracted = extract_docx_text(docx_path)
    assert "LRC 회로 - 공명진동수" in extracted
    assert "Sample text paragraph." in extracted


def test_extract_manual_text_real_downloads_file_if_present() -> None:
    """Smoke test manual extraction against real downloaded files if available."""
    dl_dir = Path(r"C:\Users\Jio\Downloads\(2026)캡스톤 실험별 파일")
    sample_docx = dl_dir / "[전자기] LRC 회로(CI-6512) - 공명진동수.docx"
    if sample_docx.exists():
        text = extract_manual_text(sample_docx)
        assert len(text) > 100


def test_sync_teaching_workspace(tmp_path: Path) -> None:
    """Verify initialization of teaching workspace files and references."""
    result = sync_teaching_workspace(tmp_path)
    assert len(result["created_or_updated"]) >= 7
    assert (tmp_path / "MISSION.md").exists()
    assert (tmp_path / "RESOURCES.md").exists()
    assert (tmp_path / "assets" / "style.css").exists()
    assert (tmp_path / "reference" / "photoelectric_effect.html").exists()
    assert (tmp_path / "reference" / "rlc_resonance.html").exists()
