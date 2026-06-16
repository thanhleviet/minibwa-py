"""Shared parser for SAM/PAF optional tags (``TAG:TYPE:VALUE``).

Both record types reuse this. Each field is split with ``str.split(':', 2)`` so
that ``Z``/``H``/``cs``/``ds`` values containing a colon (e.g. the real engine's
``cs:Z::70``) are preserved verbatim. Unknown TYPE codes are kept as the raw
string rather than guessing.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Union

from .errors import MinibwaParseError

__all__ = ["TagValue", "parse_tags"]

#: The value types a parsed optional tag can take: ``i`` -> int, ``f`` -> float,
#: ``A``/``Z``/``H``/unknown -> str, ``B`` -> list.
TagValue = Union[int, float, str, list]

_INT_SUBTYPES = frozenset("cCsSiI")
_FLOAT_SUBTYPES = frozenset("f")


def _parse_b_array(value: str, *, raw_field: str, lineno: int | None) -> list:
    """Parse a SAM ``B`` array: ``<subtype>,<v1>,<v2>,...``."""
    parts = value.split(",")
    subtype = parts[0] if parts else ""
    elements = parts[1:]
    try:
        if subtype in _INT_SUBTYPES:
            return [int(item) for item in elements]
        if subtype in _FLOAT_SUBTYPES:
            return [float(item) for item in elements]
    except ValueError as exc:
        raise MinibwaParseError(raw_field, lineno) from exc
    # Unknown subtype: keep the raw string elements untouched.
    return list(elements)


def parse_tags(fields: Sequence[str], *, lineno: int | None = None) -> Mapping[str, TagValue]:
    """Parse optional tag fields into an immutable typed mapping.

    Args:
        fields: The optional-tag columns (SAM cols 12+, PAF cols 13+).
        lineno: Optional 1-based source line number for error reporting.

    Returns:
        A read-only mapping of two-character tag -> typed value.

    Raises:
        MinibwaParseError: If a field is not ``TAG:TYPE:VALUE`` or a numeric
            type fails to coerce.
    """
    parsed: dict[str, TagValue] = {}
    for field in fields:
        if not field:
            continue
        components = field.split(":", 2)
        if len(components) != 3:
            raise MinibwaParseError(field, lineno)
        tag, typ, value = components
        parsed[tag] = _coerce(typ, value, raw_field=field, lineno=lineno)
    return MappingProxyType(parsed)


def _coerce(typ: str, value: str, *, raw_field: str, lineno: int | None) -> TagValue:
    """Coerce a single tag value according to its TYPE code."""
    try:
        if typ == "i":
            return int(value)
        if typ == "f":
            return float(value)
    except ValueError as exc:
        raise MinibwaParseError(raw_field, lineno) from exc
    if typ == "A":
        return value
    if typ == "Z":
        return value
    if typ == "H":
        # Raw hex string preserved as-is.
        return value
    if typ == "B":
        return _parse_b_array(value, raw_field=raw_field, lineno=lineno)
    # Unknown TYPE code: keep the raw value string rather than failing.
    return value
