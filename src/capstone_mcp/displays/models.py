# Copyright 2026 Capstone MCP contributors.
"""Domain models and schemas for Capstone displays and workbooks."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, computed_field, model_validator

from capstone_mcp.models import Model

# ---------------------------------------------------------------------------
# 1. Action Enumeration
# ---------------------------------------------------------------------------


class DisplayAction(StrEnum):
    """Supported display widget and workbook operations."""

    CREATE_DIGITS = "create_digits"
    CREATE_TABLE = "create_table"
    SET_TABLE_COLUMNS = "set_table_columns"
    READ_TABLE = "read_table"
    CREATE_SCOPE = "create_scope"
    SET_SCOPE_TRIGGER = "set_scope_trigger"
    CREATE_FFT = "create_fft"
    READ_FFT_PEAKS = "read_fft_peaks"
    ADD_PAGE = "add_page"
    SET_PAGE_LAYOUT = "set_page_layout"


# ---------------------------------------------------------------------------
# 2. Digits Display Models
# ---------------------------------------------------------------------------

DIGITS_PALETTE_NAME: Final = "Digits"
FLOAT_PATTERN: Final = re.compile(r"^[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$")
MAX_UNIT_STR_LEN: Final = 10


class CreateDigitsRequest(Model):
    """Specification for inserting a Digits display widget and binding a measurement."""

    measurement: str | None = None
    handle: int = 0
    digits_name: str | None = None
    allow_foreground: bool = True


class CreateDigitsResult(Model):
    """Outcome of Digits display creation, including current value and unit."""

    created: bool = True
    digits_name: str = "Digits"
    measurement: str | None = None
    current_value: float | None = None
    unit: str | None = None
    verified: bool = True
    detail: str = ""


# ---------------------------------------------------------------------------
# 3. Table Display Models
# ---------------------------------------------------------------------------

TABLE_PALETTE_NAME: Final = "Table"
ROW_Y_TOLERANCE_PX: Final = 5
MAX_HEADER_HEIGHT_PX: Final = 100
MARGIN_EXPAND_PX: Final = 50
EXPAND_RIGHT_PX: Final = 100

STATISTICS_KEYWORDS: Final = (
    "mean",
    "std dev",
    "stddev",
    "standard deviation",
    "minimum",
    "min",
    "maximum",
    "max",
    "count",
    "sum",
    "total",
)


class CreateTableRequest(Model):
    """Specification for inserting a Table display widget."""

    handle: int = 0
    table_name: str | None = None
    allow_foreground: bool = True


class CreateTableResult(Model):
    """Outcome of Table display creation."""

    created: bool = True
    table_name: str = "Table"
    verified: bool = True
    detail: str = ""


class SetTableColumnsRequest(Model):
    """Specification of columns/measurements to bind in a Table display."""

    columns: list[str] = Field(default_factory=list)
    handle: int = 0
    table_name: str | None = None
    allow_foreground: bool = True


class SetTableColumnsResult(Model):
    """Outcome of Table column configuration."""

    table_name: str
    columns: list[str]
    column_count: int
    verified: bool = True
    detail: str = ""


class ReadTableRequest(Model):
    """Specification for reading tabular cell data from a Table display."""

    table_name: str | None = None
    start_row: int = 0
    limit: int = 100
    handle: int = 0
    allow_foreground: bool = True


class ReadTableResult(Model):
    """Tabular data extracted from Table display."""

    table_name: str = "Table"
    columns: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    row_count: int = 0
    total_rows: int = 0
    page: int = 1
    page_size: int = 50
    total_pages: int = 1
    statistics: dict[str, dict[str, str]] = Field(default_factory=dict)
    has_more: bool = False
    verified: bool = True
    detail: str = ""


# ---------------------------------------------------------------------------
# 4. Scope and FFT Models
# ---------------------------------------------------------------------------

SCOPE_PALETTE_SUFFIX: Final = ".ObjNameScope"
FFT_PALETTE_SUFFIX: Final = ".ObjNameFFT"

type TriggerSlope = Literal["rising", "falling", "positive", "negative"]
type TriggerMode = Literal["auto", "normal", "single"]

VALID_SLOPES: Final = {
    "rising": "rising",
    "positive": "rising",
    "falling": "falling",
    "negative": "falling",
}

VALID_MODES: Final = {
    "auto": "auto",
    "normal": "normal",
    "single": "single",
}


class CreateScopeRequest(Model):
    """Specification for creating an oscilloscope display widget."""

    timebase: str | float | None = None
    channel: str | None = None
    handle: int = 0
    allow_foreground: bool = True


class CreateScopeResult(Model):
    """Outcome of oscilloscope display creation."""

    display_id: str
    display_type: str = "Scope"
    timebase: str | None = None
    channel: str | None = None
    verified: bool = True
    detail: str = ""


class SetScopeTriggerRequest(Model):
    """Specification for oscilloscope trigger settings."""

    scope_id: str | None = None
    trigger_level: float = 0.0
    trigger_slope: str = "rising"
    trigger_mode: str = "auto"
    trigger_source: str | None = None
    handle: int = 0
    allow_foreground: bool = True


class ScopeTriggerResult(Model):
    """Outcome of oscilloscope trigger configuration."""

    scope_id: str
    trigger_level: float
    trigger_slope: str
    trigger_mode: str
    trigger_source: str | None = None
    verified: bool = True
    detail: str = ""


class CreateFftRequest(Model):
    """Specification for creating an FFT frequency spectrum display."""

    handle: int = 0
    allow_foreground: bool = True


class CreateFftResult(Model):
    """Outcome of FFT frequency spectrum display creation."""

    display_id: str
    display_type: str = "FFT"
    verified: bool = True
    detail: str = ""


class FftPeakInfo(Model):
    """Single frequency peak in FFT spectrum."""

    frequency_hz: float
    amplitude: float


class ReadFftPeaksRequest(Model):
    """Specification for extracting prominent frequency peaks from FFT display."""

    fft_id: str | None = None
    top_k: int = 5
    min_amplitude: float | None = None
    handle: int = 0
    allow_foreground: bool = True


class ReadFftPeaksResult(Model):
    """Prominent frequency peaks extracted from FFT display."""

    fft_id: str
    peaks: list[FftPeakInfo]
    peak_count: int
    dominant_frequency_hz: float | None = None
    verified: bool = True
    detail: str = ""


# ---------------------------------------------------------------------------
# 5. Workbook Layout Models
# ---------------------------------------------------------------------------

ADD_PAGE_SUFFIX: Final = ".AddPageButton"
ADD_PAGE_NAMES: Final = ("Add Page", "New Page", "Create Page", "+")

type PageLayoutTemplate = Literal[
    "single",
    "two_vertical",
    "two_horizontal",
    "three_vertical",
    "three_horizontal",
    "four_grid",
]

LAYOUT_AREAS: Final[dict[PageLayoutTemplate, int]] = {
    "single": 1,
    "two_vertical": 2,
    "two_horizontal": 2,
    "three_vertical": 3,
    "three_horizontal": 3,
    "four_grid": 4,
}

LAYOUT_KEYWORDS: Final[dict[PageLayoutTemplate, tuple[str, ...]]] = {
    "single": ("single", "1 display", "template1", "templatesingle"),
    "two_vertical": (
        "two vertical",
        "two columns",
        "2 vertical",
        "2 columns",
        "template2v",
        "templatetwovertical",
        "vertical split",
    ),
    "two_horizontal": (
        "two horizontal",
        "two rows",
        "2 horizontal",
        "2 rows",
        "template2h",
        "templatetwohorizontal",
        "horizontal split",
    ),
    "three_vertical": (
        "three vertical",
        "3 displays",
        "three columns",
        "3 columns",
        "template3v",
        "templatethreevertical",
        "template3",
    ),
    "three_horizontal": (
        "three horizontal",
        "3 rows",
        "templatethreehorizontal",
        "template3h",
    ),
    "four_grid": (
        "four displays",
        "4 displays",
        "2x2",
        "grid",
        "template4",
        "templatefourdisplays",
        "four quadrants",
    ),
}


class AddPageRequest(Model):
    """Specification for adding a new workbook page."""

    title: str = "New Page"
    handle: int = 0
    allow_foreground: bool = True


class AddPageResult(Model):
    """Result of adding a new workbook page."""

    page_index: int
    title: str
    verified: bool = True
    detail: str = ""


class SetPageLayoutRequest(Model):
    """Specification for applying a multi-display layout template to current page."""

    layout: PageLayoutTemplate = "single"
    handle: int = 0
    allow_foreground: bool = True


class SetPageLayoutResult(Model):
    """Result of applying a layout template."""

    layout: PageLayoutTemplate
    areas_created: int
    verified: bool = True
    detail: str = ""


# ---------------------------------------------------------------------------
# 6. Unified Seam Request & Result Models
# ---------------------------------------------------------------------------

_FLAT_FIELD_MAPPINGS: Final[dict[str, tuple[str, ...]]] = {
    "create_digits": ("measurement", "handle", "digits_name", "allow_foreground"),
    "create_table": ("handle", "table_name", "allow_foreground"),
    "set_table_columns": ("columns", "handle", "table_name", "allow_foreground"),
    "read_table": ("table_name", "start_row", "limit", "handle", "allow_foreground"),
    "create_scope": ("timebase", "channel", "handle", "allow_foreground"),
    "set_scope_trigger": (
        "scope_id",
        "trigger_level",
        "trigger_slope",
        "trigger_mode",
        "trigger_source",
        "handle",
        "allow_foreground",
    ),
    "create_fft": ("handle", "allow_foreground"),
    "read_fft_peaks": (
        "fft_id",
        "top_k",
        "min_amplitude",
        "handle",
        "allow_foreground",
    ),
    "add_page": ("title", "handle", "allow_foreground"),
    "set_page_layout": ("layout", "handle", "allow_foreground"),
}


_FIELD_ALIASES: Final[dict[str, str]] = {
    "digits": "create_digits",
    "table": "create_table",
    "scope": "create_scope",
    "trigger": "set_scope_trigger",
    "fft": "create_fft",
    "page": "add_page",
}


class DisplayRequest(Model):
    """Unified request for all Capstone display and workbook layout operations."""

    action: DisplayAction
    create_digits: CreateDigitsRequest | None = None
    create_table: CreateTableRequest | None = None
    set_table_columns: SetTableColumnsRequest | None = None
    read_table: ReadTableRequest | None = None
    create_scope: CreateScopeRequest | None = None
    set_scope_trigger: SetScopeTriggerRequest | None = None
    create_fft: CreateFftRequest | None = None
    read_fft_peaks: ReadFftPeaksRequest | None = None
    add_page: AddPageRequest | None = None
    set_page_layout: SetPageLayoutRequest | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_payload(cls, data: object) -> object:
        if isinstance(data, dict):
            # Backward-compatible dictionary aliases
            for src, dst in _FIELD_ALIASES.items():
                if src in data and dst not in data:
                    data[dst] = data[src]
            if (
                "layout" in data
                and "set_page_layout" not in data
                and isinstance(data["layout"], dict)
            ):
                data["set_page_layout"] = data["layout"]

            action_raw = data.get("action")
            action_key = (
                action_raw.value
                if isinstance(action_raw, DisplayAction)
                else str(action_raw)
            )
            fields = _FLAT_FIELD_MAPPINGS.get(action_key)
            if fields and action_key not in data:
                flat = {k: data[k] for k in fields if k in data}
                if flat:
                    data[action_key] = flat
        return data
        return data


class DisplayResult(Model):
    """Unified result containing the outcome of the requested display operation."""

    action: DisplayAction
    create_digits: CreateDigitsResult | None = None
    create_table: CreateTableResult | None = None
    set_table_columns: SetTableColumnsResult | None = None
    read_table: ReadTableResult | None = None
    create_scope: CreateScopeResult | None = None
    set_scope_trigger: ScopeTriggerResult | None = None
    create_fft: CreateFftResult | None = None
    read_fft_peaks: ReadFftPeaksResult | None = None
    add_page: AddPageResult | None = None
    set_page_layout: SetPageLayoutResult | None = None

    @computed_field
    @property
    def digits(self) -> CreateDigitsResult | None:
        """Backward-compatible Digits result alias."""
        return self.create_digits

    @computed_field
    @property
    def table(self) -> CreateTableResult | None:
        """Backward-compatible Table result alias."""
        return self.create_table

    @computed_field
    @property
    def scope(self) -> CreateScopeResult | None:
        """Backward-compatible Scope result alias."""
        return self.create_scope

    @computed_field
    @property
    def fft(self) -> CreateFftResult | None:
        """Backward-compatible FFT result alias."""
        return self.create_fft

    @computed_field
    @property
    def page(self) -> AddPageResult | None:
        """Backward-compatible AddPage result alias."""
        return self.add_page

    @computed_field
    @property
    def layout(self) -> SetPageLayoutResult | None:
        """Backward-compatible SetPageLayout result alias."""
        return self.set_page_layout
