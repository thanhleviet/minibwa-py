"""Shared pytest fixtures, markers, and sample SAM/PAF payloads."""

from __future__ import annotations

import os
import shutil
import stat
import sys
from pathlib import Path

import pytest

#: Skip a test when no real engine is available (neither on PATH nor MINIBWA_BIN).
requires_minibwa = pytest.mark.skipif(
    shutil.which("minibwa") is None and not os.environ.get("MINIBWA_BIN"),
    reason="minibwa binary not installed",
)

DATA_DIR = Path(__file__).parent / "data"

# A representative SAM payload: header (@HD/@SQ/@PG), a mapped primary record
# with tags, an unmapped record, and a secondary record. The cs:Z value
# deliberately contains a leading colon to exercise split(':', 2).
SAMPLE_SAM = "\n".join(
    [
        "@HD\tVN:1.6\tSO:unsorted\tGO:query",
        "@SQ\tSN:chr1\tLN:600",
        "@SQ\tSN:chr2\tLN:1200",
        "@PG\tID:minibwa\tPN:minibwa\tVN:0.1-r363\tCL:minibwa idx reads.fq",
        "read1\t0\tchr1\t51\t60\t60M\t*\t0\t0\tACGTACGTAC\tIIIIIIIIII"
        "\tNM:i:0\tAS:i:120\tMD:Z:60\tcs:Z::60",
        "read2\t4\t*\t0\t0\t*\t*\t0\t0\tACGTACGTAC\tIIIIIIIIII",
        "read3\t256\tchr2\t101\t0\t60M\t*\t0\t0\tACGTACGTAC\tIIIIIIIIII\tNM:i:2\tAS:i:90",
    ]
)

# A representative PAF payload: a forward and a reverse record, with tp:A and
# cm:i tags and a cs:Z value containing a colon.
SAMPLE_PAF = "\n".join(
    [
        "read1\t60\t0\t60\t+\tchr1\t600\t50\t110\t60\t60\t60"
        "\ttp:A:P\ts1:i:60\tcm:i:1\tNM:i:0\tcs:Z::60",
        "read2\t60\t0\t60\t-\tchr2\t1200\t200\t260\t58\t60\t40\ttp:A:P\tcm:i:2",
    ]
)


@pytest.fixture
def sample_sam() -> str:
    """The :data:`SAMPLE_SAM` text."""
    return SAMPLE_SAM


@pytest.fixture
def sample_paf() -> str:
    """The :data:`SAMPLE_PAF` text."""
    return SAMPLE_PAF


# A self-contained Python stub that masquerades as the engine. It honors the
# subset of the CLI the tests exercise and records its received argv so tests
# can assert on it. Crucially it is launched as a real executable, so it drives
# the real SubprocessBackend Popen plumbing end to end.
_STUB_SOURCE = r'''#!/usr/bin/env python3
import os
import sys

argv = sys.argv[1:]
log_path = os.environ.get("FAKE_MINIBWA_LOG")
if log_path:
    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write("\t".join(argv) + "\n")

if os.environ.get("FAKE_MINIBWA_FAIL") == "1":
    sys.stderr.write("fake minibwa: simulated failure\n")
    sys.exit(3)

if not argv:
    sys.stderr.write("usage: minibwa <command>\n")
    sys.exit(1)

command = argv[0]
rest = argv[1:]

SAM = """@HD\tVN:1.6\tSO:unsorted\tGO:query
@SQ\tSN:chr1\tLN:600
@PG\tID:minibwa\tPN:minibwa\tVN:0.1-r363\tCL:fake
read1\t0\tchr1\t51\t60\t60M\t*\t0\t0\tACGTACGTAC\tIIIIIIIIII\tNM:i:0\tAS:i:120\tcs:Z::60
read2\t4\t*\t0\t0\t*\t*\t0\t0\tACGTACGTAC\tIIIIIIIIII
"""

PAF = """read1\t60\t0\t60\t+\tchr1\t600\t50\t110\t60\t60\t60\ttp:A:P\tcm:i:1\tcs:Z::60
read2\t60\t0\t60\t-\tchr1\t600\t200\t260\t58\t60\t40\ttp:A:P\tcm:i:2
"""


def parse_output(args):
    for i, token in enumerate(args):
        if token == "-o" and i + 1 < len(args):
            return args[i + 1]
    return None


if command == "version":
    sys.stdout.write("0.1-r363\n")
    sys.exit(0)

if command == "index":
    positionals = [a for a in rest if not a.startswith("-")]
    # Skip the option value tokens crudely: positionals are fasta [prefix].
    # The stub only needs to create sidecar files for the chosen prefix.
    fasta = positionals[-2] if len(positionals) >= 2 else positionals[-1]
    prefix = positionals[-1] if len(positionals) >= 2 else positionals[-1]
    for suffix in (".l2b", ".mbw"):
        open(prefix + suffix, "w", encoding="utf-8").close()
    if "--meth" in rest:
        open(prefix + ".meth.mbw", "w", encoding="utf-8").close()
    sys.stderr.write("[M::main] Version: 0.1-r363\n")
    sys.exit(0)

if command == "map":
    payload = PAF if "-f" in rest else SAM
    out = parse_output(rest)
    if out is not None:
        with open(out, "w", encoding="utf-8") as handle:
            handle.write(payload)
    else:
        sys.stdout.write(payload)
    sys.stderr.write("[M::main] done\n")
    sys.exit(0)

sys.stderr.write("fake minibwa: unknown command %s\n" % command)
sys.exit(1)
'''


@pytest.fixture
def fake_minibwa(tmp_path, monkeypatch):
    """Install an executable ``minibwa`` stub on a temp PATH.

    Returns an object exposing ``.path`` (the stub path), ``.bindir`` (the dir
    prepended to PATH), and ``.argv_log()`` (the list of argv lists the stub
    has received this test).
    """
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "minibwa"
    stub.write_text(_STUB_SOURCE.replace("#!/usr/bin/env python3", f"#!{sys.executable}"))
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    log = tmp_path / "argv.log"
    monkeypatch.setenv("FAKE_MINIBWA_LOG", str(log))
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.delenv("MINIBWA_BIN", raising=False)

    stub_path = str(stub)
    bin_dir = str(bindir)

    class _Fake:
        path = stub_path
        bindir = bin_dir

        @staticmethod
        def argv_log():
            if not log.exists():
                return []
            lines = log.read_text(encoding="utf-8").splitlines()
            return [line.split("\t") for line in lines if line]

    return _Fake()
