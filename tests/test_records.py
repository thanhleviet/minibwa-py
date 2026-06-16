"""Tests for SAM/PAF record parsing, tag typing, and flag properties."""

from __future__ import annotations

import pytest

from minibwa import Alignment, MinibwaParseError, PafRecord


def test_alignment_field_types_and_values():
    line = "read1\t0\tchr1\t51\t60\t60M\t=\t100\t150\tACGTACGTAC\tIIIIIIIIII\tNM:i:0\tAS:i:120"
    aln = Alignment.from_sam_line(line)
    assert aln.qname == "read1"
    assert aln.flag == 0
    assert aln.rname == "chr1"
    assert aln.pos == 51
    assert aln.mapq == 60
    assert aln.cigar == "60M"
    assert aln.rnext == "="
    assert aln.pnext == 100
    assert aln.tlen == 150
    assert aln.seq == "ACGTACGTAC"
    assert aln.qual == "IIIIIIIIII"
    assert isinstance(aln.flag, int)
    assert isinstance(aln.pos, int)


def test_alignment_pos_is_one_based_and_pos0_helper():
    aln = Alignment.from_sam_line("r\t0\tc\t51\t60\t*\t*\t0\t0\t*\t*")
    assert aln.pos == 51
    assert aln.pos0 == 50


def test_alignment_star_preserved_for_unmapped():
    aln = Alignment.from_sam_line("r\t4\t*\t0\t0\t*\t*\t0\t0\t*\t*")
    assert aln.rname == "*"
    assert aln.cigar == "*"
    assert aln.seq == "*"
    assert aln.qual == "*"
    assert aln.is_unmapped
    assert not aln.is_mapped


@pytest.mark.parametrize(
    "flag,attr,expected",
    [
        (0, "is_mapped", True),
        (0, "is_unmapped", False),
        (1, "is_paired", True),
        (2, "is_proper_pair", True),
        (4, "is_unmapped", True),
        (8, "mate_is_unmapped", True),
        (16, "is_reverse", True),
        (32, "mate_is_reverse", True),
        (64, "is_read1", True),
        (128, "is_read2", True),
        (256, "is_secondary", True),
        (512, "is_qcfail", True),
        (1024, "is_duplicate", True),
        (2048, "is_supplementary", True),
    ],
)
def test_alignment_flag_properties(flag, attr, expected):
    aln = Alignment.from_sam_line(f"r\t{flag}\tc\t1\t0\t*\t*\t0\t0\t*\t*")
    assert getattr(aln, attr) is expected


def test_alignment_tag_typing():
    line = (
        "r\t0\tc\t1\t0\t*\t*\t0\t0\t*\t*"
        "\tNM:i:3\tAS:i:90\tMD:Z:60\tXA:A:P\tBB:B:i,1,2,3\tBF:B:f,0.5,1.5"
    )
    tags = Alignment.from_sam_line(line).tags
    assert tags["NM"] == 3 and isinstance(tags["NM"], int)
    assert tags["AS"] == 90
    assert tags["MD"] == "60" and isinstance(tags["MD"], str)
    assert tags["XA"] == "P"
    assert tags["BB"] == [1, 2, 3]
    assert tags["BF"] == [0.5, 1.5]


def test_alignment_cs_tag_with_colon_preserved():
    # cs:Z::60 -> value ':60' (real engine output). split(':', 2) must keep it.
    line = "r\t0\tc\t1\t0\t*\t*\t0\t0\t*\t*\tcs:Z::60"
    tags = Alignment.from_sam_line(line).tags
    assert tags["cs"] == ":60"


def test_alignment_tags_are_immutable_mapping():
    aln = Alignment.from_sam_line("r\t0\tc\t1\t0\t*\t*\t0\t0\t*\t*\tNM:i:0")
    tags = aln.tags
    with pytest.raises(TypeError):
        tags["NM"] = 9  # type: ignore[index]
    # Cached: same object on second access.
    assert aln.tags is tags


def test_alignment_truncated_line_raises_parse_error():
    with pytest.raises(MinibwaParseError) as excinfo:
        Alignment.from_sam_line("only\tthree\tcols")
    assert excinfo.value.line == "only\tthree\tcols"


def test_alignment_non_numeric_pos_raises_parse_error():
    bad = "r\t0\tc\tNOTNUM\t0\t*\t*\t0\t0\t*\t*"
    with pytest.raises(MinibwaParseError):
        Alignment.from_sam_line(bad)


