# Copyright 2026 Capstone MCP contributors.
"""Primary-source lab manual text and structure extraction."""

import json
import shutil
import subprocess
import zipfile
from pathlib import Path

from defusedxml import ElementTree


def extract_docx_text(docx_path: str | Path) -> str:
    """Extract plain text from a Microsoft Word .docx file.

    Args:
        docx_path: Path to the .docx file.

    Returns:
        Extracted text lines joined by newlines.

    Raises:
        FileNotFoundError: If the docx file does not exist.
        ValueError: If the file is not a valid zip/docx archive.
    """
    path = Path(docx_path)
    if not path.exists():
        msg = f"DOCX file not found: {path}"
        raise FileNotFoundError(msg)

    try:
        with zipfile.ZipFile(path, "r") as z:
            if "word/document.xml" not in z.namelist():
                msg = f"Invalid DOCX archive (missing word/document.xml): {path}"
                raise ValueError(msg)
            xml_content = z.read("word/document.xml")
    except zipfile.BadZipFile as err:
        msg = f"Failed to unzip DOCX file: {path}"
        raise ValueError(msg) from err

    tree = ElementTree.fromstring(xml_content)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

    paragraphs: list[str] = []
    for p in tree.iter(f"{{{namespace['w']}}}p"):
        texts = [
            t.text for t in p.iter(f"{{{namespace['w']}}}t") if t.text is not None
        ]
        if texts:
            paragraphs.append("".join(texts).strip())

    return "\n\n".join(p for p in paragraphs if p)


def extract_hwp_text(hwp_path: str | Path, max_chars: int = 50000) -> str:
    """Extract text from a Korean Hancom HWP or HWPX file.

    Utilizes the `rhwp` executable if available in PATH, returning decoded page text.

    Args:
        hwp_path: Path to the .hwp or .hwpx file.
        max_chars: Maximum characters to extract before truncation.

    Returns:
        Extracted plain text across all pages.

    Raises:
        FileNotFoundError: If the file does not exist.
        RuntimeError: If extraction fails and no fallback is possible.
    """
    path = Path(hwp_path)
    if not path.exists():
        msg = f"HWP file not found: {path}"
        raise FileNotFoundError(msg)

    rhwp_bin = shutil.which("rhwp")
    if rhwp_bin:
        try:
            cmd = [
                rhwp_bin,
                "export-text",
                str(path),
                "--json",
                "--max-chars",
                str(max_chars),
            ]
            result = subprocess.run(  # noqa: S603
                cmd,
                capture_output=True,
                text=True,
                check=False,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                pages = data.get("pages", [])
                text_parts = [p.get("text", "") for p in pages if p.get("text")]
                return "\n\n".join(text_parts).strip()
        except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
            pass

    # Fallback: scan binary file for UTF-16 / ASCII text segments if rhwp is absent
    try:
        raw_bytes = path.read_bytes()
        # Look for PrvText or decoded strings
        decoded = raw_bytes.decode("utf-16-le", errors="ignore")
        # Filter for printable Hangul and ASCII characters
        cleaned = "".join(
            c for c in decoded if c.isalnum() or c.isspace() or c in ".,-()_/:=+"
        )
        return cleaned[:max_chars].strip()
    except Exception as err:
        msg = f"Failed to extract HWP text from {path}"
        raise RuntimeError(msg) from err


def extract_manual_text(manual_path: str | Path) -> str:
    """Extract full text from a physics lab manual (.docx, .hwp, .hwpx, .txt, .md).

    Args:
        manual_path: Path to the manual file.

    Returns:
        Clean plain text content of the manual.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If file format is unsupported.
    """
    path = Path(manual_path)
    if not path.exists():
        msg = f"Manual file does not exist: {path}"
        raise FileNotFoundError(msg)

    suffix = path.suffix.lower()
    if suffix in [".docx", ".doc"]:
        return extract_docx_text(path)
    if suffix in [".hwp", ".hwpx"]:
        return extract_hwp_text(path)
    if suffix in [".txt", ".md"]:
        return path.read_text(encoding="utf-8", errors="replace")

    # Generic fallback: attempt text decode
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        msg = f"Unsupported manual format or binary file: {suffix}"
        raise ValueError(msg) from None
