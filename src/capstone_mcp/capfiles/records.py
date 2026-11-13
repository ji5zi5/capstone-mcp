# Copyright 2026 Capstone MCP contributors.
"""Low-level binary record stream decoder for Capstone experiment payloads."""

from __future__ import annotations

from decimal import Decimal
from typing import Final

from capstone_mcp.numeric_storage import (
    DecodedScalars,
    NumericStorageError,
    decode_numeric_records,
    interval_values,
)

MAX_PAYLOAD_BYTES: Final = 16 * 1024 * 1024
MAX_RECORDS: Final = 1_000_000
MAX_VALUE_BYTES: Final = 1024 * 1024
RECORD_HEADER_SIZE: Final = 8
EMPTY_RECORD_TYPE: Final = 0
TEXT_RECORD_TYPE: Final = 2
DEPENDENT_STORAGE_TYPE: Final = 7
INDEPENDENT_STORAGE_TYPE: Final = 4
NUMERIC_STORAGE_TYPE: Final = 0
INTERVAL_STORAGE_TYPE: Final = 1


class CapFileError(ValueError):
    """Raised when a `.cap` archive or binary record payload is invalid."""


def decode_numeric_payload(
    payload: bytes,
    count: int,
    offset: Decimal = Decimal(0),
) -> DecodedScalars:
    """Decode raw little-endian attribute/double scalar records."""
    if count < 0 or count > MAX_RECORDS:
        msg = f"Record count {count} is outside the valid range (0-{MAX_RECORDS})."
        raise CapFileError(msg)
    if len(payload) > MAX_PAYLOAD_BYTES:
        msg = (
            f"Payload size {len(payload)} exceeds safety limit "
            f"({MAX_PAYLOAD_BYTES} bytes)."
        )
        raise CapFileError(msg)
    try:
        return decode_numeric_records(payload, count, offset)
    except NumericStorageError as exc:
        raise CapFileError(str(exc)) from exc


def _decode_single_text_value(
    payload: bytes,
    offset: int,
    value_size: int,
    record_index: int,
    member_name: str,
) -> tuple[str, int]:
    """Decode a single UTF-16 text record payload slice."""
    if value_size > MAX_VALUE_BYTES or value_size % 2:
        msg = f"Invalid UTF-16 value size in {member_name!r}."
        raise CapFileError(msg)

    end = offset + value_size
    if end > len(payload):
        msg = f"Truncated UTF-16 value {record_index} in {member_name!r}."
        raise CapFileError(msg)

    try:
        value = payload[offset:end].decode("utf-16-le")
    except UnicodeDecodeError as exc:
        msg = f"Invalid UTF-16 value {record_index} in {member_name!r}."
        raise CapFileError(msg) from exc

    return value, end


def decode_text_records(
    payload: bytes,
    count: int,
    *,
    member_name: str = "record_stream",
) -> list[str]:
    """Decode UTF-16 LE text records with 8-byte length/type headers."""
    if count < 0 or count > MAX_RECORDS:
        msg = f"Record count {count} is outside the valid range (0-{MAX_RECORDS})."
        raise CapFileError(msg)
    if len(payload) > MAX_PAYLOAD_BYTES:
        msg = (
            f"Payload size {len(payload)} exceeds safety limit "
            f"({MAX_PAYLOAD_BYTES} bytes)."
        )
        raise CapFileError(msg)

    values: list[str] = []
    offset = 0
    for record_index in range(count):
        if len(payload) - offset < RECORD_HEADER_SIZE:
            msg = (
                f"Truncated record header {record_index} in "
                f"{member_name!r}."
            )
            raise CapFileError(msg)

        record_type = int.from_bytes(payload[offset : offset + 4], "little")
        value_size = int.from_bytes(payload[offset + 4 : offset + 8], "little")
        offset += RECORD_HEADER_SIZE

        if record_type == EMPTY_RECORD_TYPE:
            if value_size != 0:
                msg = (
                    f"Unsupported non-zero size {value_size} for empty record "
                    f"type 0 in {member_name!r}."
                )
                raise CapFileError(msg)
            values.append("")
            continue

        if record_type != TEXT_RECORD_TYPE:
            msg = (
                f"Unsupported record type {record_type} in "
                f"{member_name!r}."
            )
            raise CapFileError(msg)

        value, offset = _decode_single_text_value(
            payload, offset, value_size, record_index, member_name,
        )
        values.append(value)

    return values


def decode_interval_coordinates(
    start: Decimal,
    interval: Decimal,
    count: int,
) -> list[Decimal]:
    """Reproduce ZIntervalCache start + index * interval coordinates."""
    try:
        return interval_values(start, interval, count)
    except NumericStorageError as exc:
        raise CapFileError(str(exc)) from exc
