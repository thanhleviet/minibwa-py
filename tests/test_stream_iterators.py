"""Iterator-level streaming tests for SamIterator / PafIterator.

These drive the *real* SubprocessBackend Popen plumbing: a small ``python -c``
child writes a fixed payload (read verbatim from a temp file) to stdout, so the
SAM/PAF iterators parse it exactly as they would the engine's output. This lets
us cover header parsing, secondary/multi-contig records, blank-line skipping,
and malformed-header tolerance without the real engine.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

import minibwa._backend as _backend
from minibwa import Alignment, MinibwaParseError, PafIterator, PafRecord, SamIterator
from minibwa._run import StreamProcess

from .conftest import SAMPLE_PAF, SAMPLE_SAM


class _PayloadBackend:
    """A backend whose ``stream_lines`` emits a fixed payload via a real child."""

    def __init__(self, payload_path: Path) -> None:
        self._payload_path = payload_path

    def resolve(self, binary):
        return sys.executable

    def run_capture(self, argv, *, timeout=None):
        return ""

    def run_to_file(self, argv, *, timeout=None):
        pass

    def stream_lines(self, argv, *, timeout=None) -> StreamProcess:
        program = (
            "import sys\n"
            f"sys.stdout.write(open({str(self._payload_path)!r}, encoding='utf-8').read())\n"
        )
        return StreamProcess([sys.executable, "-c", program], timeout=timeout)


@pytest.fixture
def payload_backend(tmp_path):
    """Return a factory that installs a payload-emitting backend and builds an iterator."""
    original = _backend.get_default_backend()
    counter = {"n": 0}

    def make(payload: str, iterator_cls):
        counter["n"] += 1
        path = tmp_path / f"payload{counter['n']}.txt"
        path.write_text(payload, encoding="utf-8")
        _backend.set_default_backend(_PayloadBackend(path))
        return iterator_cls(["fake", "map"])

    yield make
    _backend.set_default_backend(original)


# --- SAM iterator over the rich conftest fixture --------------------------


def test_sam_iterator_parses_headers_and_multi_contig(payload_backend, sample_sam):
    it: SamIterator = payload_backend(sample_sam, SamIterator)
    records = list(it)
    assert [r.qname for r in records] == ["read1", "read2", "read3"]
    assert all(isinstance(r, Alignment) for r in records)
    # Both @SQ lines parse into reference_lengths.
    assert it.reference_lengths == {"chr1": 600, "chr2": 1200}
    assert any(line.startswith("@HD") for line in it.header)


def test_sam_iterator_yields_secondary_record(payload_backend, sample_sam):
    it: SamIterator = payload_backend(sample_sam, SamIterator)
    records = list(it)
    by_name = {r.qname: r for r in records}
    # read3 has flag 256 -> secondary; the secondary record IS yielded.
    assert by_name["read3"].is_secondary is True
    assert by_name["read1"].is_secondary is False
    assert by_name["read2"].is_unmapped is True


def test_sam_iterator_module_constant_matches_fixture():
    # Guard that SAMPLE_SAM (consumed here) and the fixture agree.
    assert SAMPLE_SAM.splitlines()[1].startswith("@SQ")


# --- PAF iterator over the conftest fixture -------------------------------


def test_paf_iterator_parses_forward_and_reverse(payload_backend, sample_paf):
    it: PafIterator = payload_backend(sample_paf, PafIterator)
    records = list(it)
    assert len(records) == 2
    assert all(isinstance(r, PafRecord) for r in records)
    assert records[0].is_reverse is False
    assert records[1].is_reverse is True
    assert SAMPLE_PAF  # the module constant is also exercised


# --- robustness branches: blank lines & malformed @SQ LN ------------------


def test_sam_iterator_skips_blank_lines(payload_backend):
    payload = "\n".join(
        [
            "@SQ\tSN:chr1\tLN:600",
            "read1\t0\tchr1\t1\t60\t*\t*\t0\t0\t*\t*",
            "",  # blank line between records must be skipped, not parsed
            "read2\t0\tchr1\t2\t60\t*\t*\t0\t0\t*\t*",
        ]
    )
    it: SamIterator = payload_backend(payload, SamIterator)
    records = list(it)
    assert [r.qname for r in records] == ["read1", "read2"]


def test_paf_iterator_skips_blank_lines(payload_backend):
    line = "r{0}\t60\t0\t60\t+\tchr1\t600\t50\t110\t60\t60\t60"
    payload = "\n".join([line.format(1), "", line.format(2)])
    it: PafIterator = payload_backend(payload, PafIterator)
    records = list(it)
    assert [r.qname for r in records] == ["r1", "r2"]


def test_sam_iterator_tolerates_non_integer_ln(payload_backend):
    payload = "\n".join(
        [
            "@SQ\tSN:chrX\tLN:notanint",  # bad LN -> contig simply absent
            "@SQ\tSN:chr1\tLN:600",  # good LN -> present
            "read1\t0\tchr1\t1\t60\t*\t*\t0\t0\t*\t*",
        ]
    )
    it: SamIterator = payload_backend(payload, SamIterator)
    records = list(it)
    assert [r.qname for r in records] == ["read1"]
    assert it.reference_lengths == {"chr1": 600}
    assert "chrX" not in it.reference_lengths


# --- parse-error cleanup (no leaked process / temp file) ------------------


class _MalformedThenStallBackend:
    """Emits one malformed SAM line then stalls, to prove parse-error cleanup."""

    def resolve(self, binary):
        return sys.executable

    def run_capture(self, argv, *, timeout=None):  # pragma: no cover
        return ""

    def run_to_file(self, argv, *, timeout=None):  # pragma: no cover
        pass

    def stream_lines(self, argv, *, timeout=None) -> StreamProcess:
        program = (
            "import sys, time\nsys.stdout.write('bad\\tline\\n')\nsys.stdout.flush()\n"
            "time.sleep(30)\n"
        )
        return StreamProcess([sys.executable, "-c", program], timeout=timeout)


def test_parse_error_during_stream_reaps_child_and_unlinks_tempfile():
    original = _backend.get_default_backend()
    _backend.set_default_backend(_MalformedThenStallBackend())
    try:
        it = SamIterator(["fake", "map"])
        stderr_path = it._process._stderr_path
        assert stderr_path is not None and os.path.exists(stderr_path)
        with pytest.raises(MinibwaParseError):
            next(iter(it))
        # The still-running child was reaped deterministically (not a zombie),
        # and its stderr temp file was unlinked, before the error propagated.
        assert it._process._process is not None
        assert it._process._process.poll() is not None
        assert not os.path.exists(stderr_path)
    finally:
        _backend.set_default_backend(original)
