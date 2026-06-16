# minibwa-py

A pure-Python, standard-library-only subprocess wrapper for the
[`minibwa`](https://github.com/lh3/minibwa) sequence aligner. It shells out to
the `minibwa` engine binary on your `PATH`, parses its SAM/PAF output into
lightweight typed records, and gives you a clean, Pythonic API.

```{note}
**Licensing in one line:** this wrapper is **MIT**. The `minibwa` *engine* it
drives is a **separate program, licensed GPL-2.0-or-later** for the default
build, **installed by you**, and **not bundled** with this package. See the
[Licensing](install.md#licensing) section.
```

## Quickstart

```python
import minibwa

idx = minibwa.index("ref.fa")                  # runs the 'index' command
for aln in minibwa.map(idx, "reads.fq", preset="sr", threads=8):
    print(aln.qname, aln.flag, aln.rname, aln.pos, aln.mapq)

minibwa.version()                              # -> "0.1-r363"
```

`index()` returns an [`Index`](api/index_handle.md) handle that you pass straight
back to `map()`. `map()` streams typed [`Alignment`](api/records.md) records (or
[`PafRecord`](api/records.md) records with `paf=True`).

Read the [Quickstart](quickstart.md) for the full tour, or dive into the
[API reference](api/index.md).

## Why this package

- **Zero runtime dependencies.** Standard library only, so it is trivially
  auditable and never breaks because a transitive dependency did.
- **Typed records.** SAM and PAF lines become frozen, slotted dataclasses with
  correct types and lazily-parsed optional tags.
- **The engine's voice is never swallowed.** Every failure preserves the
  engine's own `argv`, exit code, and `stderr`.
- **Faithful coordinates.** SAM stays 1-based; PAF stays 0-based half-open.
  Nothing is silently normalized.

```{toctree}
:hidden:
:maxdepth: 2

install
quickstart
api/index
```
