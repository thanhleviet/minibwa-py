# FOR-DEVELOPERS

This document is the plain-language tour of `minibwa-py`: how it is built, why it
is built that way, and the sharp edges we sanded down so you don't cut yourself
on them later.

## The one-sentence mental model

`minibwa-py` is a **polite receptionist** standing in front of the `minibwa`
aligner. You hand it a friendly Python request; it translates that into the
exact command-line incantation the engine expects, runs the engine, reads back
what the engine says, and hands you tidy typed objects. Crucially, when the
engine complains, the receptionist **repeats the complaint verbatim** instead of
quietly throwing it in the bin.

## Technical architecture

There are three public functions -- `index()`, `map()`, and `version()` -- and a
small constellation of private modules behind them. The whole thing is a single
"build an argv, run it, parse the output" pipeline:

```
your call
   |
   v
_locate.resolve_binary()   ->  where is the engine?  (binary= > MINIBWA_BIN > PATH)
   |
   v
_cli.build_*_argv()        ->  turn kwargs into ['minibwa', 'map', '-x', 'sr', ...]
   |
   v
_backend / _run            ->  actually run it (capture / stream / write-to-file)
   |
   v
records.Alignment/PafRecord ->  parse each stdout line into a typed object
```

### The one extensibility seam (and why it's hidden)

We resisted the temptation to make everything pluggable. There is exactly **one**
seam: a private `Backend` protocol in `_backend.py` with a single shipped
implementation, `SubprocessBackend`, reached through a module-level default.

Why keep it private? Because a *public* `backend=` keyword on every function
would be complexity the user pays for today against a benefit (a hypothetical
native backend) we don't have yet. The seam exists so that future backend could
drop in without touching the public API -- but until that day, nobody has to
think about it. This is the "open the door but don't put a sign on it" approach
to extensibility.

We explicitly did **not** build a pluggable parser registry or generated
options dataclasses. Two concrete parsers (SAM, PAF) selected by `paf=` and one
data-driven flag table are enough.

## Codebase structure

```
src/minibwa/
  __init__.py   public surface: re-exports the API, records, Index, errors
  _api.py       index()/map()/version() + SamIterator/PafIterator (the orchestra)
  _locate.py    resolve_binary(): the ONE place that knows where the engine is
  _cli.py       FlagSpec tables: kwargs -> argv tokens (pure, no subprocess)
  _backend.py   the internal Backend protocol + SubprocessBackend + default
  _run.py       low-level subprocess: run_capture / run_to_file / StreamProcess
  _tags.py      shared SAM/PAF optional-tag parser (TAG:TYPE:VALUE)
  records.py    frozen, slotted Alignment and PafRecord
  index.py      the Index handle (os.PathLike, sidecar files, from_prefix)
  errors.py     the exception hierarchy
  py.typed      PEP 561 marker so downstream type checkers trust our hints
```

`_api.py` is the conductor: it asks `_locate` where the engine is, asks `_cli`
to build the argv, hands that to a `_backend` method, and wraps the resulting
lines with `records` parsers.

## Technologies used (and why)

- **Python standard library only at runtime.** `subprocess`, `dataclasses`,
  `pathlib`, `logging`, `tempfile`, `shutil`, `os`. Zero third-party runtime
  dependencies means the package is trivially auditable and never breaks because
  some transitive dependency did. For a thin wrapper, dependencies are pure
  liability.
- **hatchling** as the build backend -- modern, PEP 621-native, and it
  single-sources the version from `__init__.py`.
- **ruff** for linting and formatting -- one fast tool instead of several.
- **pytest** for tests, organized in three tiers (see below).

## The interesting lessons (read these before you "improve" something)

### 1. The pipe-deadlock trap, and why stderr goes to a temp file

