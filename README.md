# minibwa-py

A pure-Python, stdlib-only subprocess wrapper for the
[`minibwa`](https://bioconda.github.io/) sequence aligner. It shells out to the
`minibwa` engine binary on your `PATH`, parses its SAM/PAF output into
lightweight typed records, and gives you a clean, Pythonic API.

> **Licensing in one line:** this wrapper is **MIT**. The `minibwa` *engine* it
> drives is a **separate program, licensed GPL-2.0-or-later** for the default
> build, **installed by you**, and **not bundled** with this package. See
> [Licensing](#licensing).

## Install

```bash
pip install minibwa-py
```

`minibwa-py` does **not** ship the aligner. Install the engine separately:

```bash
conda install -c bioconda minibwa
```

If the binary cannot be found you get a `MinibwaNotFoundError` whose message is:

```
minibwa binary not found; install with "conda install -c bioconda minibwa", set MINIBWA_BIN, or pass binary=
```

## Quickstart

```python
import minibwa

idx = minibwa.index("ref.fa")                  # runs the 'index' command
for aln in minibwa.map(idx, "reads.fq", preset="sr", threads=8):
    print(aln.qname, aln.flag, aln.rname, aln.pos, aln.mapq)

minibwa.version()                              # -> "0.1-r363"
```

`index()` returns an `Index` handle that you pass straight back to `map()`. You
can also pass any path-like index prefix directly.

## Paired-end

Supply the second FASTQ as the third positional argument:

```python
for aln in minibwa.map(idx, "R1.fq", "R2.fq", preset="sr", threads=8):
    ...
```

## PAF output

Pass `paf=True` to stream `PafRecord` objects instead of `Alignment`:

```python
for rec in minibwa.map(idx, "reads.fq", paf=True):
    print(rec.qname, rec.tname, rec.tstart, rec.tend, rec.strand, rec.identity)
```

## Writing to a file

Pass `output=` to let the engine write the file itself. The call runs to
completion (no iteration) and returns a `pathlib.Path`:

```python
out = minibwa.map(idx, "reads.fq", output="out.sam")
print(out)  # PosixPath('out.sam')
```

## Context-manager usage

The streaming iterators own a live subprocess. Use a `with` block to guarantee
the child is terminated and the stderr temp file is removed even if you break
out early:

```python
with minibwa.map(idx, "reads.fq") as alns:
    for aln in alns:
        if aln.is_secondary:
            continue
        do_something(aln)
```

Abandoning the iterator (breaking out, then letting it be garbage-collected)
also cleans up, but the context manager makes it explicit.

## Records

`Alignment` exposes the 11 mandatory SAM fields with correct types
(`qname`, `flag`, `rname`, `pos`, `mapq`, `cigar`, `rnext`, `pnext`, `tlen`,
`seq`, `qual`), a `pos0` 0-based helper, flag-decoding boolean properties
(`is_mapped`, `is_reverse`, `is_secondary`, `is_supplementary`, ...), and a
lazily-parsed, immutable `tags` mapping (e.g. `aln.tags["NM"]`).

`PafRecord` exposes the 12 mandatory PAF columns (0-based half-open coordinates),
`is_reverse`, an `identity` property, and the same lazy `tags` mapping.

SAM `POS` is **1-based**; PAF coordinates are **0-based half-open**. Each record
stays faithful to its own format; nothing is silently normalized.

## Binary discovery

The engine is located in this order:

1. an explicit `binary=` argument,
2. the `MINIBWA_BIN` environment variable,
3. `shutil.which("minibwa")`.

```python
minibwa.version(binary="/opt/minibwa/bin/minibwa")
```

## Error model

* `MinibwaNotFoundError` -- the engine binary could not be located.
* `MinibwaRunError` -- the engine exited nonzero; carries `.argv`,
  `.returncode`, and the captured `.stderr` (diagnostics are never swallowed).
* `MinibwaParseError` (also a `ValueError`) -- a SAM/PAF line could not be
  parsed; carries the offending `.line` and (when from a stream) `.lineno`.

## Escape hatch

Any option not modeled as a keyword can be appended verbatim:

```python
minibwa.map(idx, "reads.fq", extra_args=["--some-future-flag", "value"])
```

## Logging

The library logs through `logging.getLogger("minibwa")` and installs a
`NullHandler`, so it stays silent unless you configure logging. The full argv is
logged at `DEBUG`.

## Platform

Linux and macOS only (the engine is POSIX/conda-only). Windows is out of scope.

## Licensing

The Python wrapper code in this repository is licensed under the **MIT License**
(see [`LICENSE`](LICENSE)).

The `minibwa` engine is a **separate work** with its **own license**
(GPL-2.0-or-later for the default build). This package does not include, bundle,
or statically link any engine code -- it only invokes the engine binary that you
install yourself. Your use of the engine is governed by the engine's own
license.
