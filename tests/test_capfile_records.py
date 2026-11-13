# Copyright 2026 Capstone MCP contributors.
"""Pure byte-buffer tests for low-level CapFile binary record decoding."""

import struct
from decimal import Decimal

import pytest

from capstone_mcp.capfiles import (
    CapFileError,
    decode_interval_coordinates,
    decode_numeric_payload,
    decode_text_records,
)


def _pack_scalar(attribute: int, value: float) -> bytes:
    """Helper to pack a 12-byte Capstone scalar record (4-byte tag/attribute, 8-byte double)."""
    return struct.pack("<Id", attribute, value)


def _pack_text_record(record_type: int, text: str) -> bytes:
    """Helper to pack an 8-byte header + UTF-16 LE text payload."""
    if record_type == 0:
        return struct.pack("<II", 0, 0)
    raw = text.encode("utf-16-le")
    return struct.pack("<II", record_type, len(raw)) + raw


# ---------------------------------------------------------------------------
# Numeric Payload Decoding
# ---------------------------------------------------------------------------


def test_decode_numeric_payload_valid_samples() -> None:
    # Given: 3 scalars (valid numeric samples, tag = 1)
    buf = (
        _pack_scalar(1, 10.5)
        + _pack_scalar(1, 20.25)
        + _pack_scalar(1, -5.0)
    )

    # When: decode with offset 2.0
    decoded = decode_numeric_payload(buf, 3, Decimal("2.0"))

    # Then:
    assert decoded.values == [Decimal("12.5"), Decimal("22.25"), Decimal("-3.0")]
    assert decoded.text == ["12.5", "22.25", "-3.0"]
    assert decoded.attributes == [1, 1, 1]


def test_decode_numeric_payload_empty_and_nan_tags() -> None:
    # Given: tag 0 (empty), tag 3 (NaN), tag 1 (numeric)
    buf = (
        _pack_scalar(0, 0.0)
        + _pack_scalar(3, 0.0)
        + _pack_scalar(1, 42.0)
    )

    decoded = decode_numeric_payload(buf, 3, Decimal("0.0"))

    assert decoded.values == [None, None, Decimal("42.0")]
    assert decoded.text == ["", "NaN", "42.0"]
    assert decoded.attributes == [0, 3, 1]


def test_decode_numeric_payload_truncated_buffer_raises() -> None:
    # Given: 2 records requested (24 bytes needed), but only 16 bytes provided
    buf = _pack_scalar(1, 1.0) + b"\x01\x00\x00\x00"

    with pytest.raises(CapFileError, match="Truncated"):
        _ = decode_numeric_payload(buf, 2)


def test_decode_numeric_payload_unsupported_tag_raises() -> None:
    # Given: unsupported tag 2
    buf = _pack_scalar(2, 5.0)

    with pytest.raises(CapFileError, match="Unsupported numeric scalar tag"):
        _ = decode_numeric_payload(buf, 1)


def test_decode_numeric_payload_invalid_count_raises() -> None:
    with pytest.raises(CapFileError, match="outside the valid range"):
        _ = decode_numeric_payload(b"", -1)


# ---------------------------------------------------------------------------
# Text Records Decoding
# ---------------------------------------------------------------------------


def test_decode_text_records_valid_strings() -> None:
    # Given: 2 text records and 1 empty record
    buf = (
        _pack_text_record(2, "Voltage (V)")
        + _pack_text_record(0, "")
        + _pack_text_record(2, "Time (s)")
    )

    results = decode_text_records(buf, 3)

    assert results == ["Voltage (V)", "", "Time (s)"]


def test_decode_text_records_truncated_header_raises() -> None:
    # Given: only 4 bytes instead of 8 for header
    buf = struct.pack("<I", 2)

    with pytest.raises(CapFileError, match="Truncated record header"):
        _ = decode_text_records(buf, 1)


def test_decode_text_records_non_zero_size_empty_record_raises() -> None:
    # Given: record_type=0 but value_size=4
    buf = struct.pack("<II", 0, 4) + b"test"

    with pytest.raises(CapFileError, match="Unsupported non-zero size"):
        _ = decode_text_records(buf, 1)


def test_decode_text_records_unsupported_record_type_raises() -> None:
    buf = struct.pack("<II", 99, 0)

    with pytest.raises(CapFileError, match="Unsupported record type 99"):
        _ = decode_text_records(buf, 1)


def test_decode_text_records_odd_size_raises() -> None:
    # UTF-16 code units must be even-sized
    buf = struct.pack("<II", 2, 3) + b"abc"

    with pytest.raises(CapFileError, match="Invalid UTF-16 value size"):
        _ = decode_text_records(buf, 1)


def test_decode_text_records_truncated_payload_raises() -> None:
    # Header says 8 bytes, but only 4 bytes follow
    buf = struct.pack("<II", 2, 8) + b"ab"

    with pytest.raises(CapFileError, match="Truncated UTF-16 value"):
        _ = decode_text_records(buf, 1)


# ---------------------------------------------------------------------------
# Interval Coordinates Decoding
# ---------------------------------------------------------------------------


def test_decode_interval_coordinates_valid() -> None:
    coords = decode_interval_coordinates(
        start=Decimal("1.0"),
        interval=Decimal("0.25"),
        count=4,
    )

    assert coords == [
        Decimal("1.0"),
        Decimal("1.25"),
        Decimal("1.5"),
        Decimal("1.75"),
    ]
