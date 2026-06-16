# Records

Two frozen, slotted dataclasses. Optional tags are parsed lazily on first
`.tags` access and cached. Coordinates are kept faithful to each format and
never silently normalized.

```{note}
The supported constructors are the {meth}`~minibwa.Alignment.from_sam_line` and
{meth}`~minibwa.PafRecord.from_paf_line` classmethods. The generated dataclass
``__init__`` takes private fields and is not part of the public API.
```

## Alignment

```{eval-rst}
.. currentmodule:: minibwa

.. autoclass:: Alignment
   :members:
   :undoc-members:
   :exclude-members: __init__
```

## PafRecord

```{eval-rst}
.. currentmodule:: minibwa

.. autoclass:: PafRecord
   :members:
   :undoc-members:
   :exclude-members: __init__
```
