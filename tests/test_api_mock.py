"""API behavior tests via the on-PATH fake_minibwa stub and monkeypatching."""

from __future__ import annotations

import gc
import os
import pathlib

import pytest

import minibwa
from minibwa import (
    Alignment,
    MinibwaNotFoundError,
    MinibwaRunError,
    PafIterator,
    PafRecord,
    SamIterator,
)


def test_version_from_stub(fake_minibwa):
    assert minibwa.version() == "0.1-r363"


def test_map_default_yields_alignments_and_skips_headers(fake_minibwa, tmp_path):
    reads = tmp_path / "reads.fq"
    reads.write_text("@r\nACGT\n+\nIIII\n")
    it = minibwa.map(minibwa.Index.from_prefix(str(tmp_path / "idx")), str(reads))
    assert isinstance(it, SamIterator)
    records = list(it)
    assert all(isinstance(r, Alignment) for r in records)
    # The stub's SAM has read1 (mapped) and read2 (unmapped); headers excluded.
    qnames = [r.qname for r in records]
    assert qnames == ["read1", "read2"]
    # Header captured, not yielded.
    assert any(line.startswith("@HD") for line in it.header)
    assert it.reference_lengths == {"chr1": 600}


def test_map_paf_yields_paf_records(fake_minibwa, tmp_path):
    reads = tmp_path / "reads.fq"
    reads.write_text("@r\nACGT\n+\nIIII\n")
    it = minibwa.map(str(tmp_path / "idx"), str(reads), paf=True)
    assert isinstance(it, PafIterator)
    records = list(it)
    assert len(records) == 2
    assert all(isinstance(r, PafRecord) for r in records)
    assert records[1].is_reverse is True


def test_map_output_returns_path_and_writes_file(fake_minibwa, tmp_path):
    reads = tmp_path / "reads.fq"
    reads.write_text("@r\nACGT\n+\nIIII\n")
    out = tmp_path / "out.sam"
    result = minibwa.map(str(tmp_path / "idx"), str(reads), output=str(out))
    assert isinstance(result, pathlib.Path)
    assert result == pathlib.Path(str(out))
    assert out.exists()
    assert "read1" in out.read_text()


def test_map_output_does_not_iterate(fake_minibwa, tmp_path):
    reads = tmp_path / "reads.fq"
    reads.write_text("@r\nACGT\n+\nIIII\n")
    out = tmp_path / "out.sam"
    result = minibwa.map(str(tmp_path / "idx"), str(reads), output=str(out))
    # A Path is not an iterator of records.
    assert not isinstance(result, (SamIterator, PafIterator))


def test_map_argv_records_dash_o(fake_minibwa, tmp_path):
    reads = tmp_path / "reads.fq"
    reads.write_text("@r\nACGT\n+\nIIII\n")
    out = tmp_path / "out.sam"
    minibwa.map(str(tmp_path / "idx"), str(reads), output=str(out), preset="sr")
    argvs = fake_minibwa.argv_log()
    map_argv = next(a for a in argvs if a and a[0] == "map")
    assert "-o" in map_argv
    assert "-x" in map_argv and "sr" in map_argv


def test_map_paf_with_output_returns_path_and_writes_paf(fake_minibwa, tmp_path):
    # Third overload: paf=True together with output= writes PAF to a file and
    # returns a Path (the combined -f + -o branch).
    reads = tmp_path / "reads.fq"
    reads.write_text("@r\nACGT\n+\nIIII\n")
    out = tmp_path / "out.paf"
    result = minibwa.map(str(tmp_path / "idx"), str(reads), paf=True, output=str(out))
    assert isinstance(result, pathlib.Path)
    assert result == pathlib.Path(str(out))
    assert out.exists()
    text = out.read_text()
    # PAF is tab-delimited with no @ SAM header lines.
    assert not any(line.startswith("@") for line in text.splitlines() if line)
    assert "\t" in text
    # Both -f and -o reached the engine.
    map_argv = next(a for a in fake_minibwa.argv_log() if a and a[0] == "map")
    assert "-f" in map_argv
    assert "-o" in map_argv