def test_alignment_non_numeric_flag_raises_parse_error():
    bad = "r\tXX\tc\t1\t0\t*\t*\t0\t0\t*\t*"
    with pytest.raises(MinibwaParseError):
        Alignment.from_sam_line(bad)


def test_parse_error_is_value_error():
    assert issubclass(MinibwaParseError, ValueError)


def test_parse_error_carries_lineno():
    with pytest.raises(MinibwaParseError) as excinfo:
        Alignment.from_sam_line("bad", lineno=7)
    assert excinfo.value.lineno == 7


def test_sam_tag_parse_error_retains_lineno():
    # A malformed optional tag parsed lazily must still carry the source lineno
    # threaded through from_sam_line (the documented stream contract).
    aln = Alignment.from_sam_line("r\t0\tc\t1\t0\t*\t*\t0\t0\t*\t*\tNM:i:notanint", lineno=42)
    with pytest.raises(MinibwaParseError) as excinfo:
        _ = aln.tags
    assert excinfo.value.lineno == 42


# --- PAF -----------------------------------------------------------------


def test_paf_field_types_and_coords():
    line = "read1\t60\t0\t60\t+\tchr1\t600\t50\t110\t60\t60\t60\ttp:A:P\tcm:i:1\tNM:i:0"
    rec = PafRecord.from_paf_line(line)
    assert rec.qname == "read1"
    assert rec.qlen == 60
    assert rec.qstart == 0
    assert rec.qend == 60
    assert rec.strand == "+"
    assert rec.tname == "chr1"
    assert rec.tlen == 600
    assert rec.tstart == 50
    assert rec.tend == 110
    assert rec.matches == 60
    assert rec.aln_len == 60
    assert rec.mapq == 60
    assert rec.is_reverse is False
    assert rec.identity == 1.0


def test_paf_reverse_strand():
    line = "r\t60\t0\t60\t-\tc\t600\t50\t110\t30\t60\t40"
    rec = PafRecord.from_paf_line(line)
    assert rec.is_reverse is True
    assert rec.identity == 0.5


def test_paf_identity_none_when_aln_len_zero():
    line = "r\t60\t0\t60\t+\tc\t600\t50\t110\t0\t0\t40"
    rec = PafRecord.from_paf_line(line)
    assert rec.identity is None


def test_paf_tags():
    line = "r\t60\t0\t60\t+\tc\t600\t50\t110\t60\t60\t60\ttp:A:P\tcm:i:2\tcs:Z::60"
    tags = PafRecord.from_paf_line(line).tags
    assert tags["tp"] == "P"
    assert tags["cm"] == 2
    assert tags["cs"] == ":60"


def test_paf_truncated_line_raises():
    with pytest.raises(MinibwaParseError):
        PafRecord.from_paf_line("a\tb\tc")


def test_paf_non_numeric_raises():
    bad = "r\tBADLEN\t0\t60\t+\tc\t600\t50\t110\t60\t60\t60"
    with pytest.raises(MinibwaParseError):
        PafRecord.from_paf_line(bad)


def test_paf_invalid_strand_raises():
    bad = "r\t60\t0\t60\tZ\tc\t600\t50\t110\t60\t60\t60"
    with pytest.raises(MinibwaParseError) as excinfo:
        PafRecord.from_paf_line(bad, lineno=3)
    assert excinfo.value.lineno == 3


def test_paf_empty_strand_raises():
    bad = "r\t60\t0\t60\t\tc\t600\t50\t110\t60\t60\t60"
    with pytest.raises(MinibwaParseError):
        PafRecord.from_paf_line(bad)


def test_paf_tag_parse_error_retains_lineno():
    rec = PafRecord.from_paf_line(
        "r\t60\t0\t60\t+\tc\t600\t50\t110\t60\t60\t60\tNM:i:bad", lineno=9
    )
    with pytest.raises(MinibwaParseError) as excinfo:
        _ = rec.tags
    assert excinfo.value.lineno == 9


def test_header_line_is_not_a_valid_sam_record():
    # The record class itself does not special-case '@' lines; the iterator does.
    # An @SQ line has too few tab columns to be a record, so parsing fails.
    with pytest.raises(MinibwaParseError):
        Alignment.from_sam_line("@SQ\tSN:chr1\tLN:600")
