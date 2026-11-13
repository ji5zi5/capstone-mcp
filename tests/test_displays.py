# Copyright 2026 Capstone MCP contributors.
"""Unit contract tests for the unified Display subsystem and manage_display seam."""

from unittest.mock import MagicMock, patch

import pytest

from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.displays import (
    AddPageRequest,
    AddPageResult,
    CreateDigitsRequest,
    CreateDigitsResult,
    CreateFftResult,
    CreateScopeRequest,
    CreateScopeResult,
    CreateTableRequest,
    CreateTableResult,
    DisplayAction,
    DisplayRequest,
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
    manage_display,
)


@pytest.fixture
def mock_app() -> Capstone:
    return MagicMock(spec=Capstone)


# ---------------------------------------------------------------------------
# 1. Action Dispatch Contract Tests (10 Actions)
# ---------------------------------------------------------------------------


def test_manage_display_create_digits(mock_app: Capstone) -> None:
    expected = CreateDigitsResult(
        digits_name="Digits 1",
        measurement="Force",
        current_value=12.34,
        unit="N",
    )
    with patch(
        "capstone_mcp.displays.manager.create_digits",
        return_value=expected,
    ) as mock_cd:
        req = DisplayRequest(
            action=DisplayAction.CREATE_DIGITS,
            create_digits=CreateDigitsRequest(measurement="Force"),
        )
        res = manage_display(mock_app, req)
        assert res.action == DisplayAction.CREATE_DIGITS
        assert res.create_digits == expected
        assert res.digits == expected
        mock_cd.assert_called_once_with(mock_app, req.create_digits)


def test_manage_display_create_table(mock_app: Capstone) -> None:
    expected = CreateTableResult(table_name="Table 1")
    with patch(
        "capstone_mcp.displays.manager.create_table",
        return_value=expected,
    ) as mock_ct:
        req = DisplayRequest(
            action=DisplayAction.CREATE_TABLE,
            create_table=CreateTableRequest(table_name="Table 1"),
        )
        res = manage_display(mock_app, req)
        assert res.action == DisplayAction.CREATE_TABLE
        assert res.create_table == expected
        assert res.table == expected
        mock_ct.assert_called_once_with(mock_app, req.create_table)


def test_manage_display_set_table_columns(mock_app: Capstone) -> None:
    expected = SetTableColumnsResult(
        table_name="Table 1",
        columns=["Time", "Position"],
        column_count=2,
    )
    with patch(
        "capstone_mcp.displays.manager.set_table_columns",
        return_value=expected,
    ) as mock_stc:
        req = DisplayRequest(
            action=DisplayAction.SET_TABLE_COLUMNS,
            set_table_columns=SetTableColumnsRequest(columns=["Time", "Position"]),
        )
        res = manage_display(mock_app, req)
        assert res.action == DisplayAction.SET_TABLE_COLUMNS
        assert res.set_table_columns == expected
        mock_stc.assert_called_once_with(mock_app, req.set_table_columns)


def test_manage_display_read_table(mock_app: Capstone) -> None:
    expected = ReadTableResult(
        table_name="Table 1",
        columns=["Time", "Position"],
        rows=[["0.0", "0.0"], ["0.1", "0.05"]],
        row_count=2,
        total_rows=2,
    )
    with patch(
        "capstone_mcp.displays.manager.read_table",
        return_value=expected,
    ) as mock_rt:
        req = DisplayRequest(
            action=DisplayAction.READ_TABLE,
            read_table=ReadTableRequest(limit=10),
        )
        res = manage_display(mock_app, req)
        assert res.action == DisplayAction.READ_TABLE
        assert res.read_table == expected
        mock_rt.assert_called_once_with(mock_app, req.read_table)


def test_manage_display_create_scope(mock_app: Capstone) -> None:
    expected = CreateScopeResult(
        display_id="Scope_1",
        timebase="10ms",
        channel="A",
    )
    with patch(
        "capstone_mcp.displays.manager.create_scope",
        return_value=expected,
    ) as mock_cs:
        req = DisplayRequest(
            action=DisplayAction.CREATE_SCOPE,
            create_scope=CreateScopeRequest(timebase="10ms", channel="A"),
        )
        res = manage_display(mock_app, req)
        assert res.action == DisplayAction.CREATE_SCOPE
        assert res.create_scope == expected
        assert res.scope == expected
        mock_cs.assert_called_once_with(mock_app, req.create_scope)


def test_manage_display_set_scope_trigger(mock_app: Capstone) -> None:
    expected = ScopeTriggerResult(
        scope_id="Scope_1",
        trigger_level=1.5,
        trigger_slope="rising",
        trigger_mode="auto",
    )
    with patch(
        "capstone_mcp.displays.manager.set_scope_trigger",
        return_value=expected,
    ) as mock_sst:
        req = DisplayRequest(
            action=DisplayAction.SET_SCOPE_TRIGGER,
            set_scope_trigger=SetScopeTriggerRequest(
                trigger_level=1.5,
                trigger_slope="rising",
            ),
        )
        res = manage_display(mock_app, req)
        assert res.action == DisplayAction.SET_SCOPE_TRIGGER
        assert res.set_scope_trigger == expected
        mock_sst.assert_called_once_with(mock_app, req.set_scope_trigger)


