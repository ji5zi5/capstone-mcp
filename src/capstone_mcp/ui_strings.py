# Copyright 2026 Capstone MCP contributors.
"""Exact labels from Capstone's installed resources for controls without IDs."""

import re
import unicodedata
from functools import cache
from typing import Final

from capstone_mcp.desktop import EXECUTABLE

_ENGLISH: Final = {
    "STR_DISPLAY": "Display",
    "STR_MENU_DISPLAY_COPY_DISPLAY": "Copy Display",
    "STR_MENU_FILE": "File",
    "STR_EXPORT_DATA_DIALOG_SELECT_ALL": "Select All",
    "STR_EXPORT_DATA_DIALOG_OPTIONS": "Alignment Options",
    "STR_EXPORT_DATA_EXPORT_FORMAT_BUTTON_LABEL": "Export Format",
    "STR_EXPORT_DATA_EXPORT_FORMAT_CSV_MENU_ITEM": "Comma separated values",
    "STR_TABLE_DATA_ALIGNMENT_MODE_INDEX": "Align by Index",
    "STR_EXPORT_DATA_DIALOG_EXPORT": "Export to file...",
    "STR_CLOSE": "Close",
    "STR_PROPERTY_SENSOR_ZERO_SENSOR": "Zero Sensor Now",
    "STR_FORMAT_RUN_NAME": "Run #%1",
}


def _normalize(text: str) -> str:
    caption = text.replace("&&", "\0").replace("&", "").replace("\0", "&")
    return " ".join(unicodedata.normalize("NFC", caption).casefold().split())


@cache
def _labels() -> dict[str, set[str]]:
    labels = {key: {_normalize(text)} for key, text in _ENGLISH.items()}
    resources = EXECUTABLE.parent / "Resources" / "Strings"
    for resource in resources.glob("Capstone_???.txt"):
        try:
            text = resource.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            continue
        for line in text.splitlines():
            key, _, rest = line.partition("\t")
            _, _, caption = rest.partition("\t")
            if key in labels and caption.strip():
                labels[key].add(_normalize(caption))
    return labels


def label_matches(text: str, resource_key: str) -> bool:
    """Match a control caption to one known string ID across installed languages."""
    return _normalize(text) in _labels()[resource_key]


def numbered_run(text: str) -> str | None:
    """Read the number only from a complete native run caption or legacy Run label."""
    caption = _normalize(text)
    match = re.fullmatch(r"run\s*#?\s*(\d+)", caption)
    if match:
        return match[1]
    for template in _labels()["STR_FORMAT_RUN_NAME"]:
        if template.count("%1") == 1:
            pattern = re.escape(template).replace("%1", r"(\d+)")
            if match := re.fullmatch(pattern, caption):
                return match[1]
    return None