def test_map_paired_end_reads2_is_trailing_positional(fake_minibwa, tmp_path):
    # Paired-end driven through the public API: reads2 must appear as the last
    # positional after the index and first FASTQ in the real built argv.
    r1 = tmp_path / "r1.fq"
    r1.write_text("@r\nACGT\n+\nIIII\n")
    r2 = tmp_path / "r2.fq"
    r2.write_text("@r\nTGCA\n+\nIIII\n")
    list(minibwa.map(str(tmp_path / "idx"), str(r1), str(r2)))
    map_argv = next(a for a in fake_minibwa.argv_log() if a and a[0] == "map")
    assert str(r1) in map_argv
    assert str(r2) in map_argv
    # reads2 is the final positional (last token in this command, no extra_args).
    assert map_argv[-1] == str(r2)
    assert map_argv.index(str(r2)) == map_argv.index(str(r1)) + 1


def test_map_not_found_eager_at_call_time(monkeypatch, tmp_path):
    # Empty PATH and no MINIBWA_BIN: resolution must fail when map() is CALLED.
    monkeypatch.setenv("PATH", "")
    monkeypatch.delenv("MINIBWA_BIN", raising=False)
    reads = tmp_path / "reads.fq"
    reads.write_text("@r\nACGT\n+\nIIII\n")
    with pytest.raises(MinibwaNotFoundError):
        minibwa.map(str(tmp_path / "idx"), str(reads))


def test_map_nonzero_exit_raises_with_stderr(fake_minibwa, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_MINIBWA_FAIL", "1")
    reads = tmp_path / "reads.fq"
    reads.write_text("@r\nACGT\n+\nIIII\n")
    it = minibwa.map(str(tmp_path / "idx"), str(reads))
    with pytest.raises(MinibwaRunError) as excinfo:
        list(it)
    assert "simulated failure" in excinfo.value.stderr
    assert excinfo.value.returncode == 3


def test_early_break_then_gc_reaps_child(fake_minibwa, tmp_path):
    reads = tmp_path / "reads.fq"
    reads.write_text("@r\nACGT\n+\nIIII\n")
    it = minibwa.map(str(tmp_path / "idx"), str(reads))
    stderr_path = it._process._stderr_path
    assert stderr_path is not None and os.path.exists(stderr_path)
    for _ in it:
        break  # abandon early
    it.close()
    assert it._process._process is not None
    assert it._process._process.poll() is not None
    assert not os.path.exists(stderr_path)
    del it
    gc.collect()


def test_context_manager_cleans_up(fake_minibwa, tmp_path):
    reads = tmp_path / "reads.fq"
    reads.write_text("@r\nACGT\n+\nIIII\n")
    with minibwa.map(str(tmp_path / "idx"), str(reads)) as alns:
        stderr_path = alns._process._stderr_path
        assert stderr_path is not None and os.path.exists(stderr_path)
        first = next(iter(alns))
        assert first.qname == "read1"
    assert not os.path.exists(stderr_path)


def test_index_accepts_index_handle_as_map_first_arg(fake_minibwa, tmp_path):
    fasta = tmp_path / "ref.fa"
    fasta.write_text(">chr1\nACGT\n")
    reads = tmp_path / "reads.fq"
    reads.write_text("@r\nACGT\n+\nIIII\n")
    idx = minibwa.index(str(fasta), str(tmp_path / "idx"))
    # Passing the Index handle directly must reduce to its prefix in argv.
    list(minibwa.map(idx, str(reads)))
    argvs = fake_minibwa.argv_log()
    map_argv = next(a for a in argvs if a and a[0] == "map")
    assert str(tmp_path / "idx") in map_argv
