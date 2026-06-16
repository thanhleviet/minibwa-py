# Functions

The three entry points of the package: build an index, map reads against it, and
query the engine version.

```{eval-rst}
.. currentmodule:: minibwa

.. autofunction:: index

.. autofunction:: map

.. autofunction:: version
```

## Streaming iterators

When `output` is not set, {func}`minibwa.map` launches the engine eagerly and
returns one of these iterators. Both raise {exc}`minibwa.MinibwaRunError` at
end-of-stream if the engine exits nonzero.

Each iterator owns a live subprocess and exposes:

- `close()` — terminate the engine and remove the stderr temp file. Also invoked
  by the context-manager protocol (`with minibwa.map(...) as alns:`) and on
  garbage collection, so an abandoned iterator never leaks a process.
- `header` — the raw `@` header lines consumed during iteration (SAM mode).
- `reference_lengths` — a `{name: length}` mapping parsed from `@SQ` lines,
  populated once iteration has passed the header.

```{eval-rst}
.. currentmodule:: minibwa

.. autoclass:: SamIterator
   :members:
   :inherited-members:
   :exclude-members: __init__

.. autoclass:: PafIterator
   :members:
   :inherited-members:
   :exclude-members: __init__
```
