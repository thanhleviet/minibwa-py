"""Integration tests against the real ``minibwa`` engine.

Auto-skips entirely when no engine is available (neither on PATH nor via
MINIBWA_BIN), so CI without the engine still passes.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

import pytest

import minibwa
from minibwa import Alignment, PafRecord

from .conftest import DATA_DIR, requires_minibwa

pytestmark = pytest.mark.integration


@requires_minibwa
def test_version_matches_expected_shape():
    out = minibwa.version()
    assert out, "version() returned empty string"
    assert re.match(r"^0\.1-r\d+", out), f"unexpected version string: {out!r}"


@requires_minibwa
def test_index_creates_sidecar_files(tmp_path):
    prefix = tmp_path / "idx"
    idx = minibwa.index(DATA_DIR / "ref.fa", prefix)
    assert idx.exists()
    files = {path.name for path in idx.files}
    assert files == {"idx.l2b", "idx.mbw"}


@requires_minibwa
def test_map_sam_roundtrip(tmp_path):
    prefix = tmp_path / "idx"
    idx = minibwa.index(DATA_DIR / "ref.fa", prefix)
    records = list(minibwa.map(idx, DATA_DIR / "reads.fq"))
    assert records, "no SAM records parsed"
    assert all(isinstance(r, Alignment) for r in records)
    primary = [r for r in records if r.is_mapped and not r.is_secondary]
    assert primary, "no primary mapped alignment found"
    first = primary[0]
    assert first.qname
    assert isinstance(first.flag, int)
    assert first.pos >= 1


@requires_minibwa
def test_map_sam_header_and_reference_lengths(tmp_path):
    prefix = tmp_path / "idx"
    idx = minibwa.index(DATA_DIR / "ref.fa", prefix)
    it = minibwa.map(idx, DATA_DIR / "reads.fq")
    list(it)
    assert any(line.startswith("@SQ") for line in it.header)
    assert "chr1" in it.reference_lengths
    assert it.reference_lengths["chr1"] == 600


@requires_minibwa
def test_map_paf_roundtrip(tmp_path):
    prefix = tmp_path / "idx"
    idx = minibwa.index(DATA_DIR / "ref.fa", prefix)
    records = list(minibwa.map(idx, DATA_DIR / "reads.fq", paf=True))
    assert records, "no PAF records parsed"
    assert all(isinstance(r, PafRecord) for r in records)
    first = records[0]
    assert first.qname
    assert first.strand in ("+", "-")
    assert 0 <= first.mapq <= 255


@requires_minibwa
def test_map_to_file_returns_path(tmp_path):
    prefix = tmp_path / "idx"
    idx = minibwa.index(DATA_DIR / "ref.fa", prefix)
    out = tmp_path / "out.sam"
    result = minibwa.map(idx, DATA_DIR / "reads.fq", output=out)
    assert isinstance(result, Path)
    assert result == out
    assert result.exists()
    text = result.read_text()
    assert text, "output file is empty"
    # The engine routes the SAM header to stdout (discarded by run_to_file) and
    # writes the alignment records to the -o file, so the file holds records.
    record_lines = [line for line in text.splitlines() if line and not line.startswith("@")]
    assert record_lines, "no alignment records written to output file"
    first = Alignment.from_sam_line(record_lines[0])
    assert first.qname
    assert first.rname == "chr1"


@requires_minibwa
def test_engine_is_actually_present():
    # Sanity: this test only runs when the engine resolves; prove it.
    assert shutil.which("minibwa") or os.environ.get("MINIBWA_BIN")
