# Copyright 2026 Capstone MCP contributors.
"""Unified Display Manager engine and functional manage_display seam."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.displays.digits import create_digits
from capstone_mcp.displays.models import (
    AddPageRequest,
    AddPageResult,
    CreateDigitsRequest,
    CreateDigitsResult,
    CreateFftRequest,
    CreateFftResult,
    CreateScopeRequest,
    CreateScopeResult,
    CreateTableRequest,
    CreateTableResult,
    DisplayAction,
    DisplayRequest,
    DisplayResult,
    ReadFftPeaksRequest,
    ReadFftPeaksResult,
    ReadTableRequest,
    ReadTableResult,
    ScopeTriggerResult,
    SetPageLayoutRequest,
    SetPageLayoutResult,
    SetScopeTriggerRequest,
    SetTableColumnsRequest,
    SetTableColumnsResult,
)
from capstone_mcp.displays.scope import (
    create_fft,
    create_scope,
    read_fft_peaks,
    set_scope_trigger,
)
from capstone_mcp.displays.table import (
    create_table,
    read_table,
    set_table_columns,
)
from capstone_mcp.displays.workbook import add_page, set_page_layout

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DisplayManager Engine
# ---------------------------------------------------------------------------


class DisplayManager:
    """Central engine managing Capstone display widgets and workbook layouts."""

    def __init__(self, app: Capstone) -> None:
        """Initialize the display manager with a desktop Capstone instance."""
        self.app = app

    def create_digits(
        self,
        request: CreateDigitsRequest | None = None,
    ) -> CreateDigitsResult:
        """Create a Digits display widget on the active workbook page."""
        return create_digits(self.app, request)

    def create_table(
        self,
        request: CreateTableRequest | None = None,
    ) -> CreateTableResult:
        """Create a Table display widget on the active workbook page."""
        return create_table(self.app, request)

    def set_table_columns(
        self,
        request: SetTableColumnsRequest,
    ) -> SetTableColumnsResult:
        """Configure column measurements for a Table display."""
        return set_table_columns(self.app, request)

    def read_table(
        self,
        request: ReadTableRequest | None = None,
    ) -> ReadTableResult:
        """Read tabular cell data and column headers from a Table display."""
        return read_table(self.app, request)

    def create_scope(
        self,
        request: CreateScopeRequest | None = None,
    ) -> CreateScopeResult:
        """Create an Oscilloscope display widget on the active page."""
        return create_scope(self.app, request)

    def set_scope_trigger(
        self,
        request: SetScopeTriggerRequest,
    ) -> ScopeTriggerResult:
        """Configure hardware trigger settings on an Oscilloscope display."""
        return set_scope_trigger(self.app, request)

    def create_fft(
        self,
        request: CreateFftRequest | None = None,
    ) -> CreateFftResult:
        """Create an FFT (Fast Fourier Transform) display widget."""
        return create_fft(self.app, request)

    def read_fft_peaks(
        self,
        request: ReadFftPeaksRequest | None = None,
    ) -> ReadFftPeaksResult:
        """Read detected spectral peak frequencies and amplitudes from FFT."""
        return read_fft_peaks(self.app, request)

    def add_page(
        self,
        request: AddPageRequest | None = None,
    ) -> AddPageResult:
        """Add a new page tab to the Capstone workbook."""
        return add_page(self.app, request)

    def set_page_layout(
        self,
        request: SetPageLayoutRequest,
    ) -> SetPageLayoutResult:
        """Apply a multi-display grid template layout to the active page."""
        return set_page_layout(self.app, request)

    # -----------------------------------------------------------------------
    # Action Dispatchers
    # -----------------------------------------------------------------------

    def _manage_create_digits(self, request: DisplayRequest) -> DisplayResult:
        req = request.create_digits or CreateDigitsRequest()
        return DisplayResult(
            action=request.action,
            create_digits=self.create_digits(req),
        )

    def _manage_create_table(self, request: DisplayRequest) -> DisplayResult:
        req = request.create_table or CreateTableRequest()
        return DisplayResult(
            action=request.action,
            create_table=self.create_table(req),
        )

    def _manage_set_table_columns(self, request: DisplayRequest) -> DisplayResult:
        if request.set_table_columns is None:
            msg = (
                "set_table_columns request must be provided for "
                "SET_TABLE_COLUMNS action."
            )
            raise AutomationError(msg)
        return DisplayResult(
            action=request.action,
            set_table_columns=self.set_table_columns(request.set_table_columns),
        )

    def _manage_read_table(self, request: DisplayRequest) -> DisplayResult:
        req = request.read_table or ReadTableRequest()
        return DisplayResult(
            action=request.action,
            read_table=self.read_table(req),
        )

    def _manage_create_scope(self, request: DisplayRequest) -> DisplayResult:
        req = request.create_scope or CreateScopeRequest()
        return DisplayResult(
            action=request.action,
            create_scope=self.create_scope(req),
        )

    def _manage_set_scope_trigger(self, request: DisplayRequest) -> DisplayResult:
        if request.set_scope_trigger is None:
            msg = (
                "set_scope_trigger request must be provided for "
                "SET_SCOPE_TRIGGER action."
            )
            raise AutomationError(msg)
        return DisplayResult(
            action=request.action,
            set_scope_trigger=self.set_scope_trigger(request.set_scope_trigger),
        )

    def _manage_create_fft(self, request: DisplayRequest) -> DisplayResult:
        req = request.create_fft or CreateFftRequest()
        return DisplayResult(
            action=request.action,
            create_fft=self.create_fft(req),
        )

    def _manage_read_fft_peaks(self, request: DisplayRequest) -> DisplayResult:
        req = request.read_fft_peaks or ReadFftPeaksRequest()
        return DisplayResult(
            action=request.action,
            read_fft_peaks=self.read_fft_peaks(req),
        )

    def _manage_add_page(self, request: DisplayRequest) -> DisplayResult:
        req = request.add_page or AddPageRequest()
        return DisplayResult(
            action=request.action,
            add_page=self.add_page(req),
        )

    def _manage_set_page_layout(self, request: DisplayRequest) -> DisplayResult:
        if request.set_page_layout is None:
            msg = (
                "set_page_layout request must be provided for "
                "SET_PAGE_LAYOUT action."
            )
            raise AutomationError(msg)
        return DisplayResult(
            action=request.action,
            set_page_layout=self.set_page_layout(request.set_page_layout),
        )

    def manage(self, request: DisplayRequest) -> DisplayResult:
        """Unified dispatch method for all display actions."""
        dispatchers: dict[
            DisplayAction,
            Callable[[DisplayRequest], DisplayResult],
        ] = {
            DisplayAction.CREATE_DIGITS: self._manage_create_digits,
            DisplayAction.CREATE_TABLE: self._manage_create_table,
            DisplayAction.SET_TABLE_COLUMNS: self._manage_set_table_columns,
            DisplayAction.READ_TABLE: self._manage_read_table,
            DisplayAction.CREATE_SCOPE: self._manage_create_scope,
            DisplayAction.SET_SCOPE_TRIGGER: self._manage_set_scope_trigger,
            DisplayAction.CREATE_FFT: self._manage_create_fft,
            DisplayAction.READ_FFT_PEAKS: self._manage_read_fft_peaks,
            DisplayAction.ADD_PAGE: self._manage_add_page,
            DisplayAction.SET_PAGE_LAYOUT: self._manage_set_page_layout,
        }

        handler = dispatchers.get(request.action)
        if handler is None:
            msg = f"Unsupported display action: {request.action}"
            raise AutomationError(msg)

        logger.debug("Dispatching display action: %s", request.action)
        return handler(request)


# ---------------------------------------------------------------------------
# Functional Seam
# ---------------------------------------------------------------------------


def manage_display(app: Capstone, request: DisplayRequest) -> DisplayResult:
    """Primary functional seam for managing Capstone displays and workbook layout."""
    return DisplayManager(app).manage(request)
