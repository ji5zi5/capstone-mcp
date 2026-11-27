# Copyright 2026 Capstone MCP contributors.
"""Bounded pages of native CSV export text, without invented dataset identities."""

import csv
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Final, Literal, TextIO

from capstone_mcp.models import Model

MAX_CSV_BYTES: Final = 64 * 1024 * 1024
MAX_ROWS: Final = 1_000_000
MAX_COLUMNS: Final = 1024
MAX_PAGE_CELLS: Final = 100_000
DELIMITER_SAMPLE_ROWS: Final = 20

_ISO_WALL_CLOCK_RE: Final = re.compile(
    r"^(?P<body>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?)"
    r"(?P<tz>Z|[+-]\d{2}:\d{2})?$",
    re.IGNORECASE,
)


class CsvDataError(ValueError):
    """The exported text is malformed or exceeds extraction bounds."""


@dataclass
class CsvTable:
    """Validated CSV cells shared by paging and analysis adapters."""

    header: list[str]
    rows: list[list[str]]


def parse_csv_number(value: str) -> Decimal | None:
    """Parse decimal-point or decimal-comma values, without thousands grouping."""
    value = value.strip().removeprefix("\ufeff").strip()
    if value.startswith("\u2212"):
        value = "-" + value[1:]
    if not value:
        return None
    if "," in value and "." not in value and value.count(",") == 1:
        value = value.replace(",", ".")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        msg = f"Invalid numeric CSV value: {value!r}."
        raise CsvDataError(msg) from exc
    return number if number.is_finite() else None


def _csv_delimiter(stream: TextIO) -> str:
    candidates: list[str] = []
    header_candidates: list[str] = []
    for delimiter in (",", ";", "\t"):
        stream.seek(0)
        reader = csv.reader(stream, delimiter=delimiter, strict=True)
        try:
            header = next(reader, [])
            if len(header) <= 1:
                continue
            header_candidates.append(delimiter)
            consistent = True
            for index, row in enumerate(reader):
                if len(row) != len(header):
                    consistent = False
                    break
                if index + 1 >= DELIMITER_SAMPLE_ROWS:
                    break
            if consistent:
                candidates.append(delimiter)
        except csv.Error:
            continue
    candidates = candidates or header_candidates
    if len(candidates) > 1:
        msg = "CSV delimiter is ambiguous; export with quoted fields."
        raise CsvDataError(msg)
    return candidates[0] if candidates else ","


def _collect_csv_rows(
    stream: TextIO, offset: int, limit: int | None,
) -> tuple[list[str], list[list[str]], int, list[str | None]]:
    delimiter = _csv_delimiter(stream)
    stream.seek(0)
    reader = csv.reader(stream, delimiter=delimiter, strict=True)
    try:
        header = next(reader, None)
        if not header or len(header) > MAX_COLUMNS:
            msg = "CSV needs a header with at most 1024 columns."
            raise CsvDataError(msg)
        stop = MAX_ROWS if limit is None else offset + min(
            limit, MAX_PAGE_CELLS // len(header),
        )
        rows: list[list[str]] = []
        first_values: list[str | None] = [None] * len(header)
        count = 0
        for count, row in enumerate(reader, 1):
            if len(row) != len(header) or count > MAX_ROWS:
                msg = "CSV is ragged or exceeds the one-million-row limit."
                raise CsvDataError(msg)
            for col_idx, cell in enumerate(row):
                if first_values[col_idx] is None and cell.strip():
                    first_values[col_idx] = cell
            if offset < count <= stop:
                rows.append(row)
    except csv.Error as exc:
        raise CsvDataError(str(exc)) from exc
    return header, rows, count, first_values


def _read_csv_rows(
    source: Path, offset: int = 0, limit: int | None = None,
) -> tuple[list[str], list[list[str]], int, list[str | None]]:
    if source.stat().st_size > MAX_CSV_BYTES:
        msg = "CSV exceeds the 64 MiB extraction limit."
        raise CsvDataError(msg)
    with source.open("rb") as stream:
        bom = stream.read(2)
    encodings = (
        ("utf-16",) if bom in (b"\xff\xfe", b"\xfe\xff") else ("utf-8-sig", "cp949")
    )
    for encoding in encodings:
        try:
            with source.open(encoding=encoding, newline="") as stream:
                return _collect_csv_rows(stream, offset, limit)
        except UnicodeDecodeError:
            continue
    msg = "CSV must be UTF-8, BOM-marked UTF-16, or CP949 text."
    raise CsvDataError(msg)


def read_csv_table(path: str | Path) -> CsvTable:
    """Read a bounded, rectangular UTF-8/UTF-16/CP949 comma/semicolon/tab table."""
    header, rows, _, _ = _read_csv_rows(Path(path))
    return CsvTable(header, rows)


class CsvTimestampAxis(Model):
    """ISO-8601 wall-clock axis metadata preserving origin, timezone, and raw text."""

    origin_iso: str
    timezone_status: Literal[
        "explicit_offset",
        "mixed_offsets_normalized_utc",
        "naive_wall_clock",
    ]
    observed_offsets: list[str]
    elapsed_seconds: list[Decimal | None]


class CsvColumn(Model):
    """Raw header and cells; parsed numbers are not a native source-type claim."""

    index: int
    label: str
    values: list[str]
    numeric_values: list[Decimal | None] | None
    iso_timestamps: CsvTimestampAxis | None = None


