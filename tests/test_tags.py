"""Direct tests for the optional-tag parser :func:`minibwa._tags.parse_tags`.

These are pure-function tests (no subprocess) exercising the error and edge
branches that record-level tests only reach indirectly with well-formed tags.
"""

from __future__ import annotations

import pytest

from minibwa import MinibwaParseError
from minibwa._tags import parse_tags


def test_well_formed_int_float_string_and_array():
    tags = parse_tags(["NM:i:3", "XF:f:0.5", "MD:Z:60", "XA:A:P", "BB:B:i,1,2,3"])
    assert tags["NM"] == 3 and isinstance(tags["NM"], int)
    assert tags["XF"] == 0.5 and isinstance(tags["XF"], float)
    assert tags["MD"] == "60" and isinstance(tags["MD"], str)
    assert tags["XA"] == "P"
    assert tags["BB"] == [1, 2, 3]


def test_two_component_field_raises():
    with pytest.raises(MinibwaParseError):
        parse_tags(["NM:i"])


def test_non_numeric_int_raises():
    with pytest.raises(MinibwaParseError):
        parse_tags(["NM:i:notanint"])


def test_non_numeric_float_raises():
    with pytest.raises(MinibwaParseError):
        parse_tags(["XF:f:notafloat"])


def test_malformed_b_array_element_raises():
    with pytest.raises(MinibwaParseError):
        parse_tags(["BB:B:i,1,notnum"])


def test_empty_field_is_skipped():
    tags = parse_tags(["", "NM:i:0", ""])
    assert dict(tags) == {"NM": 0}


def test_unknown_type_passes_through_as_raw_string():
    tags = parse_tags(["Xx:Q:weird"])
    assert tags["Xx"] == "weird"


def test_hex_type_returns_raw_string():
    tags = parse_tags(["H1:H:1AE301"])
    assert tags["H1"] == "1AE301"


def test_b_array_float_subtype():
    tags = parse_tags(["BF:B:f,0.5,1.5"])
    assert tags["BF"] == [0.5, 1.5]


def test_b_array_unknown_subtype_keeps_raw_elements():
    tags = parse_tags(["BS:B:Z,foo,bar"])
    assert tags["BS"] == ["foo", "bar"]


def test_value_with_colon_preserved():
    # split(':', 2) keeps a colon inside the value (real engine's cs:Z::60).
    tags = parse_tags(["cs:Z::60"])
    assert tags["cs"] == ":60"


@pytest.mark.parametrize("bad", ["NM:i:x", "NM:i", "BB:B:i,1,x"])
def test_lineno_is_propagated_into_error(bad):
    with pytest.raises(MinibwaParseError) as excinfo:
        parse_tags([bad], lineno=42)
    assert excinfo.value.lineno == 42


def test_returned_mapping_is_immutable():
    tags = parse_tags(["NM:i:0"])
    with pytest.raises(TypeError):
        tags["NM"] = 9  # type: ignore[index]
