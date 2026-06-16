# API reference

Everything below is re-exported from the top-level `minibwa` package, so you
import it as `minibwa.map`, `minibwa.Alignment`, and so on.

```{eval-rst}
.. currentmodule:: minibwa

.. rubric:: Functions

.. autosummary::

   index
   map
   version

.. rubric:: Streaming iterators

.. autosummary::

   SamIterator
   PafIterator

.. rubric:: Records

.. autosummary::

   Alignment
   PafRecord

.. rubric:: Index handle

.. autosummary::

   Index

.. rubric:: Exceptions

.. autosummary::

   MinibwaError
   MinibwaNotFoundError
   MinibwaRunError
   MinibwaParseError
```

```{toctree}
:maxdepth: 2

functions
records
index_handle
errors
```