def test_manage_display_create_fft(mock_app: Capstone) -> None:
    expected = CreateFftResult(display_id="FFT_1")
    with patch(
        "capstone_mcp.displays.manager.create_fft",
        return_value=expected,
    ) as mock_cf:
        req = DisplayRequest(action=DisplayAction.CREATE_FFT)
        res = manage_display(mock_app, req)
        assert res.action == DisplayAction.CREATE_FFT
        assert res.create_fft == expected
        assert res.fft == expected
        mock_cf.assert_called_once()


def test_manage_display_read_fft_peaks(mock_app: Capstone) -> None:
    expected = ReadFftPeaksResult(
        fft_id="FFT_1",
        peaks=[],
        peak_count=0,
        dominant_frequency_hz=1000.0,
    )
    with patch(
        "capstone_mcp.displays.manager.read_fft_peaks",
        return_value=expected,
    ) as mock_rfp:
        req = DisplayRequest(
            action=DisplayAction.READ_FFT_PEAKS,
            read_fft_peaks=ReadFftPeaksRequest(top_k=3),
        )
        res = manage_display(mock_app, req)
        assert res.action == DisplayAction.READ_FFT_PEAKS
        assert res.read_fft_peaks == expected
        mock_rfp.assert_called_once_with(mock_app, req.read_fft_peaks)


def test_manage_display_add_page(mock_app: Capstone) -> None:
    expected = AddPageResult(page_index=2, title="Analysis Page")
    with patch(
        "capstone_mcp.displays.manager.add_page",
        return_value=expected,
    ) as mock_ap:
        req = DisplayRequest(
            action=DisplayAction.ADD_PAGE,
            add_page=AddPageRequest(title="Analysis Page"),
        )
        res = manage_display(mock_app, req)
        assert res.action == DisplayAction.ADD_PAGE
        assert res.add_page == expected
        assert res.page == expected
        mock_ap.assert_called_once_with(mock_app, req.add_page)


def test_manage_display_set_page_layout(mock_app: Capstone) -> None:
    expected = SetPageLayoutResult(layout="two_vertical", areas_created=2)
    with patch(
        "capstone_mcp.displays.manager.set_page_layout",
        return_value=expected,
    ) as mock_spl:
        req = DisplayRequest(
            action=DisplayAction.SET_PAGE_LAYOUT,
            set_page_layout=SetPageLayoutRequest(layout="two_vertical"),
        )
        res = manage_display(mock_app, req)
        assert res.action == DisplayAction.SET_PAGE_LAYOUT
        assert res.set_page_layout == expected
        assert res.layout == expected
        mock_spl.assert_called_once_with(mock_app, req.set_page_layout)


# ---------------------------------------------------------------------------
# 2. Error Handling & Payload Validation Tests
# ---------------------------------------------------------------------------


def test_manage_display_unsupported_action(mock_app: Capstone) -> None:
    req = DisplayRequest(action=DisplayAction.CREATE_DIGITS)
    object.__setattr__(req, "action", "unsupported_display_action")
    with pytest.raises(AutomationError, match="Unsupported display action"):
        _ = manage_display(mock_app, req)


def test_manage_display_missing_payload_raises(mock_app: Capstone) -> None:
    strict_actions = [
        (DisplayAction.SET_TABLE_COLUMNS, "set_table_columns"),
        (DisplayAction.SET_SCOPE_TRIGGER, "set_scope_trigger"),
        (DisplayAction.SET_PAGE_LAYOUT, "set_page_layout"),
    ]
    for action, field_name in strict_actions:
        req = DisplayRequest(action=action)
        with pytest.raises(AutomationError, match=f"{field_name} request must be provided"):
            _ = manage_display(mock_app, req)


def test_display_request_normalization_and_aliases() -> None:
    """Verify table-driven flat payload normalization and dictionary aliases."""
    # 1. Flat create_digits payload
    data_digits = {
        "action": "create_digits",
        "measurement": "Velocity",
        "digits_name": "Speed Readout",
    }
    req_digits = DisplayRequest.model_validate(data_digits)
    assert req_digits.action == DisplayAction.CREATE_DIGITS
    assert req_digits.create_digits is not None
    assert req_digits.create_digits.measurement == "Velocity"
    assert req_digits.create_digits.digits_name == "Speed Readout"

    # 2. Flat set_page_layout payload
    data_layout = {
        "action": "set_page_layout",
        "layout": "four_grid",
    }
    req_layout = DisplayRequest.model_validate(data_layout)
    assert req_layout.action == DisplayAction.SET_PAGE_LAYOUT
    assert req_layout.set_page_layout is not None
    assert req_layout.set_page_layout.layout == "four_grid"

    # 3. Flat set_scope_trigger payload
    data_trigger = {
        "action": "set_scope_trigger",
        "trigger_level": 2.5,
        "trigger_slope": "falling",
    }
    req_trigger = DisplayRequest.model_validate(data_trigger)
    assert req_trigger.action == DisplayAction.SET_SCOPE_TRIGGER
    assert req_trigger.set_scope_trigger is not None
    assert req_trigger.set_scope_trigger.trigger_level == 2.5
    assert req_trigger.set_scope_trigger.trigger_slope == "falling"

    # 4. Backward-compatible nested dictionary aliases
    data_alias = {
        "action": "create_table",
        "table": {"table_name": "Alias Table"},
    }
    req_alias = DisplayRequest.model_validate(data_alias)
    assert req_alias.create_table is not None
    assert req_alias.create_table.table_name == "Alias Table"