class CsvPage(Model):
    """One page of an immutable export; column indices disambiguate repeated labels."""

    path: str
    row_count: int
    offset: int
    returned_rows: int
    next_offset: int | None
    columns: list[CsvColumn]


def parse_csv_iso_timestamp(value: str) -> tuple[datetime, str | None, str] | None:
    """Parse strict ISO-8601 date+time wall-clock text without matching bare numbers."""
    cleaned = value.strip().removeprefix("\ufeff").strip()
    if not cleaned:
        return None
    match = _ISO_WALL_CLOCK_RE.match(cleaned)
    if match is None:
        return None
    tz_raw = match.group("tz")
    offset_tag = "Z" if tz_raw and tz_raw.upper() == "Z" else tz_raw
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError as exc:
        msg = f"Invalid ISO-8601 CSV timestamp: {value!r}."
        raise CsvDataError(msg) from exc
    return parsed, offset_tag, cleaned


def _decimal_elapsed(target: datetime, base: datetime) -> Decimal:
    """Compute exact elapsed seconds between two datetimes as Decimal."""
    delta = target - base
    whole = Decimal(delta.days) * Decimal(86400) + Decimal(delta.seconds)
    if delta.microseconds == 0:
        return whole
    return whole + (Decimal(delta.microseconds) / Decimal(1_000_000))


def _resolve_timestamp_timezone(
    all_items: list[tuple[datetime, str | None, str]],
) -> tuple[
    bool,
    Literal[
        "explicit_offset",
        "mixed_offsets_normalized_utc",
        "naive_wall_clock",
    ],
    list[str],
]:
    """Validate uniform aware-vs-naive discipline and classify UTC offset usage."""
    aware_flags = {item[0].tzinfo is not None for item in all_items}
    if len(aware_flags) > 1:
        msg = "CSV timestamp column mixes timezone-aware and naive timestamps."
        raise CsvDataError(msg)
    is_aware = next(iter(aware_flags))
    if not is_aware:
        return False, "naive_wall_clock", []
    offsets = list({tag: None for _, tag, _ in all_items if tag is not None})
    status: Literal[
        "explicit_offset",
        "mixed_offsets_normalized_utc",
        "naive_wall_clock",
    ] = "explicit_offset" if len(offsets) <= 1 else "mixed_offsets_normalized_utc"
    return True, status, offsets


def parse_csv_iso_column(
    values: list[str],
    *,
    origin_raw: str | None = None,
) -> CsvTimestampAxis | None:
    """Validate and project an ISO-8601 column without discarding raw text."""
    origin_parsed = (
        parse_csv_iso_timestamp(origin_raw) if origin_raw is not None else None
    )
    parsed_cells: list[tuple[datetime, str | None, str] | None] = []
    has_iso = origin_parsed is not None
    has_invalid = False
    for value in values:
        parsed = parse_csv_iso_timestamp(value) if value.strip() else None
        if parsed is None and value.strip():
            has_invalid = True
        elif parsed is not None:
            has_iso = True
        parsed_cells.append(parsed)

    if not has_iso:
        return None
    if has_invalid:
        msg = "CSV timestamp column mixes ISO-8601 timestamps with invalid values."
        raise CsvDataError(msg)

    non_empty = [item for item in parsed_cells if item is not None]
    if origin_parsed is None:
        if not non_empty:
            return None
        origin_parsed = non_empty[0]

    is_aware, timezone_status, observed_offsets = _resolve_timestamp_timezone(
        [origin_parsed, *non_empty],
    )
    origin_dt, _, origin_text = origin_parsed
    base_dt = origin_dt.astimezone(UTC) if is_aware else origin_dt
    elapsed = [
        None
        if item is None
        else _decimal_elapsed(
            item[0].astimezone(UTC) if is_aware else item[0],
            base_dt,
        )
        for item in parsed_cells
    ]
    return CsvTimestampAxis(
        origin_iso=origin_text,
        timezone_status=timezone_status,
        observed_offsets=observed_offsets,
        elapsed_seconds=elapsed,
    )


def _numbers(values: list[str]) -> list[Decimal | None] | None:
    parsed: list[Decimal | None] = []
    has_value = False
    for value in values:
        if not value.strip():
            parsed.append(None)
            continue
        try:
            numeric = parse_csv_number(value)
        except CsvDataError:
            return None
        has_value = True
        parsed.append(numeric)
    return parsed if has_value else None


def read_csv_page(path: str, offset: int = 0, limit: int = 1000) -> CsvPage:
    """Read CSV without assuming unit symbols, run IDs, or time alignment."""
    if offset < 0 or limit < 1:
        msg = "CSV offset must be nonnegative and limit must be positive."
        raise CsvDataError(msg)
    source = Path(path).resolve()
    header, page, row_count, first_values = _read_csv_rows(source, offset, limit)
    columns: list[CsvColumn] = []
    for index, label in enumerate(header):
        values = [row[index] for row in page]
        numeric_values = _numbers(values)
        iso_timestamps = (
            None
            if numeric_values is not None
            else parse_csv_iso_column(values, origin_raw=first_values[index])
        )
        columns.append(
            CsvColumn(
                index=index,
                label=label,
                values=values,
                numeric_values=numeric_values,
                iso_timestamps=iso_timestamps,
            ),
        )
    next_offset = offset + len(page)
    return CsvPage(
        path=str(source),
        row_count=row_count,
        offset=offset,
        returned_rows=len(page),
        next_offset=next_offset if next_offset < row_count else None,
        columns=columns,
    )