The classic way to stream a child's stdout is `Popen(stdout=PIPE)` and iterate.
The classic way to *also* capture stderr is a second `stderr=PIPE`. Put those
together and stream gigabytes of SAM, and you can **deadlock**: the OS pipe
buffers are finite, the child blocks writing stderr because nobody is draining
that pipe (you're busy reading stdout), and meanwhile it stops writing stdout,
so your read blocks too. Both sides wait forever.

The textbook fixes are a second reader thread or `select`. We chose the simplest
robust option instead: **redirect stderr to a `NamedTemporaryFile` on disk.** A
file never fills up the way a pipe does, so the child can scribble progress and
warnings freely while we calmly read stdout. At end-of-stream we read the temp
file back and, if the exit code was nonzero, fold its contents into
`MinibwaRunError`. Fewer moving parts, no threads, no deadlock.

The tradeoff: stderr isn't visible *live* during a long run -- it's buffered to
disk and surfaced at the end. For a batch aligner that's fine.

### 2. Eager launch: fail at call time, not at first `next()`

A subtle ergonomics bug in lazy iterators: if you only spawn the process on the
first `next()`, then a typo in the binary path or a bad argument doesn't blow up
until someone starts iterating -- possibly far from the `map()` call. We launch
the process **inside `map()`** (in the iterator's `__init__`). So
`MinibwaNotFoundError` and launch errors land right where you called `map()`.

The tradeoff: a process starts even if you never iterate. The context-manager
form (`with minibwa.map(...) as alns:`) exists to make cleanup explicit in that
case.

### 3. Iterator lifecycle: don't leak children or temp files

If a caller does `for aln in minibwa.map(...): break`, the engine is still
running and the stderr temp file still exists. So `StreamProcess` (and the
iterators wrapping it) implement `close()`, `__enter__`/`__exit__`, and
`__del__`. Break early and let it get garbage-collected, or use a `with` block --
either way the child is terminated (then killed if it won't terminate) and the
temp file is unlinked. There is a dedicated test for exactly this.

### 4. Records use explicit `__slots__`, not `@dataclass(slots=True)`

We want low-overhead, `__dict__`-free records. The package targets Python 3.10+,
so `@dataclass(slots=True)` is available -- but we deliberately keep the
**explicit class-attribute `__slots__`** form. There's a wrinkle that bites
either way: a `frozen=True` dataclass mixing `__slots__` with field defaults can
collide (the default class attribute fights the slot descriptor), so the records
keep their lazy-tags cache in a slot and populate it via `object.__setattr__`,
the sanctioned way to write to a frozen dataclass from inside its own methods.
Hand-writing `__slots__` keeps that layout and the frozen-write pattern explicit
rather than hidden behind a generated class.

### 5. SAM is 1-based, PAF is 0-based half-open -- the off-by-one footgun

Mixing coordinate conventions silently corrupts data in ways that pass small
tests and fail in production. We refuse to "helpfully normalize." `Alignment.pos`
is 1-based exactly as SAM emits it; if you want 0-based, ask for `pos0`. PAF
coordinates stay 0-based half-open. Each record is faithful to its own format,
and that contract is documented loudly.

### 6. `split(':', 2)` for tags -- a real bug the engine showed us

SAM/PAF optional tags look like `TAG:TYPE:VALUE`. The naive `split(':')` breaks
the moment a value itself contains a colon. The real engine emits exactly this:
`cs:Z::70` -- the value is `:70`. Splitting on *all* colons would mangle it.
`field.split(':', 2)` keeps the value intact (`('cs', 'Z', ':70')`). Unknown
TYPE codes are kept as raw strings rather than guessed at, so a future tag type
never crashes the parser.

### 7. Never swallow the engine's voice

Every failure path preserves the engine's own words. `MinibwaRunError` carries
`.argv`, `.returncode`, and `.stderr`. `MinibwaParseError` carries the raw line
and line number. When a bioinformatics pipeline fails at 3 a.m., the engine's
stderr is the single most valuable thing you can have -- so we never drop it.

## The MIT / GPL boundary (important, not legalese for its own sake)

The wrapper code here is MIT. The `minibwa` engine is GPL-2.0-or-later (default
build). We keep them at arm's length on purpose: this package ships and links
**no** engine code. It calls a binary the user installed (via bioconda). That
"runs a separate program over a process boundary" relationship is why an
MIT wrapper around a GPL tool is fine -- we're a caller, not a derivative work.
If you ever consider bundling the engine or linking its library, stop and get
the licensing reviewed first.

## Testing tiers

- **Tier 1 (pure unit):** binary resolution order, exact argv construction for
  every flag, record parsing and tag typing, the `Index` handle. No subprocess.
- **Tier 2 (hermetic):** real `python -c` children prove the no-deadlock path
  and that nonzero exits raise with stderr; an on-PATH `fake_minibwa` stub
  exercises the real `SubprocessBackend` Popen plumbing end-to-end without the
  GPL engine.
- **Tier 3 (integration):** runs against a real engine when present, auto-skips
  via the `requires_minibwa` marker when absent. CI deliberately does not
  install the engine, which also proves the skip path works.

Run everything locally:

```bash
ruff check . && ruff format --check . && pytest
```

## Documentation

The API reference and guides are built with [Sphinx](https://www.sphinx-doc.org/)
and published on [Read the Docs](https://minibwa-py.readthedocs.io). The source
lives under `docs/`: narrative pages (`index`, `install`, `quickstart`) are MyST
Markdown, and the `docs/api/` pages pull docstrings straight from the code via
`autodoc` + `napoleon`, so the reference can never drift from the source.

Build it locally:

```bash
pip install -e ".[docs]"
sphinx-build -W --keep-going -b html docs docs/_build/html
```

The `-W` flag turns warnings into errors -- the same gate CI and Read the Docs
enforce -- so a missing cross-reference or an undocumented new public symbol
fails the build instead of silently degrading the site. The version is
single-sourced from the installed package metadata, never hardcoded in
`docs/conf.py`.

### Publishing to Read the Docs (one-time)

The repository ships `.readthedocs.yaml`, so the hosting side is already
configured -- it just needs to be connected once:

1. Sign in at [readthedocs.org](https://readthedocs.org) and choose **Import a
   Project**, then connect the GitHub account and pick this repository.
2. **Name the project exactly `minibwa-py`.** Read the Docs derives the site
   slug from the project name, and the published URL must be
   `minibwa-py.readthedocs.io` to match the links in this file and the README.
3. Leave the rest at the defaults and import. Read the Docs detects
   `.readthedocs.yaml` automatically and runs the first build immediately.

After that it rebuilds on every push to the default branch. Enable **Build pull
requests** in the project's *Advanced Settings* to get a preview build (and the
same `fail_on_warning` gate) on each PR.
