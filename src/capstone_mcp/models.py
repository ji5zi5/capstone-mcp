# Copyright 2026 Capstone MCP contributors.
"""Serializable observations and bounded inputs for Capstone automation."""

from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class Model(BaseModel):
    """Immutable data crossing the MCP boundary."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)


class Bounds(Model):
    """Screen-pixel rectangle, with exclusive right and bottom edges."""

    left: int
    top: int
    right: int
    bottom: int


class Point(Model):
    """Window-relative pixel position."""

    x: int
    y: int


class Window(Model):
    """One top-level window belonging to the attached Capstone process."""

    handle: int
    title: str
    process_id: int
    bounds: Bounds


class Control(Model):
    """An accessible control and its snapshot-scoped reference."""

    ref: str
    parent: str | None
    name: str
    control_type: str
    automation_id: str
    enabled: bool
    visible: bool
    bounds: Bounds


class Snapshot(Model):
    """Bounded accessibility tree; omitted descendants are reported explicitly."""

    window: Window
    controls: list[Control]
    truncated: bool


class Action(StrEnum):
    """UI Automation actions; unsupported patterns produce a tool error."""

    INVOKE = "invoke"
    TOGGLE = "toggle"
    SELECT = "select"
    EXPAND = "expand"
    COLLAPSE = "collapse"
    FOCUS = "focus"


class Button(StrEnum):
    """Physical mouse buttons."""

    LEFT = "left"
    RIGHT = "right"
    MIDDLE = "middle"


class Result(Model):
    """Acknowledgement of input delivery, not of an application's business result."""

    delivered: bool = True
    detail: str
    interrupted: bool = False
    typed_text: str | None = None
    popup_window: Window | None = None


class ToolErrorPayload(Model):
    """Structured error envelope for MCP tool failures."""

    error_code: str
    message: str
    remediation: str
