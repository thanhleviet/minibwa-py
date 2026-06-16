# Quickstart

This page is a hands-on tour of the public API. For the exhaustive parameter
lists, see the [API reference](api/index.md).

## Index, then map

```python
import minibwa

idx = minibwa.index("ref.fa")                  # runs the 'index' command
for aln in minibwa.map(idx, "reads.fq", preset="sr", threads=8):
    print(aln.qname, aln.flag, aln.rname, aln.pos, aln.mapq)

minibwa.version()                              # -> "0.1-r363"
```

```text
read1 0 chr1 51 60
read2 0 chr1 201 60
read3 0 chr1 401 60
```

[`index()`](api/functions.md) returns an [`Index`](api/index_handle.md) handle
that you pass straight back to [`map()`](api/functions.md). You can also pass any
path-like index prefix directly.

## Paired-end

Supply the second FASTQ as the third positional argument:

```python
for aln in minibwa.map(idx, "R1.fq", "R2.fq", preset="sr", threads=8):
    ...
```

## PAF output

Pass `paf=True` to stream [`PafRecord`](api/records.md) objects instead of
[`Alignment`](api/records.md):

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

## Reference lengths and the SAM header

In SAM mode the iterator consumes the `@` header lines for you (they are never
yielded as records) and keeps them. `@SQ` lines are parsed into a
name-to-length mapping, available once iteration has passed the header:

```python
alns = minibwa.map(idx, "reads.fq")
records = list(alns)
print(alns.reference_lengths)   # {'chr1': 600}
print(alns.header)              # the raw '@HD' / '@SQ' / '@PG' lines
```

## Reusing a pre-built index

If the index already exists on disk — built earlier, or by the `minibwa index`
CLI — wrap it with [`Index.from_prefix`](api/index_handle.md) instead of
rebuilding:

```python
idx = minibwa.Index.from_prefix("ref.fa")   # no rebuild; just a handle
for aln in minibwa.map(idx, "reads.fq"):
    ...
```

`map()` also accepts a bare prefix string or any `os.PathLike` as its first
argument, so `minibwa.map("ref.fa", "reads.fq")` works without a handle at all.

## Records

[`Alignment`](api/records.md) exposes the 11 mandatory SAM fields with correct
types (`qname`, `flag`, `rname`, `pos`, `mapq`, `cigar`, `rnext`, `pnext`,
`tlen`, `seq`, `qual`), a `pos0` 0-based helper, flag-decoding boolean
properties (`is_mapped`, `is_reverse`, `is_secondary`, `is_supplementary`, ...),
and a lazily-parsed, immutable `tags` mapping (e.g. `aln.tags["NM"]`).

[`PafRecord`](api/records.md) exposes the 12 mandatory PAF columns (0-based
half-open coordinates), `is_reverse`, an `identity` property, and the same lazy
`tags` mapping.

```{warning}
SAM `POS` is **1-based**; PAF coordinates are **0-based half-open**. Each record
stays faithful to its own format; nothing is silently normalized. The same read
that aligns to the 51st base of `chr1` reports `pos == 51` as an `Alignment` but
`tstart == 50` as a `PafRecord` — one locus, two conventions. Reach for
`Alignment.pos0` when you need the 0-based start.
```

## Error handling

All errors inherit from [`MinibwaError`](api/errors.md), so you can catch one
specifically or the whole family at once. For the streaming path the engine's
exit status is checked at end-of-stream, so wrap the iteration:

```python
try:
    alignments = list(minibwa.map(idx, "reads.fq"))
except minibwa.MinibwaRunError as exc:
    print("exit", exc.returncode)   # e.g. -6 (SIGABRT)
    print(exc.stderr)               # the engine's own diagnostics, verbatim
    raise
```

See the [Exceptions](api/errors.md) reference for the full hierarchy.

## Timeouts

`index()`, `map()`, and `version()` all accept `timeout=` (seconds). For
`output=` and `version()` it bounds the run-to-completion call; for the
streaming path it is a deadline checked while iterating, so a stalled engine
raises `MinibwaRunError` instead of hanging the caller forever:

```python
for aln in minibwa.map(idx, "reads.fq", timeout=300):
    ...
```

## Escape hatch

Any option not modeled as a keyword can be appended verbatim:

```python
minibwa.map(idx, "reads.fq", extra_args=["--some-future-flag", "value"])
```

## Logging

The library logs through `logging.getLogger("minibwa")` and installs a
`NullHandler`, so it stays silent unless you configure logging. The full argv is
logged at `DEBUG`.
